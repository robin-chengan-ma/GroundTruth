from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.procurement.models import (
    ApprovalCase,
    ApprovalPolicy,
    ApprovalStep,
    AwardDecision,
    AwardLine,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    Rfq,
    RfqSupplier,
    SupplierQuote,
    SupplierQuoteItem,
)


def create_award_context(user, supplier, product, *, quantity="5.000"):
    request = PurchaseRequest.objects.create(
        request_no="PR-B3-001", requester=user, purpose="B3 得標測試"
    )
    request_item = PurchaseRequestItem.objects.create(
        request=request,
        line_no=1,
        product=product,
        description_snapshot="辦公椅",
        quantity=Decimal(quantity),
        unit_of_measure="EA",
    )
    rfq = Rfq.objects.create(rfq_no="RFQ-B3-001", request=request)
    invitation = RfqSupplier.objects.create(
        rfq=rfq, supplier=supplier, invited_at=timezone.now(), status="responded"
    )
    quote = SupplierQuote.objects.create(
        quote_no="SQ-B3-001",
        rfq_supplier=invitation,
        status="accepted_for_evaluation",
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("500.00"),
        landed_total_twd=Decimal("500.00"),
        valid_until=timezone.now() + timezone.timedelta(days=30),
    )
    quote_item = SupplierQuoteItem.objects.create(
        supplier_quote=quote,
        request_item=request_item,
        quantity=Decimal(quantity),
        unit_price=Decimal("100.00"),
        subtotal=Decimal("500.00"),
    )
    award = AwardDecision.objects.create(
        rfq=rfq, revision=1, selected_by=user, selection_reason="綜合評選結果"
    )
    return request, request_item, quote_item, award


@pytest.mark.django_db(transaction=True)
def test_submitted_award_requires_each_request_item_quantity_to_be_fully_allocated(user, supplier, product):
    _, request_item, quote_item, award = create_award_context(user, supplier, product)
    AwardLine.objects.create(
        award=award,
        request_item=request_item,
        supplier_quote_item=quote_item,
        awarded_quantity=Decimal("4.000"),
        unit_price_snapshot=Decimal("100.00"),
        amount_snapshot=Decimal("400.00"),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        award.status = "submitted"
        award.submitted_at = timezone.now()
        award.save(update_fields=["status", "submitted_at"])


@pytest.mark.django_db(transaction=True)
def test_submitted_award_accepts_complete_allocation(user, supplier, product):
    _, request_item, quote_item, award = create_award_context(user, supplier, product)
    AwardLine.objects.create(
        award=award,
        request_item=request_item,
        supplier_quote_item=quote_item,
        awarded_quantity=Decimal("5.000"),
        unit_price_snapshot=Decimal("100.00"),
        amount_snapshot=Decimal("500.00"),
    )
    award.status = "submitted"
    award.submitted_at = timezone.now()
    award.save(update_fields=["status", "submitted_at"])

    assert award.status == "submitted"


@pytest.mark.django_db
def test_award_line_rejects_cross_request_quote_item(user, supplier, product):
    _, request_item, _, award = create_award_context(user, supplier, product)
    other_request = PurchaseRequest.objects.create(
        request_no="PR-B3-OTHER", requester=user, purpose="其他需求"
    )
    other_item = PurchaseRequestItem.objects.create(
        request=other_request,
        line_no=1,
        product=product,
        description_snapshot="其他品項",
        quantity=Decimal("1.000"),
        unit_of_measure="EA",
    )
    other_rfq = Rfq.objects.create(rfq_no="RFQ-B3-OTHER", request=other_request)
    invitation = RfqSupplier.objects.create(
        rfq=other_rfq, supplier=supplier, invited_at=timezone.now()
    )
    quote = SupplierQuote.objects.create(
        quote_no="SQ-B3-OTHER",
        rfq_supplier=invitation,
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("100.00"),
        landed_total_twd=Decimal("100.00"),
    )
    other_quote_item = SupplierQuoteItem.objects.create(
        supplier_quote=quote,
        request_item=other_item,
        quantity=Decimal("1.000"),
        unit_price=Decimal("100.00"),
        subtotal=Decimal("100.00"),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        AwardLine.objects.create(
            award=award,
            request_item=request_item,
            supplier_quote_item=other_quote_item,
            awarded_quantity=Decimal("1.000"),
            unit_price_snapshot=Decimal("100.00"),
            amount_snapshot=Decimal("100.00"),
        )


@pytest.mark.django_db
def test_approval_step_claim_fields_must_match_status(user, supplier, product, role_employee):
    request, request_item, quote_item, award = create_award_context(user, supplier, product)
    AwardLine.objects.create(
        award=award,
        request_item=request_item,
        supplier_quote_item=quote_item,
        awarded_quantity=Decimal("5.000"),
        unit_price_snapshot=Decimal("100.00"),
        amount_snapshot=Decimal("500.00"),
    )
    policy = ApprovalPolicy.objects.create(
        name="B3 小額",
        currency="TWD",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("10000.00"),
        active_from=timezone.now(),
    )
    case = ApprovalCase.objects.create(
        award=award,
        policy=policy,
        requester=request.requester,
        policy_snapshot={"name": "B3 小額"},
        total_amount=Decimal("500.00"),
        currency="TWD",
        submitted_at=timezone.now(),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        ApprovalStep.objects.create(
            approval_case=case,
            sequence=1,
            role=role_employee,
            role_snapshot={"role": role_employee.role},
            status="claimed",
        )


@pytest.mark.django_db
def test_purchase_order_preserves_award_line_snapshot(user, supplier, product):
    _, request_item, quote_item, award = create_award_context(user, supplier, product)
    award_line = AwardLine.objects.create(
        award=award,
        request_item=request_item,
        supplier_quote_item=quote_item,
        awarded_quantity=Decimal("5.000"),
        unit_price_snapshot=Decimal("100.00"),
        amount_snapshot=Decimal("500.00"),
    )
    purchase_order = PurchaseOrder.objects.create(
        po_no="PO-B3-001",
        award=award,
        supplier=supplier,
        currency="TWD",
        total_amount=Decimal("500.00"),
    )
    item = PurchaseOrderItem.objects.create(
        purchase_order=purchase_order,
        award_line=award_line,
        line_no=1,
        product=product,
        product_name_snapshot="辦公椅",
        specification_snapshot={"material": "網布"},
        ordered_quantity=Decimal("5.000"),
        unit_price=Decimal("100.00"),
        amount=Decimal("500.00"),
    )

    assert item.product_name_snapshot == "辦公椅"
