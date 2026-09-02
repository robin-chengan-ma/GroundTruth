"""Phase 4.1 C6-3B：驗收差異案件草稿、送出與查詢。"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.erp.models import InspectionVarianceCase, InspectionVarianceLine
from repositories.erp import InspectionVarianceRepository, QualityInspectionRepository
from repositories.procurement import PurchaseOrderRepository
from services.rbac_service import get_permission_codes


class InspectionVarianceError(Exception):
    code = "invalid_inspection_variance"


class InspectionVarianceNotFound(InspectionVarianceError):
    code = "not_found"


class InspectionVariancePermissionDenied(InspectionVarianceError):
    code = "permission_denied"


class InspectionVarianceConflict(InspectionVarianceError):
    code = "conflict"


def _require_manage(user):
    if "purchase_order.manage" not in get_permission_codes(user):
        raise InspectionVariancePermissionDenied("沒有管理驗收差異案件的權限")


def _require_read(user):
    readable = {
        "purchase_order.manage",
        "receipt.record",
        "inspection.decide",
        "audit.read",
    }
    if not (readable & get_permission_codes(user)):
        raise InspectionVariancePermissionDenied("沒有讀取驗收差異案件的權限")


def _version(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise InspectionVarianceError("version 必須是正整數") from exc
    if parsed <= 0:
        raise InspectionVarianceError("version 必須是正整數")
    return parsed


def _positive_quantity(value):
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InspectionVarianceError("處理數量必須是大於 0 的數字") from exc
    if not quantity.is_finite() or quantity <= 0 or quantity.as_tuple().exponent < -3:
        raise InspectionVarianceError("處理數量必須大於 0 且最多三位小數")
    return quantity


def _normalize_lines(payload_lines, variance_quantity):
    if not isinstance(payload_lines, list) or not payload_lines:
        raise InspectionVarianceError("差異案件至少需要一筆處理明細")
    valid_actions = set(InspectionVarianceLine.ActionType.values)
    normalized = []
    total = Decimal("0.000")
    for row in payload_lines:
        if not isinstance(row, dict) or row.get("action_type") not in valid_actions:
            raise InspectionVarianceError("處理類型必須是 replacement、return、credit 或 waive")
        reason = str(row.get("reason") or "").strip()
        if not reason:
            raise InspectionVarianceError("每筆處理明細都必須填寫理由")
        quantity = _positive_quantity(row.get("quantity"))
        total += quantity
        normalized.append(
            {"action_type": row["action_type"], "quantity": quantity, "reason": reason}
        )
    if total > variance_quantity:
        raise InspectionVarianceError("處理明細總數不得超過驗收差異數量")
    return normalized


def _audit(user, action_type, variance_case):
    AuditLog.objects.create(
        user=user,
        action_type=action_type,
        real_query_summary=f"inspection_variance_case_id={variance_case.id}",
        verification_result="n/a",
    )


@transaction.atomic
def create_variance_draft(user, payload):
    _require_manage(user)
    try:
        inspection_id = int(payload.get("quality_inspection_id"))
        inspection = QualityInspectionRepository.get(inspection_id)
    except (TypeError, ValueError):
        raise InspectionVarianceError("品質驗收編號格式錯誤") from None
    except ObjectDoesNotExist as exc:
        raise InspectionVarianceNotFound("找不到指定的品質驗收") from exc
    variance_quantity = inspection.defective_quantity + inspection.rejected_quantity
    if variance_quantity <= 0:
        raise InspectionVarianceError("只有瑕疵或拒收數量才能建立差異案件")
    lines = _normalize_lines(payload.get("lines"), variance_quantity)
    try:
        variance_case = InspectionVarianceRepository.create_case(
            quality_inspection=inspection, created_by=user
        )
        for line in lines:
            InspectionVarianceRepository.create_line(variance_case=variance_case, **line)
    except IntegrityError as exc:
        raise InspectionVarianceConflict("這筆驗收已建立差異案件") from exc
    _audit(user, "inspection_variance_created", variance_case)
    return InspectionVarianceRepository.get(variance_case.id)


def list_variances(user, *, search=None, status=None):
    _require_read(user)
    return InspectionVarianceRepository.all(search=search, status=status)


def get_variance(user, variance_id):
    _require_read(user)
    try:
        return InspectionVarianceRepository.get(variance_id)
    except ObjectDoesNotExist as exc:
        raise InspectionVarianceNotFound("找不到指定的差異案件") from exc


@transaction.atomic
def update_variance_draft(user, variance_id, payload):
    _require_manage(user)
    try:
        variance_case = InspectionVarianceRepository.get_for_update(variance_id)
    except ObjectDoesNotExist as exc:
        raise InspectionVarianceNotFound("找不到指定的差異案件") from exc
    if variance_case.status != InspectionVarianceCase.Status.DRAFT:
        raise InspectionVarianceConflict("只有草稿差異案件可以修改")
    if variance_case.version != _version(payload.get("version")):
        raise InspectionVarianceConflict("差異案件版本已變更，請重新整理")
    inspection = variance_case.quality_inspection
    lines = _normalize_lines(
        payload.get("lines"), inspection.defective_quantity + inspection.rejected_quantity
    )
    InspectionVarianceRepository.delete_lines(variance_case)
    for line in lines:
        InspectionVarianceRepository.create_line(variance_case=variance_case, **line)
    variance_case.version += 1
    variance_case.save(update_fields=["version", "updated_at"])
    _audit(user, "inspection_variance_updated", variance_case)
    return InspectionVarianceRepository.get(variance_case.id)


@transaction.atomic
def delete_variance_draft(user, variance_id, version):
    _require_manage(user)
    try:
        variance_case = InspectionVarianceRepository.get_for_update(variance_id)
    except ObjectDoesNotExist as exc:
        raise InspectionVarianceNotFound("找不到指定的差異案件") from exc
    if variance_case.status != InspectionVarianceCase.Status.DRAFT:
        raise InspectionVarianceConflict("只有草稿差異案件可以刪除")
    if variance_case.version != _version(version):
        raise InspectionVarianceConflict("差異案件版本已變更，請重新整理")
    case_id = variance_case.id
    InspectionVarianceRepository.delete_lines(variance_case)
    variance_case.delete()
    AuditLog.objects.create(
        user=user,
        action_type="inspection_variance_deleted",
        real_query_summary=f"inspection_variance_case_id={case_id}",
        verification_result="n/a",
    )


@transaction.atomic
def submit_variance(user, variance_id, version):
    _require_manage(user)
    try:
        variance_case = InspectionVarianceRepository.get_for_update(variance_id)
    except ObjectDoesNotExist as exc:
        raise InspectionVarianceNotFound("找不到指定的差異案件") from exc
    if variance_case.status != InspectionVarianceCase.Status.DRAFT:
        raise InspectionVarianceConflict("只有草稿差異案件可以送出")
    if variance_case.version != _version(version):
        raise InspectionVarianceConflict("差異案件版本已變更，請重新整理")
    expected = (
        variance_case.quality_inspection.defective_quantity
        + variance_case.quality_inspection.rejected_quantity
    )
    allocated = sum(
        (line.quantity for line in variance_case.lines.all()), Decimal("0.000")
    )
    if allocated != expected:
        raise InspectionVarianceError("送出時處理明細總數必須等於驗收差異數量")
    variance_case.status = InspectionVarianceCase.Status.OPEN
    variance_case.submitted_by = user
    variance_case.submitted_at = timezone.now()
    variance_case.version += 1
    try:
        variance_case.save(
            update_fields=["status", "submitted_by", "submitted_at", "version", "updated_at"]
        )
    except IntegrityError as exc:
        raise InspectionVarianceConflict("差異案件送出發生衝突，請重新整理") from exc
    _audit(user, "inspection_variance_submitted", variance_case)
    return InspectionVarianceRepository.get(variance_case.id)


@transaction.atomic
def complete_variance_line(user, variance_id, line_id, version):
    _require_manage(user)
    try:
        variance_case = InspectionVarianceRepository.get_for_update(variance_id)
        line = InspectionVarianceRepository.get_line_for_update(variance_id, line_id)
    except ObjectDoesNotExist as exc:
        raise InspectionVarianceNotFound("找不到指定的差異案件或處理明細") from exc
    if variance_case.status != InspectionVarianceCase.Status.OPEN:
        raise InspectionVarianceConflict("只有處理中的差異案件可以完成明細")
    if variance_case.version != _version(version):
        raise InspectionVarianceConflict("差異案件版本已變更，請重新整理")
    if line.status != InspectionVarianceLine.Status.PENDING:
        raise InspectionVarianceConflict("只有待處理明細可以完成")
    if line.action_type == InspectionVarianceLine.ActionType.REPLACEMENT:
        raise InspectionVarianceConflict("補交明細必須由替換品驗收合格後自動完成")
    now = timezone.now()
    line.status = InspectionVarianceLine.Status.COMPLETED
    line.completed_by = user
    line.completed_at = now
    try:
        line.save(update_fields=["status", "completed_by", "completed_at"])
    except IntegrityError as exc:
        raise InspectionVarianceConflict("差異明細處理發生衝突，請重新整理") from exc
    variance_case.version += 1
    variance_case.save(update_fields=["version", "updated_at"])
    _audit(user, "inspection_variance_line_completed", variance_case)
    return InspectionVarianceRepository.get(variance_case.id)


def complete_replacement_line_if_fulfilled(inspection, user):
    line_id = inspection.receipt_item.replacement_variance_line_id
    if line_id is None:
        return
    line = InspectionVarianceRepository.get_line_for_update(
        inspection.receipt_item.replacement_variance_line.variance_case_id, line_id
    )
    if line.status != InspectionVarianceLine.Status.PENDING:
        return
    accepted = InspectionVarianceRepository.accepted_replacement_quantity(line.id)
    if accepted < line.quantity:
        return
    variance_case = InspectionVarianceRepository.get_for_update(line.variance_case_id)
    line.status = InspectionVarianceLine.Status.COMPLETED
    line.completed_by = user
    line.completed_at = timezone.now()
    line.save(update_fields=["status", "completed_by", "completed_at"])
    variance_case.version += 1
    variance_case.save(update_fields=["version", "updated_at"])
    _audit(user, "inspection_variance_replacement_completed", variance_case)


@transaction.atomic
def close_variance(user, variance_id, version):
    _require_manage(user)
    try:
        variance_case = InspectionVarianceRepository.get_for_update(variance_id)
    except ObjectDoesNotExist as exc:
        raise InspectionVarianceNotFound("找不到指定的差異案件") from exc
    if variance_case.status != InspectionVarianceCase.Status.OPEN:
        raise InspectionVarianceConflict("只有處理中的差異案件可以結案")
    if variance_case.version != _version(version):
        raise InspectionVarianceConflict("差異案件版本已變更，請重新整理")
    if variance_case.lines.exclude(
        status=InspectionVarianceLine.Status.COMPLETED
    ).exists():
        raise InspectionVarianceConflict("所有差異處理明細完成後才能結案")
    variance_case.status = InspectionVarianceCase.Status.CLOSED
    variance_case.closed_by = user
    variance_case.closed_at = timezone.now()
    variance_case.version += 1
    try:
        variance_case.save(
            update_fields=["status", "closed_by", "closed_at", "version", "updated_at"]
        )
    except IntegrityError as exc:
        raise InspectionVarianceConflict("差異案件結案發生衝突，請重新整理") from exc
    purchase_order = PurchaseOrderRepository.get_for_update(
        variance_case.quality_inspection.receipt_item.receipt.purchase_order_id
    )
    from services.purchase_receiving_rollup_service import roll_up_purchase_documents

    roll_up_purchase_documents(purchase_order)
    _audit(user, "inspection_variance_closed", variance_case)
    return InspectionVarianceRepository.get(variance_case.id)


def serialize_variance(variance_case):
    inspection = variance_case.quality_inspection
    receipt_item = inspection.receipt_item
    purchase_order = receipt_item.receipt.purchase_order
    return {
        "id": variance_case.id,
        "quality_inspection_id": inspection.id,
        "goods_receipt_id": receipt_item.receipt_id,
        "purchase_order_id": purchase_order.id,
        "product": {
            "id": receipt_item.purchase_order_item.product_id,
            "name": receipt_item.purchase_order_item.product_name_snapshot,
        },
        "supplier": {"id": purchase_order.supplier_id, "name": purchase_order.supplier.name},
        "variance_quantity": f"{inspection.defective_quantity + inspection.rejected_quantity:.3f}",
        "status": variance_case.status,
        "version": variance_case.version,
        "created_by": {"id": variance_case.created_by_id, "name": variance_case.created_by.name},
        "submitted_by": (
            {"id": variance_case.submitted_by_id, "name": variance_case.submitted_by.name}
            if variance_case.submitted_by_id
            else None
        ),
        "submitted_at": variance_case.submitted_at,
        "closed_by": (
            {"id": variance_case.closed_by_id, "name": variance_case.closed_by.name}
            if variance_case.closed_by_id
            else None
        ),
        "closed_at": variance_case.closed_at,
        "lines": [
            {
                "id": line.id,
                "action_type": line.action_type,
                "quantity": f"{line.quantity:.3f}",
                "status": line.status,
                "reason": line.reason,
                "completed_by": (
                    {"id": line.completed_by_id, "name": line.completed_by.name}
                    if line.completed_by_id
                    else None
                ),
                "completed_at": line.completed_at,
            }
            for line in variance_case.lines.all().order_by("id")
        ],
    }
