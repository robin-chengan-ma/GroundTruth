"""Phase 4.1 庫存查詢快照的 transaction 內更新邏輯。"""

from collections import defaultdict
from decimal import Decimal

from apps.erp.models import InventoryMovement
from repositories.erp import InventoryBalanceRepository, InventoryMovementRepository


class InventoryBalanceConflict(Exception):
    pass


def _quantities_by_product(items, quantity_field):
    quantities = defaultdict(lambda: Decimal("0.000"))
    for item in items:
        product_id = item.product_id
        quantities[product_id] += getattr(item, quantity_field)
    return quantities


def add_purchase_order_in_transit(purchase_order):
    quantities = _quantities_by_product(purchase_order.items.all(), "ordered_quantity")
    for product_id in sorted(quantities):
        balance = InventoryBalanceRepository.get_or_create_for_update(product_id)
        balance.in_transit_quantity += quantities[product_id]
        balance.version += 1
        balance.save(update_fields=["in_transit_quantity", "version", "updated_at"])


def remove_receipt_in_transit(receipt):
    quantities = defaultdict(lambda: Decimal("0.000"))
    for receipt_item in receipt.items.all():
        if receipt_item.replacement_variance_line_id is not None:
            continue
        quantities[receipt_item.purchase_order_item.product_id] += receipt_item.received_quantity
    for product_id in sorted(quantities):
        balance = InventoryBalanceRepository.get_or_create_for_update(product_id)
        if balance.in_transit_quantity < quantities[product_id]:
            raise InventoryBalanceConflict("在途數量不足，請先核對採購單與庫存快照")
        balance.in_transit_quantity -= quantities[product_id]
        balance.version += 1
        balance.save(update_fields=["in_transit_quantity", "version", "updated_at"])


def post_accepted_inventory(inspection, user):
    quantity = inspection.accepted_quantity
    if quantity <= 0:
        return None
    product_id = inspection.receipt_item.purchase_order_item.product_id
    if product_id is None:
        raise InventoryBalanceConflict("採購單明細沒有可入庫的品項主檔")
    balance = InventoryBalanceRepository.get_or_create_for_update(product_id)
    movement = InventoryMovementRepository.create(
        product_id=product_id,
        movement_type=InventoryMovement.MovementType.RECEIPT_ACCEPT,
        quantity_delta=quantity,
        reference_type="quality_inspection",
        reference_id=inspection.id,
        affects_balance=True,
        reason="品質驗收合格入庫",
        posted_by=user,
    )
    balance.on_hand_quantity += quantity
    balance.version += 1
    balance.save(update_fields=["on_hand_quantity", "version", "updated_at"])
    from services.purchase_suggestion_service import create_if_below_threshold

    create_if_below_threshold(movement, balance)
    return movement
