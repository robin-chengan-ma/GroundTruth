from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.procurement.models import (
    PurchaseRequest,
    PurchaseRequestItem,
    QuoteRequirementResult,
    RequestItemRequirement,
    Rfq,
    RfqScoringCriterion,
    RfqSupplier,
    SupplierQuote,
    SupplierQuoteItem,
    SupplierQuoteScore,
)


def create_quote_context(user, supplier, product):
    request = PurchaseRequest.objects.create(
        request_no="PR-B2-001",
        requester=user,
        purpose="B2 報價測試",
    )
    item = PurchaseRequestItem.objects.create(
        request=request,
        line_no=1,
        product=product,
        description_snapshot="辦公椅",
        quantity=Decimal("5.000"),
        unit_of_measure="EA",
    )
    rfq = Rfq.objects.create(rfq_no="RFQ-B2-001", request=request)
    invitation = RfqSupplier.objects.create(
        rfq=rfq,
        supplier=supplier,
        invited_at=timezone.now(),
    )
    return item, rfq, invitation


@pytest.mark.django_db
def test_supplier_quote_supports_multiple_versions_and_only_one_active(user, supplier, product):
    _, _, invitation = create_quote_context(user, supplier, product)
    first = SupplierQuote.objects.create(
        quote_no="SQ-B2-001",
        rfq_supplier=invitation,
        revision=1,
        status="submitted",
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("500.00"),
        landed_total_twd=Decimal("500.00"),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        SupplierQuote.objects.create(
            quote_no="SQ-B2-001",
            rfq_supplier=invitation,
            revision=2,
            status="draft",
            currency="TWD",
            exchange_rate_to_twd=Decimal("1.000000"),
            items_subtotal=Decimal("450.00"),
            landed_total_twd=Decimal("450.00"),
        )

    first.status = "revised"
    first.save(update_fields=["status"])
    second = SupplierQuote.objects.create(
        quote_no="SQ-B2-001",
        rfq_supplier=invitation,
        revision=2,
        status="draft",
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("450.00"),
        landed_total_twd=Decimal("450.00"),
    )

    assert second.revision == 2


@pytest.mark.django_db
def test_supplier_quote_item_preserves_commercial_and_specification_snapshot(user, supplier, product):
    request_item, _, invitation = create_quote_context(user, supplier, product)
    quote = SupplierQuote.objects.create(
        quote_no="SQ-B2-002",
        rfq_supplier=invitation,
        currency="USD",
        exchange_rate_to_twd=Decimal("31.500000"),
        items_subtotal=Decimal("50.00"),
        landed_total_twd=Decimal("1575.00"),
    )
    quote_item = SupplierQuoteItem.objects.create(
        supplier_quote=quote,
        request_item=request_item,
        quantity=Decimal("5.000"),
        unit_price=Decimal("10.00"),
        subtotal=Decimal("50.00"),
        lead_time_days=7,
        warranty_months=24,
        specification_snapshot={"material": "網布", "color": "black"},
    )

    assert quote_item.specification_snapshot["material"] == "網布"


@pytest.mark.django_db
def test_supplier_quote_rejects_invalid_currency_and_negative_amount(user, supplier, product):
    _, _, invitation = create_quote_context(user, supplier, product)

    with pytest.raises(IntegrityError), transaction.atomic():
        SupplierQuote.objects.create(
            quote_no="SQ-B2-003",
            rfq_supplier=invitation,
            currency="twd",
            exchange_rate_to_twd=Decimal("1.000000"),
            items_subtotal=Decimal("-1.00"),
            landed_total_twd=Decimal("0.00"),
        )


@pytest.mark.django_db
def test_waived_requirement_requires_approver_reason_and_time(user, supplier, product):
    request_item, _, invitation = create_quote_context(user, supplier, product)
    requirement = RequestItemRequirement.objects.create(
        request_item=request_item,
        code="material",
        label="材質",
        data_type="string",
        operator="equals",
        expected_value="網布",
        is_mandatory=True,
    )
    quote = SupplierQuote.objects.create(
        quote_no="SQ-B2-004",
        rfq_supplier=invitation,
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("500.00"),
        landed_total_twd=Decimal("500.00"),
    )
    quote_item = SupplierQuoteItem.objects.create(
        supplier_quote=quote,
        request_item=request_item,
        quantity=Decimal("5.000"),
        unit_price=Decimal("100.00"),
        subtotal=Decimal("500.00"),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        QuoteRequirementResult.objects.create(
            quote_item=quote_item,
            requirement=requirement,
            result="waived",
            evidence="供應商替代材質說明",
        )

    result = QuoteRequirementResult.objects.create(
        quote_item=quote_item,
        requirement=requirement,
        result="waived",
        evidence="供應商替代材質說明",
        waiver_reason="交期優先，經業務核准採用等級相同材質",
        waived_by=user,
        waived_at=timezone.now(),
    )
    assert result.result == "waived"


@pytest.mark.django_db
def test_scoring_criterion_weight_total_must_be_100_before_rfq_is_issued(user, supplier, product):
    _, rfq, _ = create_quote_context(user, supplier, product)
    RfqScoringCriterion.objects.create(
        rfq=rfq,
        code="landed_cost",
        label="實際總成本",
        weight=Decimal("30.00"),
        calculation_method="inverse_min",
        sequence=1,
    )

    rfq.status = "issued"
    with pytest.raises(IntegrityError), transaction.atomic():
        rfq.save(update_fields=["status"])


@pytest.mark.django_db
def test_scoring_snapshots_accept_valid_normalized_and_weighted_scores(user, supplier, product):
    request_item, rfq, invitation = create_quote_context(user, supplier, product)
    criterion = RfqScoringCriterion.objects.create(
        rfq=rfq,
        code="landed_cost",
        label="實際總成本",
        weight=Decimal("30.00"),
        calculation_method="inverse_min",
        sequence=1,
    )
    quote = SupplierQuote.objects.create(
        quote_no="SQ-B2-005",
        rfq_supplier=invitation,
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("500.00"),
        landed_total_twd=Decimal("500.00"),
        valid_until=timezone.now() + timedelta(days=30),
    )
    SupplierQuoteItem.objects.create(
        supplier_quote=quote,
        request_item=request_item,
        quantity=Decimal("5.000"),
        unit_price=Decimal("100.00"),
        subtotal=Decimal("500.00"),
    )
    score = SupplierQuoteScore.objects.create(
        supplier_quote=quote,
        criterion=criterion,
        raw_value={"landed_total_twd": "500.00", "lowest_twd": "500.00"},
        normalized_score=Decimal("100.00"),
        weighted_score=Decimal("30.00"),
    )

    assert score.weighted_score == Decimal("30.00")


@pytest.mark.django_db
def test_supplier_quote_score_rejects_out_of_range_score(user, supplier, product):
    _, rfq, invitation = create_quote_context(user, supplier, product)
    criterion = RfqScoringCriterion.objects.create(
        rfq=rfq,
        code="quality",
        label="規格品質",
        weight=Decimal("30.00"),
        calculation_method="requirement_ratio",
        sequence=1,
    )
    quote = SupplierQuote.objects.create(
        quote_no="SQ-B2-006",
        rfq_supplier=invitation,
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("500.00"),
        landed_total_twd=Decimal("500.00"),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        SupplierQuoteScore.objects.create(
            supplier_quote=quote,
            criterion=criterion,
            raw_value={},
            normalized_score=Decimal("101.00"),
            weighted_score=Decimal("30.30"),
        )


@pytest.mark.django_db
def test_supplier_quote_item_requires_object_specification(user, supplier, product):
    request_item, _, invitation = create_quote_context(user, supplier, product)
    quote = SupplierQuote.objects.create(
        quote_no="SQ-B2-007",
        rfq_supplier=invitation,
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("500.00"),
        landed_total_twd=Decimal("500.00"),
    )
    quote_item = SupplierQuoteItem(
        supplier_quote=quote,
        request_item=request_item,
        quantity=Decimal("5.000"),
        unit_price=Decimal("100.00"),
        subtotal=Decimal("500.00"),
        specification_snapshot=["網布"],
    )

    with pytest.raises(ValidationError, match="JSON object"):
        quote_item.full_clean()
