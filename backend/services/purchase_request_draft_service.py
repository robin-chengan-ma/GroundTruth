"""Phase 4.1.4 採購需求草稿、試算預覽與確認提交。"""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import uuid4

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, models, transaction
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.audit.models import AuditLog, ManualReviewQueue
from apps.crm.models import Supplier
from apps.erp.models import Product
from apps.procurement.models import (
    ApprovalCase,
    AwardDecision,
    PurchaseRequest,
    PurchaseRequestItem,
    Rfq,
    RfqSupplier,
)
from repositories.procurement import PurchaseRequestRepository
from services.candidate_audit_service import CandidateTokenError, record_candidate_confirmation
from services.rbac_service import user_has_permission


class DraftError(Exception):
    code = "invalid_draft"


class DraftClarificationRequired(DraftError):
    code = "clarification_required"

    def __init__(self, missing_fields):
        self.missing_fields = missing_fields
        super().__init__("採購需求資料不完整，請補充標示欄位")


class DraftPermissionDenied(DraftError):
    code = "permission_denied"


class DraftNotFound(DraftError):
    code = "not_found"


class DraftVersionConflict(DraftError):
    code = "version_conflict"


def _require_permission(user, code):
    if not user_has_permission(user, code):
        raise DraftPermissionDenied("沒有執行此操作的權限")


def _parse_quantity(value, field_name, missing_fields):
    if value in (None, ""):
        missing_fields.append(field_name)
        return None
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DraftError(f"{field_name} 必須是有效數量") from exc
    if not quantity.is_finite() or quantity <= 0 or quantity.as_tuple().exponent < -3:
        raise DraftError(f"{field_name} 必須是大於 0 且最多三位小數的數量")
    return quantity


def _validate_payload(payload, *, require_items=True, require_suppliers=True):
    missing_fields = []
    items = payload.get("items")
    supplier_ids = payload.get("supplier_ids")
    if items is not None and not isinstance(items, list):
        raise DraftError("items 必須是陣列")
    if supplier_ids is not None and not isinstance(supplier_ids, list):
        raise DraftError("supplier_ids 必須是陣列")
    if require_items and not items:
        missing_fields.append("items")
    if require_suppliers and not supplier_ids:
        missing_fields.append("supplier_ids")
    normalized_items = []
    for index, item in enumerate(items or []):
        if not isinstance(item, dict):
            raise DraftError(f"items.{index} 必須是 object")
        product_id = item.get("product_id")
        if product_id in (None, ""):
            missing_fields.append(f"items.{index}.product_id")
        quantity = _parse_quantity(item.get("quantity"), f"items.{index}.quantity", missing_fields)
        specifications = item.get("specifications", {})
        if not isinstance(specifications, dict):
            raise DraftError(f"items.{index}.specifications 必須是 JSON object")
        normalized_items.append({**item, "product_id": product_id, "quantity": quantity})
    if missing_fields:
        # 若 items 已存在，就回報真正缺少的明細欄位，避免同時回報籠統的 items。
        if items:
            missing_fields = [field for field in missing_fields if field != "items"]
        raise DraftClarificationRequired(missing_fields)
    if len(set(supplier_ids or [])) != len(supplier_ids or []):
        raise DraftError("supplier_ids 不可重複")
    if any(not isinstance(supplier_id, int) or isinstance(supplier_id, bool) for supplier_id in supplier_ids or []):
        raise DraftError("supplier_ids 必須是整數陣列")
    return normalized_items, list(supplier_ids or [])


def _normalize_currency(value):
    currency = str(value or "TWD").upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise DraftError("currency 必須是 ISO 4217 三碼大寫幣別")
    return currency


def _normalize_needed_by(value):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise DraftError("needed_by 必須是 YYYY-MM-DD 日期") from exc


def _load_products(items):
    products = Product.objects.in_bulk([item["product_id"] for item in items])
    missing = [item["product_id"] for item in items if item["product_id"] not in products]
    inactive = [
        item["product_id"]
        for item in items
        if item["product_id"] in products and not products[item["product_id"]].is_active
    ]
    if missing or inactive:
        raise DraftError("包含不存在或已停用的品項")
    return products


def _load_suppliers(supplier_ids):
    suppliers = Supplier.objects.in_bulk(supplier_ids)
    invalid = [supplier_id for supplier_id in supplier_ids if supplier_id not in suppliers]
    invalid += [
        supplier_id for supplier_id in supplier_ids
        if supplier_id in suppliers
        and (not suppliers[supplier_id].is_active or suppliers[supplier_id].status != "active")
    ]
    if invalid:
        raise DraftError("包含不存在、停用或不可合作的供應商")
    return suppliers


def _replace_items(request, items, products):
    request.items.all().delete()
    PurchaseRequestItem.objects.bulk_create([
        PurchaseRequestItem(
            request=request,
            line_no=index,
            product=products[item["product_id"]],
            description_snapshot=products[item["product_id"]].description or products[item["product_id"]].name,
            specification_snapshot=item.get("specifications") or products[item["product_id"]].specifications,
            quantity=item["quantity"],
            unit_of_measure=item.get("unit_of_measure") or products[item["product_id"]].unit_of_measure,
        )
        for index, item in enumerate(items, start=1)
    ])


def _replace_suppliers(request, supplier_ids):
    rfq, _ = Rfq.objects.get_or_create(
        request=request,
        status=Rfq.Status.DRAFT,
        defaults={"rfq_no": f"RFQ-DRAFT-{uuid4().hex.upper()}", "revision": 1},
    )
    rfq.invited_suppliers.all().delete()
    now = timezone.now()
    RfqSupplier.objects.bulk_create([
        RfqSupplier(rfq=rfq, supplier_id=supplier_id, invited_at=now)
        for supplier_id in supplier_ids
    ])


@transaction.atomic
def _resolve_copied_from_review(user, review_id):
    """複製自已駁回複核案件（人工複核駁回，選項 B 的追蹤欄位）：只有原始申請人本人、
    且該案件確實已駁回、且尚未被複製過，才允許帶入（Robin 2026-09-03 決策：只能複製
    一次，避免變成通用的「複製舊詢價」功能）。"""
    if review_id in (None, ""):
        return None
    try:
        review = ManualReviewQueue.objects.get(pk=review_id)
    except ManualReviewQueue.DoesNotExist as exc:
        raise DraftError("找不到指定的複核案件") from exc
    if review.requester_id != user.id:
        raise DraftError("只能複製自己被駁回的複核案件")
    if review.decision != ManualReviewQueue.Decision.REJECTED:
        raise DraftError("只有已駁回的複核案件可以複製")
    if review.copies.exists():
        raise DraftError("此複核案件已經複製過，請至原案件查看複製後的需求")
    return review


def _resolve_copied_from_request(user, request_id):
    """複製自已駁回採購需求（簽核階段駁回）：同樣只能是本人擁有、已駁回、且尚未被
    複製過的需求。"""
    if request_id in (None, ""):
        return None
    try:
        source_request = PurchaseRequestRepository.owned(user.id).get(pk=request_id)
    except ObjectDoesNotExist as exc:
        raise DraftError("找不到指定的採購需求") from exc
    if source_request.status != PurchaseRequest.Status.REJECTED:
        raise DraftError("只有已駁回的採購需求可以複製")
    if source_request.copies.exists():
        raise DraftError("此採購需求已經複製過，請至原需求查看複製後的草稿")
    return source_request


def create_draft(user, payload):
    _require_permission(user, "purchase_request.create")
    items, supplier_ids = _validate_payload(payload)
    products = _load_products(items)
    _load_suppliers(supplier_ids)
    try:
        record_candidate_confirmation(user, payload.get("candidate_token"), payload)
    except CandidateTokenError as exc:
        raise DraftError(str(exc)) from exc
    copied_from_review = _resolve_copied_from_review(user, payload.get("copied_from_review_id"))
    copied_from_request = _resolve_copied_from_request(user, payload.get("copied_from_request_id"))
    request = PurchaseRequest.objects.create(
        request_no=f"PR-DRAFT-{uuid4().hex.upper()}",
        requester=user,
        purpose=(payload.get("purpose") or "").strip(),
        needed_by=_normalize_needed_by(payload.get("needed_by")),
        currency=_normalize_currency(payload.get("currency")),
        source="manual",
        copied_from_review=copied_from_review,
        copied_from_request=copied_from_request,
    )
    _replace_items(request, items, products)
    _replace_suppliers(request, supplier_ids)
    return PurchaseRequestRepository.owned_drafts(user.id).get(pk=request.pk)


@transaction.atomic
def update_draft(user, pk, payload):
    _require_permission(user, "purchase_request.edit_draft")
    try:
        request = PurchaseRequestRepository.get_owned_draft(pk, user.id, for_update=True)
    except ObjectDoesNotExist as exc:
        raise DraftNotFound("找不到指定的草稿") from exc
    if payload.get("version") != request.version:
        raise DraftVersionConflict("草稿已被更新，請重新載入最新版本")
    if "items" in payload:
        items, _ = _validate_payload(
            {"items": payload["items"], "supplier_ids": [1]}, require_suppliers=False,
        )
        _replace_items(request, items, _load_products(items))
    if "supplier_ids" in payload:
        supplier_ids = list(payload["supplier_ids"] or [])
        if not supplier_ids:
            raise DraftClarificationRequired(["supplier_ids"])
        _load_suppliers(supplier_ids)
        _replace_suppliers(request, supplier_ids)
    if "purpose" in payload:
        request.purpose = str(payload["purpose"] or "").strip()
    if "needed_by" in payload:
        request.needed_by = _normalize_needed_by(payload["needed_by"])
    if "currency" in payload:
        request.currency = _normalize_currency(payload["currency"])
    request.version += 1
    request.save(update_fields=["purpose", "needed_by", "currency", "version"])
    return PurchaseRequestRepository.owned_drafts(user.id).get(pk=request.pk)


def get_owned_draft(user, pk):
    _require_permission(user, "purchase_request.read_own")
    try:
        return PurchaseRequestRepository.owned_drafts(user.id).get(pk=pk)
    except ObjectDoesNotExist as exc:
        raise DraftNotFound("找不到指定的草稿") from exc


def list_owned_drafts(user):
    _require_permission(user, "purchase_request.read_own")
    return PurchaseRequestRepository.owned_drafts(user.id)


def list_owned_requests(user, *, search=None, status=None):
    _require_permission(user, "purchase_request.read_own")
    normalized_search = str(search or "").strip()
    normalized_status = str(status or "").strip()
    if normalized_status and normalized_status not in PurchaseRequest.Status.values:
        raise DraftError("status 不是有效的採購需求狀態")
    return PurchaseRequestRepository.owned(
        user.id,
        search=normalized_search or None,
        status=normalized_status or None,
    )


def get_owned_request(user, pk):
    _require_permission(user, "purchase_request.read_own")
    try:
        return PurchaseRequestRepository.owned(user.id).get(pk=pk)
    except ObjectDoesNotExist as exc:
        raise DraftNotFound("找不到指定的採購需求") from exc


@transaction.atomic
def withdraw_request(user, pk, *, version, reason):
    _require_permission(user, "purchase_request.withdraw")
    normalized_reason = str(reason or "").strip()
    if not normalized_reason:
        raise DraftError("撤回原因為必填")
    try:
        request = PurchaseRequestRepository.get_owned(pk, user.id, for_update=True)
    except ObjectDoesNotExist as exc:
        raise DraftNotFound("找不到指定的採購需求") from exc
    if version != request.version:
        raise DraftVersionConflict("採購需求已被更新，請重新載入最新版本")
    withdrawable = {
        PurchaseRequest.Status.SUBMITTED,
        PurchaseRequest.Status.SOURCING,
        PurchaseRequest.Status.AWARDING,
        PurchaseRequest.Status.APPROVAL,
    }
    if request.status not in withdrawable:
        raise DraftVersionConflict("目前狀態不可撤回")

    active_rfqs = request.rfqs.select_for_update().exclude(
        status__in=[Rfq.Status.CLOSED, Rfq.Status.CANCELLED]
    )
    RfqSupplier.objects.filter(rfq__in=active_rfqs).exclude(
        status=RfqSupplier.Status.CANCELLED
    ).update(status=RfqSupplier.Status.CANCELLED)
    active_rfqs.update(status=Rfq.Status.CANCELLED, version=models.F("version") + 1)

    active_awards = AwardDecision.objects.select_for_update().filter(
        rfq__request=request,
        status__in=[AwardDecision.Status.DRAFT, AwardDecision.Status.SUBMITTED],
    )
    ApprovalCase.objects.select_for_update().filter(
        award__in=active_awards,
        status__in=[ApprovalCase.Status.PENDING, ApprovalCase.Status.IN_PROGRESS],
    ).update(
        status=ApprovalCase.Status.CANCELLED,
        decided_at=timezone.now(),
        version=models.F("version") + 1,
    )
    # award_decisions_submission_time_consistent：非 draft 狀態必須有 submitted_at；
    # 仍在 draft 就被撤回連動取消的得標方案，一併補上取消當下時間，避免違反 CHECK constraint。
    active_awards.update(
        status=AwardDecision.Status.CANCELLED,
        submitted_at=Coalesce(models.F("submitted_at"), Value(timezone.now())),
    )

    request.status = PurchaseRequest.Status.WITHDRAWN
    request.version += 1
    request.save(update_fields=["status", "version"])
    AuditLog.objects.create(
        user=user,
        action_type="purchase_request_withdrawal",
        real_query_summary=f"request_no={request.request_no}; reason={normalized_reason}",
        verification_result="n/a",
    )
    return PurchaseRequestRepository.owned(user.id).get(pk=request.pk)


@transaction.atomic
def delete_draft(user, pk):
    _require_permission(user, "purchase_request.edit_draft")
    try:
        request = PurchaseRequestRepository.get_owned_draft(pk, user.id, for_update=True)
    except ObjectDoesNotExist as exc:
        raise DraftNotFound("找不到指定的草稿") from exc
    request.rfqs.filter(status=Rfq.Status.DRAFT).delete()
    request.delete()


def preview_draft(user, pk, version):
    request = get_owned_draft(user, pk)
    if version != request.version:
        raise DraftVersionConflict("草稿已被更新，請重新載入最新版本")
    rfq = request.rfqs.get(status=Rfq.Status.DRAFT)
    suppliers = []
    for invitation in rfq.invited_suppliers.select_related("supplier").all():
        rows = []
        supplier_total = Decimal("0.00")
        for item in request.items.select_related("product").all():
            price = PurchaseRequestRepository.active_price(
                supplier_id=invitation.supplier_id,
                product_id=item.product_id,
                quantity=item.quantity,
                currency=request.currency,
            )
            if price is None:
                rows.append({
                    "product_id": item.product_id,
                    "product_name": item.product.name,
                    "quantity": str(item.quantity),
                    "unit_of_measure": item.unit_of_measure,
                    "available": False,
                    "message": "目前沒有有效價格，正式邀價時需由供應商回覆",
                })
                continue
            total = (price.unit_price * item.quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            supplier_total += total
            historical_average = PurchaseRequestRepository.historical_average_price(
                supplier_id=invitation.supplier_id,
                product_id=item.product_id,
                currency=request.currency,
            )
            comparison = {"status": "unavailable", "label": "無歷史資料", "deviation_pct": None}
            if historical_average not in (None, 0):
                deviation = ((price.unit_price - historical_average) / historical_average * 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                )
                comparison = {
                    "status": "warning" if abs(deviation) > Decimal("20.00") else "normal",
                    "label": "高於歷史均價" if deviation > 0 else ("低於歷史均價" if deviation < 0 else "接近歷史均價"),
                    "historical_average": f"{historical_average:.2f}",
                    "deviation_pct": f"{deviation:.2f}",
                }
            rows.append({
                "product_id": item.product_id,
                "product_name": item.product.name,
                "quantity": str(item.quantity),
                "unit_of_measure": item.unit_of_measure,
                "available": True,
                "unit_price": f"{price.unit_price:.2f}",
                "total_amount": f"{total:.2f}",
                "currency": request.currency,
                "price_comparison": comparison,
            })
        suppliers.append({
            "supplier_id": invitation.supplier_id,
            "supplier_name": invitation.supplier.name,
            "items": rows,
            "estimated_total": f"{supplier_total:.2f}",
            "currency": request.currency,
        })
    return {
        "request_id": request.id,
        "version": request.version,
        "status": "estimate_only",
        "message": "此為參考試算，尚未提交採購申請或正式邀價",
        "suppliers": suppliers,
    }


@transaction.atomic
def submit_draft(user, pk, *, version, idempotency_key):
    _require_permission(user, "purchase_request.submit")
    if not idempotency_key or not str(idempotency_key).strip():
        raise DraftError("idempotency_key 為必填")
    try:
        request = PurchaseRequestRepository.get_owned(pk, user.id, for_update=True)
    except ObjectDoesNotExist as exc:
        raise DraftNotFound("找不到指定的採購需求") from exc
    if request.idempotency_key == idempotency_key and request.status == PurchaseRequest.Status.SUBMITTED:
        return request
    if request.status != PurchaseRequest.Status.DRAFT:
        raise DraftError("只有草稿可以提交")
    if request.version != version:
        raise DraftVersionConflict("草稿已被更新，請重新試算並確認")
    if not request.items.exists() or not request.rfqs.filter(status=Rfq.Status.DRAFT).exists():
        raise DraftClarificationRequired(["items", "supplier_ids"])
    try:
        request.idempotency_key = str(idempotency_key).strip()
        request.status = PurchaseRequest.Status.SUBMITTED
        request.version += 1
        request.save(update_fields=["idempotency_key", "status", "version"])
    except IntegrityError as exc:
        raise DraftVersionConflict("此提交識別碼已由其他採購需求使用") from exc
    from services.purchase_suggestion_service import mark_request_in_progress

    mark_request_in_progress(request.id)
    return request
