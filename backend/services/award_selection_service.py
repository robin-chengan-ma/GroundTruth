"""Phase 4.1.6 C5-1：人工選商、逐項／拆量分配與得標方案提交。"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.procurement.models import AwardDecision, AwardLine, PurchaseRequest, Rfq
from repositories.procurement import AwardRepository
from services.approval_case_service import ApprovalWorkflowConflict, create_approval_case_for_award
from services.rbac_service import user_has_permission
from services.rfq_evaluation_service import allocated_item_unit_cost_twd, evaluate_rfq

AMOUNT_QUANTUM = Decimal("0.01")


class AwardSelectionError(Exception):
    code = "invalid_award"


class AwardSelectionNotFound(AwardSelectionError):
    code = "not_found"


class AwardSelectionPermissionDenied(AwardSelectionError):
    code = "permission_denied"


class AwardSelectionConflict(AwardSelectionError):
    code = "conflict"


class AwardSelectionReasonRequired(AwardSelectionError):
    code = "reason_required"


def _require_permission(user):
    if not user_has_permission(user, "award.recommend"):
        raise AwardSelectionPermissionDenied("沒有建立或提交得標方案的權限")


def _quantity(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AwardSelectionError("得標數量必須是有效數字") from exc
    if result <= 0 or result.as_tuple().exponent < -3:
        raise AwardSelectionError("得標數量必須大於 0，且最多三位小數")
    return result


def _evaluation_maps(user, rfq):
    result = evaluate_rfq(user, rfq.id, enforce_permission=False)
    candidates = {}
    recommendations = {}
    for section in result["items"]:
        recommendations[section["request_item_id"]] = set(section["recommended_quote_ids"])
        for row in section["quotes"]:
            candidates[row["quote_item_id"]] = row
    return candidates, recommendations


def _validated_lines(user, rfq, line_payloads, selection_reason):
    if not isinstance(line_payloads, list) or not line_payloads:
        raise AwardSelectionError("得標方案至少需要一筆分配明細")
    candidates, recommendations = _evaluation_maps(user, rfq)
    seen_quote_items = set()
    prepared = []
    chose_non_recommended = False
    for payload in line_payloads:
        try:
            request_item_id = int(payload["request_item_id"])
            quote_item_id = int(payload["supplier_quote_item_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AwardSelectionError("每筆得標明細都必須提供需求品項與報價品項") from exc
        if quote_item_id in seen_quote_items:
            raise AwardSelectionError("同一報價品項不可重複分配")
        seen_quote_items.add(quote_item_id)
        row = candidates.get(quote_item_id)
        if row is None:
            raise AwardSelectionConflict("報價已過期、不是目前有效版本，或不屬於此 RFQ")
        try:
            quote_item = AwardRepository.quote_item_for_award(quote_item_id)
        except ObjectDoesNotExist as exc:
            raise AwardSelectionConflict("報價品項已不存在，請重新整理評選結果") from exc
        if quote_item.request_item_id != request_item_id:
            raise AwardSelectionConflict("報價品項與需求品項不相符")
        if not row["eligible"]:
            raise AwardSelectionConflict("必要條件未通過且尚未取得例外核准")
        if row["quote_id"] not in recommendations.get(request_item_id, set()):
            chose_non_recommended = True
        quantity = _quantity(payload.get("quantity"))
        unit_cost = allocated_item_unit_cost_twd(quote_item.supplier_quote, quote_item)
        prepared.append({
            "request_item": quote_item.request_item,
            "quote_item": quote_item,
            "quantity": quantity,
            "unit_cost": unit_cost,
            "amount": (unit_cost * quantity).quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP),
            "reason": str(payload.get("reason") or "").strip(),
        })
    if chose_non_recommended and not str(selection_reason or "").strip():
        raise AwardSelectionReasonRequired("選擇非系統推薦報價時必須填寫選商理由")
    return prepared


def _replace_lines(award, prepared):
    award.lines.all().delete()
    AwardLine.objects.bulk_create([
        AwardLine(
            award=award,
            request_item=row["request_item"],
            supplier_quote_item=row["quote_item"],
            awarded_quantity=row["quantity"],
            unit_price_snapshot=row["unit_cost"],
            amount_snapshot=row["amount"],
            reason=row["reason"],
        )
        for row in prepared
    ])


@transaction.atomic
def create_award_draft(user, payload):
    _require_permission(user)
    try:
        rfq = AwardRepository.rfq_for_award(int(payload.get("rfq_id")))
    except (ObjectDoesNotExist, TypeError, ValueError) as exc:
        raise AwardSelectionNotFound("找不到指定的 RFQ") from exc
    if rfq.status != Rfq.Status.EVALUATING or rfq.request.status != PurchaseRequest.Status.AWARDING:
        raise AwardSelectionConflict("只有評選中的 RFQ 可以建立得標方案")
    if AwardDecision.objects.filter(rfq=rfq, status__in=["draft", "submitted", "approved"]).exists():
        raise AwardSelectionConflict("此 RFQ 已有進行中的得標方案")
    reason = str(payload.get("selection_reason") or "").strip()
    prepared = _validated_lines(user, rfq, payload.get("lines"), reason)
    revision = (AwardDecision.objects.filter(rfq=rfq).aggregate(value=Max("revision"))["value"] or 0) + 1
    try:
        with transaction.atomic():
            award = AwardDecision.objects.create(
                rfq=rfq,
                revision=revision,
                selected_by=user,
                selection_reason=reason,
            )
    except IntegrityError as exc:
        raise AwardSelectionConflict("此 RFQ 已由其他人建立得標方案，請重新整理") from exc
    _replace_lines(award, prepared)
    return AwardRepository.get(award.id)


@transaction.atomic
def update_award_draft(user, award_id, payload):
    _require_permission(user)
    try:
        award = AwardRepository.get_for_update(award_id)
    except ObjectDoesNotExist as exc:
        raise AwardSelectionNotFound("找不到指定的得標方案") from exc
    if award.status != AwardDecision.Status.DRAFT:
        raise AwardSelectionConflict("只有草稿得標方案可以修改")
    reason = str(payload.get("selection_reason") or "").strip()
    prepared = _validated_lines(user, award.rfq, payload.get("lines"), reason)
    award.selection_reason = reason
    award.save(update_fields=["selection_reason"])
    _replace_lines(award, prepared)
    return AwardRepository.get(award.id)


def _ensure_complete_allocation(award):
    allocated = {}
    for line in award.lines.all():
        allocated[line.request_item_id] = allocated.get(line.request_item_id, Decimal(0)) + line.awarded_quantity
    for item in award.rfq.request.items.all():
        if allocated.get(item.id, Decimal(0)) != item.quantity:
            raise AwardSelectionConflict(f"品項「{item.description_snapshot}」的得標數量尚未完整分配")


@transaction.atomic
def submit_award(user, award_id):
    _require_permission(user)
    try:
        award = AwardRepository.get_for_update(award_id)
    except ObjectDoesNotExist as exc:
        raise AwardSelectionNotFound("找不到指定的得標方案") from exc
    if award.status != AwardDecision.Status.DRAFT:
        raise AwardSelectionConflict("只有草稿得標方案可以提交")
    payload = [{
        "request_item_id": line.request_item_id,
        "supplier_quote_item_id": line.supplier_quote_item_id,
        "quantity": line.awarded_quantity,
        "reason": line.reason,
    } for line in award.lines.all()]
    _validated_lines(user, award.rfq, payload, award.selection_reason)
    _ensure_complete_allocation(award)
    now = timezone.now()
    award.status = AwardDecision.Status.SUBMITTED
    award.submitted_at = now
    award.save(update_fields=["status", "submitted_at"])
    request = award.rfq.request
    request.status = PurchaseRequest.Status.APPROVAL
    request.version += 1
    request.save(update_fields=["status", "version"])
    try:
        create_approval_case_for_award(award)
    except ApprovalWorkflowConflict as exc:
        raise AwardSelectionConflict(str(exc)) from exc
    return AwardRepository.get(award.id)


def serialize_award(award):
    lines = list(award.lines.all())
    try:
        approval_case_id = award.approval_case.id
    except ObjectDoesNotExist:
        approval_case_id = None
    return {
        "id": award.id,
        "rfq_id": award.rfq_id,
        "revision": award.revision,
        "status": award.status,
        "selection_reason": award.selection_reason,
        "selected_by": {"id": award.selected_by_id, "name": award.selected_by.name},
        "submitted_at": award.submitted_at,
        "approval_case_id": approval_case_id,
        "total_amount_twd": f"{sum((line.amount_snapshot for line in lines), Decimal(0)):.2f}",
        "lines": [{
            "id": line.id,
            "request_item_id": line.request_item_id,
            "supplier_quote_item_id": line.supplier_quote_item_id,
            "supplier_id": line.supplier_quote_item.supplier_quote.rfq_supplier.supplier_id,
            "supplier_name": line.supplier_quote_item.supplier_quote.rfq_supplier.supplier.name,
            "quantity": f"{line.awarded_quantity:.3f}",
            "unit_cost_twd": f"{line.unit_price_snapshot:.2f}",
            "amount_twd": f"{line.amount_snapshot:.2f}",
            "reason": line.reason,
        } for line in lines],
    }
