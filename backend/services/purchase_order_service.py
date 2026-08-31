"""Phase 4.1 C5-3：依得標供應商拆分採購單、查詢與發單。"""

from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.procurement.models import PurchaseOrder, PurchaseOrderItem
from repositories.procurement import PurchaseOrderRepository
from services.inventory_balance_service import add_purchase_order_in_transit
from services.rbac_service import get_permission_codes


class PurchaseOrderError(Exception):
    code = "invalid_purchase_order"


class PurchaseOrderNotFound(PurchaseOrderError):
    code = "not_found"


class PurchaseOrderPermissionDenied(PurchaseOrderError):
    code = "permission_denied"


class PurchaseOrderConflict(PurchaseOrderError):
    code = "conflict"


def _audit(user, action_type, purchase_order, result="n/a"):
    AuditLog.objects.create(
        user=user,
        action_type=action_type,
        real_query_summary=f"purchase_order_id={purchase_order.id}",
        verification_result=result,
    )


def _group_award_lines(award):
    lines = list(
        award.lines.select_related(
            "request_item__product",
            "supplier_quote_item__supplier_quote__rfq_supplier__supplier",
        ).order_by("request_item__line_no", "id")
    )
    if not lines:
        raise PurchaseOrderConflict("得標方案沒有可建立採購單的明細")
    grouped = defaultdict(list)
    for line in lines:
        supplier = line.supplier_quote_item.supplier_quote.rfq_supplier.supplier
        grouped[supplier.id].append((supplier, line))
    return grouped


def _expected_signature(grouped):
    return {
        supplier_id: {
            "total": sum((line.amount_snapshot for _, line in rows), Decimal("0.00")),
            "line_ids": {line.id for _, line in rows},
        }
        for supplier_id, rows in grouped.items()
    }


def _validate_existing(existing, grouped):
    expected = _expected_signature(grouped)
    if {order.supplier_id for order in existing} != set(expected):
        raise PurchaseOrderConflict("得標方案已存在不完整的供應商採購單")
    for order in existing:
        signature = expected[order.supplier_id]
        if order.total_amount != signature["total"]:
            raise PurchaseOrderConflict("既有採購單總額與得標快照不一致")
        if {item.award_line_id for item in order.items.all()} != signature["line_ids"]:
            raise PurchaseOrderConflict("既有採購單明細與得標快照不一致")
    return existing


def create_purchase_orders_for_award(award, actor):
    grouped = _group_award_lines(award)
    existing = PurchaseOrderRepository.for_award_for_update(award.id)
    if existing:
        return _validate_existing(existing, grouped)
    created = []
    try:
        for supplier_id in sorted(grouped):
            rows = grouped[supplier_id]
            supplier = rows[0][0]
            purchase_order = PurchaseOrder.objects.create(
                po_no=f"PO-{award.id:06d}-{supplier_id:06d}",
                award=award,
                supplier=supplier,
                currency="TWD",
                total_amount=sum(
                    (line.amount_snapshot for _, line in rows), Decimal("0.00")
                ),
            )
            PurchaseOrderItem.objects.bulk_create(
                [
                    PurchaseOrderItem(
                        purchase_order=purchase_order,
                        award_line=line,
                        line_no=index,
                        product=line.request_item.product,
                        product_name_snapshot=line.request_item.description_snapshot,
                        specification_snapshot=line.request_item.specification_snapshot,
                        ordered_quantity=line.awarded_quantity,
                        unit_price=line.unit_price_snapshot,
                        amount=line.amount_snapshot,
                    )
                    for index, (_, line) in enumerate(rows, 1)
                ]
            )
            _audit(actor, "purchase_order_created", purchase_order)
            created.append(purchase_order)
    except IntegrityError as exc:
        raise PurchaseOrderConflict("採購單已由其他交易建立，請重新整理") from exc
    return created


def list_accessible_purchase_orders(user):
    permissions = get_permission_codes(user)
    can_read_all = bool({"purchase_order.manage", "audit.read"} & permissions)
    if not can_read_all and "purchase_request.read_own" not in permissions:
        raise PurchaseOrderPermissionDenied("沒有讀取採購單的權限")
    return PurchaseOrderRepository.accessible(user_id=user.id, can_read_all=can_read_all)


def get_accessible_purchase_order(user, purchase_order_id):
    try:
        return list_accessible_purchase_orders(user).get(pk=purchase_order_id)
    except PurchaseOrder.DoesNotExist as exc:
        raise PurchaseOrderNotFound("找不到指定的採購單") from exc


@transaction.atomic
def issue_purchase_order(user, purchase_order_id, version):
    if "purchase_order.manage" not in get_permission_codes(user):
        raise PurchaseOrderPermissionDenied("沒有正式發出採購單的權限")
    try:
        version = int(version)
    except (TypeError, ValueError) as exc:
        raise PurchaseOrderError("version 必須是正整數") from exc
    if version <= 0:
        raise PurchaseOrderError("version 必須是正整數")
    try:
        purchase_order = PurchaseOrderRepository.get_for_update(purchase_order_id)
    except ObjectDoesNotExist as exc:
        raise PurchaseOrderNotFound("找不到指定的採購單") from exc
    if purchase_order.status != PurchaseOrder.Status.DRAFT:
        raise PurchaseOrderConflict("只有草稿採購單可以正式發出")
    if purchase_order.version != version:
        raise PurchaseOrderConflict("採購單版本已變更，請重新整理")
    if not purchase_order.items.exists():
        raise PurchaseOrderConflict("採購單沒有可發出的明細")
    add_purchase_order_in_transit(purchase_order)
    purchase_order.status = PurchaseOrder.Status.ISSUED
    purchase_order.issued_at = timezone.now()
    purchase_order.version += 1
    purchase_order.save(update_fields=["status", "issued_at", "version", "updated_at"])
    _audit(user, "purchase_order_issued", purchase_order)
    return PurchaseOrderRepository.get(purchase_order.id)


def serialize_purchase_order(purchase_order):
    return {
        "id": purchase_order.id,
        "po_no": purchase_order.po_no,
        "award_id": purchase_order.award_id,
        "request_id": purchase_order.award.rfq.request_id,
        "request_no": purchase_order.award.rfq.request.request_no,
        "supplier": {
            "id": purchase_order.supplier_id,
            "name": purchase_order.supplier.name,
        },
        "status": purchase_order.status,
        "currency": purchase_order.currency,
        "total_amount": f"{purchase_order.total_amount:.2f}",
        "issued_at": purchase_order.issued_at,
        "version": purchase_order.version,
        "items": [
            {
                "id": item.id,
                "line_no": item.line_no,
                "award_line_id": item.award_line_id,
                "product_id": item.product_id,
                "product_name": item.product_name_snapshot,
                "specifications": item.specification_snapshot,
                "quantity": f"{item.ordered_quantity:.3f}",
                "unit_price": f"{item.unit_price:.2f}",
                "amount": f"{item.amount:.2f}",
            }
            for item in purchase_order.items.all().order_by("line_no")
        ],
    }
