"""Phase 4.1 C6-2：品質驗收、合格入庫與單據狀態彙總。"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.erp.models import GoodsReceipt, QualityInspection
from apps.procurement.models import PurchaseOrder
from repositories.erp import GoodsReceiptRepository, QualityInspectionRepository
from services.goods_receipt_service import (
    GoodsReceiptConflict,
    GoodsReceiptError,
    GoodsReceiptNotFound,
    GoodsReceiptPermissionDenied,
)
from services.inspection_variance_service import complete_replacement_line_if_fulfilled
from services.inventory_balance_service import InventoryBalanceConflict, post_accepted_inventory
from services.purchase_receiving_rollup_service import roll_up_purchase_documents
from services.rbac_service import get_permission_codes


def _quantity(value, label):
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise GoodsReceiptError(f"{label}必須是非負數字") from exc
    if not quantity.is_finite() or quantity < 0 or quantity.as_tuple().exponent < -3:
        raise GoodsReceiptError(f"{label}必須是非負且最多三位小數的數字")
    return quantity


def _validate_allocations(receipt, payload_items):
    if not isinstance(payload_items, list) or not payload_items:
        raise GoodsReceiptError("驗收至少需要一筆明細")
    receipt_items = {item.id: item for item in receipt.items.all()}
    if len(payload_items) != len(receipt_items):
        raise GoodsReceiptError("必須一次完成收貨單的所有明細驗收")
    normalized = []
    seen = set()
    for row in payload_items:
        if not isinstance(row, dict):
            raise GoodsReceiptError("驗收明細格式錯誤")
        try:
            receipt_item_id = int(row.get("receipt_item_id"))
        except (TypeError, ValueError) as exc:
            raise GoodsReceiptError("收貨明細編號格式錯誤") from exc
        if receipt_item_id in seen or receipt_item_id not in receipt_items:
            raise GoodsReceiptError("驗收明細重複或不屬於指定收貨單")
        seen.add(receipt_item_id)
        receipt_item = receipt_items[receipt_item_id]
        accepted = _quantity(row.get("accepted_quantity"), "合格數量")
        defective = _quantity(row.get("defective_quantity"), "瑕疵數量")
        rejected = _quantity(row.get("rejected_quantity"), "拒收數量")
        if accepted + defective + rejected != receipt_item.received_quantity:
            raise GoodsReceiptError("合格、瑕疵與拒收數量加總必須等於實收數量")
        defect_details = str(row.get("defect_details") or "").strip()
        if defective > 0 and not defect_details:
            raise GoodsReceiptError("有瑕疵數量時必須填寫瑕疵內容")
        if accepted == receipt_item.received_quantity:
            status = QualityInspection.Status.ACCEPTED
        elif accepted > 0:
            status = QualityInspection.Status.PARTIALLY_ACCEPTED
        else:
            status = QualityInspection.Status.REJECTED
        normalized.append(
            {
                "receipt_item": receipt_item,
                "status": status,
                "accepted_quantity": accepted,
                "defective_quantity": defective,
                "rejected_quantity": rejected,
                "defect_details": defect_details,
                "notes": str(row.get("notes") or "").strip(),
            }
        )
    return normalized


@transaction.atomic
def inspect_goods_receipt(user, receipt_id, payload):
    if "inspection.decide" not in get_permission_codes(user):
        raise GoodsReceiptPermissionDenied("沒有執行品質驗收的權限")
    try:
        version = int(payload.get("version"))
    except (TypeError, ValueError) as exc:
        raise GoodsReceiptError("version 必須是正整數") from exc
    if version <= 0:
        raise GoodsReceiptError("version 必須是正整數")
    try:
        receipt = GoodsReceiptRepository.get_for_update(receipt_id)
    except ObjectDoesNotExist as exc:
        raise GoodsReceiptNotFound("找不到指定的收貨單") from exc
    if receipt.received_by_id == user.id:
        raise GoodsReceiptPermissionDenied("收貨人不得驗收自己記錄的收貨批次")
    if receipt.status != GoodsReceipt.Status.INSPECTING:
        raise GoodsReceiptConflict("只有送驗中的收貨單可以進行品質驗收")
    if receipt.version != version:
        raise GoodsReceiptConflict("收貨單版本已變更，請重新整理")
    allocations = _validate_allocations(receipt, payload.get("items"))
    now = timezone.now()
    try:
        for allocation in allocations:
            inspection = QualityInspectionRepository.create(
                **allocation,
                inspected_by=user,
                inspected_at=now,
            )
            post_accepted_inventory(inspection, user)
            complete_replacement_line_if_fulfilled(inspection, user)
    except (IntegrityError, InventoryBalanceConflict) as exc:
        raise GoodsReceiptConflict("驗收已完成或庫存過帳發生衝突，請重新整理") from exc
    accepted_total = sum((row["accepted_quantity"] for row in allocations), Decimal("0.000"))
    received_total = sum(
        (row["receipt_item"].received_quantity for row in allocations), Decimal("0.000")
    )
    receipt.status = (
        GoodsReceipt.Status.POSTED
        if accepted_total == received_total
        else GoodsReceipt.Status.PARTIALLY_ACCEPTED
        if accepted_total > 0
        else GoodsReceipt.Status.REJECTED
    )
    receipt.version += 1
    receipt.save(update_fields=["status", "version", "updated_at"])
    purchase_order = PurchaseOrder.objects.select_for_update().get(pk=receipt.purchase_order_id)
    roll_up_purchase_documents(purchase_order)
    AuditLog.objects.create(
        user=user,
        action_type="quality_inspection_posted",
        real_query_summary=f"goods_receipt_id={receipt.id}",
        verification_result="n/a",
    )
    return GoodsReceiptRepository.get(receipt.id)
