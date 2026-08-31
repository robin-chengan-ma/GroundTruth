"""Phase 4.1 C6-3C 低庫存採購建議與轉單流程。"""

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.erp.models import Inventory, InventoryBalance, PurchaseSuggestion
from repositories.erp import PurchaseSuggestionRepository
from services.purchase_request_draft_service import create_draft
from services.rbac_service import user_has_permission


class PurchaseSuggestionError(Exception):
    code = "invalid_purchase_suggestion"


class PurchaseSuggestionNotFound(PurchaseSuggestionError):
    code = "not_found"


class PurchaseSuggestionPermissionDenied(PurchaseSuggestionError):
    code = "permission_denied"


class PurchaseSuggestionConflict(PurchaseSuggestionError):
    code = "conflict"


def _get_for_update(pk):
    try:
        return PurchaseSuggestionRepository.get_for_update(pk)
    except ObjectDoesNotExist as exc:
        raise PurchaseSuggestionNotFound("找不到指定的採購建議") from exc


def create_if_below_threshold(movement, balance=None):
    if not movement.affects_balance:
        return None
    try:
        inventory = Inventory.objects.select_for_update().get(product_id=movement.product_id)
    except Inventory.DoesNotExist:
        return None
    balance = balance or InventoryBalance.objects.select_for_update().get(
        product_id=movement.product_id
    )
    inventory_position = (
        balance.on_hand_quantity
        - balance.reserved_quantity
        + balance.in_transit_quantity
    )
    threshold = Decimal(inventory.threshold)
    if inventory_position >= threshold:
        return None
    if PurchaseSuggestionRepository.has_unfinished_for_product(movement.product_id):
        return None
    return PurchaseSuggestionRepository.create(
        product_id=movement.product_id,
        suggested_qty=threshold - inventory_position,
        source_movement=movement,
    )


@transaction.atomic
def convert_to_draft(user, pk, payload):
    if not user_has_permission(user, "purchase_request.create"):
        raise PurchaseSuggestionPermissionDenied("沒有建立採購需求的權限")
    suggestion = _get_for_update(pk)
    if suggestion.status != PurchaseSuggestion.Status.PENDING:
        raise PurchaseSuggestionConflict("只有待處理的採購建議可以轉單")
    if suggestion.purchase_request_id is not None:
        raise PurchaseSuggestionConflict("這筆採購建議已經轉成採購需求")
    request = create_draft(user, {
        "items": [{
            "product_id": suggestion.product_id,
            "quantity": suggestion.suggested_qty,
            "specifications": suggestion.product.specifications,
            "unit_of_measure": suggestion.product.unit_of_measure,
        }],
        "supplier_ids": payload.get("supplier_ids"),
        "purpose": payload.get("purpose") or f"低庫存自動補貨：{suggestion.product.name}",
        "needed_by": payload.get("needed_by"),
        "currency": payload.get("currency") or "TWD",
    })
    request.source = "inventory_suggestion"
    request.save(update_fields=["source", "updated_at"])
    suggestion.purchase_request = request
    suggestion.save(update_fields=["purchase_request"])
    return suggestion


@transaction.atomic
def dismiss(user, pk):
    if getattr(getattr(user, "role", None), "role", None) != "admin":
        raise PurchaseSuggestionPermissionDenied("只有系統管理員可以忽略採購建議")
    suggestion = _get_for_update(pk)
    if suggestion.status != PurchaseSuggestion.Status.PENDING:
        raise PurchaseSuggestionConflict("只有待處理的採購建議可以忽略")
    if suggestion.purchase_request_id is not None:
        raise PurchaseSuggestionConflict("已轉單的採購建議不可忽略")
    suggestion.status = PurchaseSuggestion.Status.DISMISSED
    suggestion.save(update_fields=["status"])
    return suggestion


def mark_request_in_progress(request_id):
    PurchaseSuggestionRepository.pending_for_requests([request_id]).update(
        status=PurchaseSuggestion.Status.IN_PROGRESS
    )


def mark_request_processed(request_id):
    PurchaseSuggestionRepository.in_progress_for_request(request_id).update(
        status=PurchaseSuggestion.Status.PROCESSED
    )
