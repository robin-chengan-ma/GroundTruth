from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.erp.models import (
    GoodsReceipt,
    GoodsReceiptItem,
    InventoryBalance,
    InventoryMovement,
    QualityInspection,
)
from apps.procurement.models import (
    AwardDecision,
    AwardLine,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    Quote,
    Rfq,
    RfqSupplier,
    SupplierQuote,
    SupplierQuoteItem,
)


def create_purchase_order(user, supplier, product, *, suffix="001", quantity="5.000"):
    request = PurchaseRequest.objects.create(
        request_no=f"PR-B4-{suffix}", requester=user, purpose="B4 收貨測試"
    )
    request_item = PurchaseRequestItem.objects.create(
        request=request,
        line_no=1,
        product=product,
        description_snapshot="辦公椅",
        quantity=Decimal(quantity),
        unit_of_measure="EA",
    )
    rfq = Rfq.objects.create(rfq_no=f"RFQ-B4-{suffix}", request=request)
    invitation = RfqSupplier.objects.create(
        rfq=rfq, supplier=supplier, invited_at=timezone.now(), status="responded"
    )
    quote = SupplierQuote.objects.create(
        quote_no=f"SQ-B4-{suffix}",
        rfq_supplier=invitation,
        status="accepted_for_evaluation",
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("500.00"),
        landed_total_twd=Decimal("500.00"),
    )
    quote_item = SupplierQuoteItem.objects.create(
        supplier_quote=quote,
        request_item=request_item,
        quantity=Decimal(quantity),
        unit_price=Decimal("100.00"),
        subtotal=Decimal("500.00"),
    )
    award = AwardDecision.objects.create(
        rfq=rfq, selected_by=user, selection_reason="B4 測試選商"
    )
    award_line = AwardLine.objects.create(
        award=award,
        request_item=request_item,
        supplier_quote_item=quote_item,
        awarded_quantity=Decimal(quantity),
        unit_price_snapshot=Decimal("100.00"),
        amount_snapshot=Decimal("500.00"),
    )
    purchase_order = PurchaseOrder.objects.create(
        po_no=f"PO-B4-{suffix}",
        award=award,
        supplier=supplier,
        status="issued",
        currency="TWD",
        total_amount=Decimal("500.00"),
        issued_at=timezone.now(),
    )
    purchase_order_item = PurchaseOrderItem.objects.create(
        purchase_order=purchase_order,
        award_line=award_line,
        line_no=1,
        product=product,
        product_name_snapshot="辦公椅",
        ordered_quantity=Decimal(quantity),
        unit_price=Decimal("100.00"),
        amount=Decimal("500.00"),
    )
    return purchase_order, purchase_order_item


@pytest.mark.django_db
def test_receipt_item_rejects_cumulative_quantity_above_purchase_order(user, supplier, product):
    purchase_order, purchase_order_item = create_purchase_order(user, supplier, product)
    first_receipt = GoodsReceipt.objects.create(
        receipt_no="GR-B4-001", purchase_order=purchase_order, received_by=user
    )
    GoodsReceiptItem.objects.create(
        receipt=first_receipt,
        purchase_order_item=purchase_order_item,
        received_quantity=Decimal("3.000"),
    )
    second_receipt = GoodsReceipt.objects.create(
        receipt_no="GR-B4-002", purchase_order=purchase_order, received_by=user
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        GoodsReceiptItem.objects.create(
            receipt=second_receipt,
            purchase_order_item=purchase_order_item,
            received_quantity=Decimal("2.001"),
        )


@pytest.mark.django_db
def test_receipt_item_must_belong_to_receipts_purchase_order(user, supplier, product):
    purchase_order, _ = create_purchase_order(user, supplier, product, suffix="REL-A")
    _, other_item = create_purchase_order(user, supplier, product, suffix="REL-B")
    receipt = GoodsReceipt.objects.create(
        receipt_no="GR-B4-REL", purchase_order=purchase_order, received_by=user
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        GoodsReceiptItem.objects.create(
            receipt=receipt,
            purchase_order_item=other_item,
            received_quantity=Decimal("1.000"),
        )


@pytest.mark.django_db
def test_inspection_quantities_must_equal_received_quantity(user, supplier, product):
    purchase_order, purchase_order_item = create_purchase_order(user, supplier, product)
    receipt = GoodsReceipt.objects.create(
        receipt_no="GR-B4-INSPECT", purchase_order=purchase_order, received_by=user
    )
    receipt_item = GoodsReceiptItem.objects.create(
        receipt=receipt,
        purchase_order_item=purchase_order_item,
        received_quantity=Decimal("5.000"),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        QualityInspection.objects.create(
            receipt_item=receipt_item,
            status="partially_accepted",
            accepted_quantity=Decimal("3.000"),
            defective_quantity=Decimal("1.000"),
            rejected_quantity=Decimal("0.000"),
            defect_details="椅背刮傷",
            inspected_by=user,
            inspected_at=timezone.now(),
        )


@pytest.mark.django_db
def test_receipt_accept_movement_must_match_inspection_accepted_quantity(user, supplier, product):
    purchase_order, purchase_order_item = create_purchase_order(user, supplier, product)
    receipt = GoodsReceipt.objects.create(
        receipt_no="GR-B4-MOVE", purchase_order=purchase_order, received_by=user
    )
    receipt_item = GoodsReceiptItem.objects.create(
        receipt=receipt,
        purchase_order_item=purchase_order_item,
        received_quantity=Decimal("5.000"),
    )
    inspection = QualityInspection.objects.create(
        receipt_item=receipt_item,
        status="partially_accepted",
        accepted_quantity=Decimal("3.000"),
        defective_quantity=Decimal("1.000"),
        rejected_quantity=Decimal("1.000"),
        defect_details="一件刮傷",
        inspected_by=user,
        inspected_at=timezone.now(),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        InventoryMovement.objects.create(
            product=product,
            movement_type="receipt_accept",
            quantity_delta=Decimal("4.000"),
            reference_type="quality_inspection",
            reference_id=inspection.id,
            reason="驗收合格入庫",
            posted_by=user,
        )


@pytest.mark.django_db
def test_inventory_movement_is_append_only(user, product):
    movement = InventoryMovement.objects.create(
        product=product,
        movement_type="adjustment_in",
        quantity_delta=Decimal("1.000"),
        reference_type="manual_adjustment",
        reference_id=1,
        reason="盤點更正",
        posted_by=user,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        movement.reason = "覆寫歷史"
        movement.save(update_fields=["reason"])

    with pytest.raises(IntegrityError), transaction.atomic():
        movement.delete()


@pytest.mark.django_db
def test_inventory_balance_quantities_cannot_be_negative(product):
    with pytest.raises(IntegrityError), transaction.atomic():
        InventoryBalance.objects.create(
            product=product,
            on_hand_quantity=Decimal("-0.001"),
        )


@pytest.mark.django_db
def test_legacy_assumed_receipt_allows_missing_receiving_and_inspection_actors(
    user, supplier, product
):
    purchase_order, purchase_order_item = create_purchase_order(
        user, supplier, product, suffix="LEGACY-ACTOR", quantity="2.000"
    )
    legacy_quote = Quote.objects.create(
        user=user,
        supplier=supplier,
        product=product,
        quantity=2,
        price=Decimal("100.00"),
        total_amount=Decimal("200.00"),
        currency="TWD",
        status="approved",
    )
    receipt = GoodsReceipt.objects.create(
        receipt_no="GR-B4-LEGACY-ACTOR",
        purchase_order=purchase_order,
        status="posted",
        received_by=None,
        received_at=timezone.now(),
        legacy_quote=legacy_quote,
    )
    receipt_item = GoodsReceiptItem.objects.create(
        receipt=receipt,
        purchase_order_item=purchase_order_item,
        received_quantity=Decimal("2.000"),
    )

    inspection = QualityInspection.objects.create(
        receipt_item=receipt_item,
        status="accepted",
        accepted_quantity=Decimal("2.000"),
        inspected_by=None,
        inspected_at=timezone.now(),
        notes="legacy migration assumed receipt",
    )

    assert inspection.inspected_by_id is None


@pytest.mark.django_db
def test_nonlegacy_receipt_rejects_missing_receiving_actor(user, supplier, product):
    purchase_order, _ = create_purchase_order(
        user, supplier, product, suffix="NO-ACTOR", quantity="1.000"
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        GoodsReceipt.objects.create(
            receipt_no="GR-B4-NO-ACTOR",
            purchase_order=purchase_order,
            received_by=None,
        )
