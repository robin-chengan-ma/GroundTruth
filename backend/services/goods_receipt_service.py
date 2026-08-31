"""Phase 4.1 C6-1：分批收貨草稿、查詢與送驗。"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.erp.models import GoodsReceipt, GoodsReceiptItem
from apps.procurement.models import PurchaseOrder
from repositories.erp import GoodsReceiptRepository
from repositories.procurement import PurchaseOrderRepository
from services.inventory_balance_service import (
    InventoryBalanceConflict,
    remove_receipt_in_transit,
)
from services.rbac_service import get_permission_codes


class GoodsReceiptError(Exception):
    code = "invalid_goods_receipt"


class GoodsReceiptNotFound(GoodsReceiptError):
    code = "not_found"


class GoodsReceiptPermissionDenied(GoodsReceiptError):
    code = "permission_denied"


class GoodsReceiptConflict(GoodsReceiptError):
    code = "conflict"


def _audit(user, action_type, receipt):
    AuditLog.objects.create(
        user=user,
        action_type=action_type,
        real_query_summary=f"goods_receipt_id={receipt.id}",
        verification_result="n/a",
    )


def _positive_quantity(value):
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise GoodsReceiptError("實收數量必須是大於 0 的數字") from exc
    if not quantity.is_finite() or quantity <= 0 or quantity.as_tuple().exponent < -3:
        raise GoodsReceiptError("實收數量必須是大於 0 且最多三位小數的數字")
    return quantity


def _validate_items(purchase_order, payload_items):
    if not isinstance(payload_items, list) or not payload_items:
        raise GoodsReceiptError("收貨單至少需要一筆實收明細")
    order_items = {item.id: item for item in purchase_order.items.all()}
    normalized = []
    seen = set()
    for row in payload_items:
        if not isinstance(row, dict):
            raise GoodsReceiptError("收貨明細格式錯誤")
        try:
            item_id = int(row.get("purchase_order_item_id"))
        except (TypeError, ValueError) as exc:
            raise GoodsReceiptError("採購單明細編號格式錯誤") from exc
        if item_id in seen:
            raise GoodsReceiptError("同一採購單明細不得在同批收貨重複出現")
        if item_id not in order_items:
            raise GoodsReceiptError("收貨明細不屬於指定採購單")
        replacement_line_id = row.get("replacement_variance_line_id")
        if replacement_line_id is not None:
            try:
                replacement_line_id = int(replacement_line_id)
            except (TypeError, ValueError) as exc:
                raise GoodsReceiptError("替換處理明細編號格式錯誤") from exc
            if replacement_line_id <= 0:
                raise GoodsReceiptError("替換處理明細編號格式錯誤")
        seen.add(item_id)
        normalized.append(
            {
                "purchase_order_item": order_items[item_id],
                "received_quantity": _positive_quantity(row.get("received_quantity")),
                "lot_no": str(row.get("lot_no") or "").strip(),
                "replacement_variance_line_id": replacement_line_id,
            }
        )
    return normalized


@transaction.atomic
def create_goods_receipt(user, payload):
    if "receipt.record" not in get_permission_codes(user):
        raise GoodsReceiptPermissionDenied("沒有建立收貨單的權限")
    try:
        purchase_order_id = int(payload.get("purchase_order_id"))
        purchase_order = PurchaseOrderRepository.get_for_update(purchase_order_id)
    except (TypeError, ValueError):
        raise GoodsReceiptError("採購單編號格式錯誤") from None
    except ObjectDoesNotExist as exc:
        raise GoodsReceiptNotFound("找不到指定的採購單") from exc
    if purchase_order.status not in {
        PurchaseOrder.Status.ISSUED,
        PurchaseOrder.Status.PARTIALLY_RECEIVED,
    }:
        raise GoodsReceiptConflict("只有已發出或部分收貨的採購單可以收貨")
    normalized_items = _validate_items(purchase_order, payload.get("items"))
    sequence = GoodsReceiptRepository.next_sequence_for_purchase_order(purchase_order.id)
    try:
        with transaction.atomic():
            receipt = GoodsReceipt.objects.create(
                receipt_no=f"GR-{purchase_order.id:06d}-{sequence:03d}",
                purchase_order=purchase_order,
                received_by=user,
            )
            for row in normalized_items:
                GoodsReceiptItem.objects.create(receipt=receipt, **row)
    except IntegrityError as exc:
        raise GoodsReceiptConflict("收貨數量超過未收數量，或收貨單已由其他交易建立") from exc
    _audit(user, "goods_receipt_created", receipt)
    return GoodsReceiptRepository.get(receipt.id)


def list_accessible_goods_receipts(user):
    permissions = get_permission_codes(user)
    can_read_all = bool({"receipt.record", "inspection.decide", "audit.read"} & permissions)
    if not can_read_all and "purchase_request.read_own" not in permissions:
        raise GoodsReceiptPermissionDenied("沒有讀取收貨單的權限")
    return GoodsReceiptRepository.accessible(user_id=user.id, can_read_all=can_read_all)


def get_accessible_goods_receipt(user, receipt_id):
    try:
        return list_accessible_goods_receipts(user).get(pk=receipt_id)
    except GoodsReceipt.DoesNotExist as exc:
        raise GoodsReceiptNotFound("找不到指定的收貨單") from exc


@transaction.atomic
def submit_goods_receipt(user, receipt_id, version):
    if "receipt.record" not in get_permission_codes(user):
        raise GoodsReceiptPermissionDenied("沒有送出收貨單的權限")
    try:
        version = int(version)
    except (TypeError, ValueError) as exc:
        raise GoodsReceiptError("version 必須是正整數") from exc
    if version <= 0:
        raise GoodsReceiptError("version 必須是正整數")
    try:
        receipt = GoodsReceiptRepository.get_for_update(receipt_id)
    except ObjectDoesNotExist as exc:
        raise GoodsReceiptNotFound("找不到指定的收貨單") from exc
    if receipt.status != GoodsReceipt.Status.DRAFT:
        raise GoodsReceiptConflict("只有草稿收貨單可以送驗")
    if receipt.version != version:
        raise GoodsReceiptConflict("收貨單版本已變更，請重新整理")
    if not receipt.items.exists():
        raise GoodsReceiptConflict("收貨單沒有可送驗的明細")
    try:
        remove_receipt_in_transit(receipt)
    except InventoryBalanceConflict as exc:
        raise GoodsReceiptConflict(str(exc)) from exc
    receipt.status = GoodsReceipt.Status.INSPECTING
    receipt.received_at = timezone.now()
    receipt.version += 1
    receipt.save(update_fields=["status", "received_at", "version", "updated_at"])
    _audit(user, "goods_receipt_submitted", receipt)
    return GoodsReceiptRepository.get(receipt.id)


def serialize_goods_receipt(receipt):
    return {
        "id": receipt.id,
        "receipt_no": receipt.receipt_no,
        "purchase_order_id": receipt.purchase_order_id,
        "po_no": receipt.purchase_order.po_no,
        "request_id": receipt.purchase_order.award.rfq.request_id,
        "supplier": {
            "id": receipt.purchase_order.supplier_id,
            "name": receipt.purchase_order.supplier.name,
        },
        "status": receipt.status,
        "received_by": (
            {"id": receipt.received_by_id, "name": receipt.received_by.name}
            if receipt.received_by_id
            else None
        ),
        "received_at": receipt.received_at,
        "version": receipt.version,
        "items": [
            {
                "id": item.id,
                "purchase_order_item_id": item.purchase_order_item_id,
                "product_id": item.purchase_order_item.product_id,
                "product_name": item.purchase_order_item.product_name_snapshot,
                "received_quantity": f"{item.received_quantity:.3f}",
                "lot_no": item.lot_no,
                "replacement_variance_line_id": item.replacement_variance_line_id,
                "inspection": (
                    {
                        "id": item.quality_inspection.id,
                        "status": item.quality_inspection.status,
                        "accepted_quantity": f"{item.quality_inspection.accepted_quantity:.3f}",
                        "defective_quantity": f"{item.quality_inspection.defective_quantity:.3f}",
                        "rejected_quantity": f"{item.quality_inspection.rejected_quantity:.3f}",
                        "defect_details": item.quality_inspection.defect_details,
                        "notes": item.quality_inspection.notes,
                        "inspected_by": (
                            {
                                "id": item.quality_inspection.inspected_by_id,
                                "name": item.quality_inspection.inspected_by.name,
                            }
                            if item.quality_inspection.inspected_by_id
                            else None
                        ),
                        "inspected_at": item.quality_inspection.inspected_at,
                    }
                    if hasattr(item, "quality_inspection")
                    else None
                ),
            }
            for item in receipt.items.all().order_by("purchase_order_item__line_no")
        ],
    }
