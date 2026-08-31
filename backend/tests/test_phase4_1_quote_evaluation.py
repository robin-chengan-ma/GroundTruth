from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import Permission, RolePermission, UserRole
from apps.crm.models import Supplier
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
from services.rfq_quote_service import DEFAULT_CRITERIA


def _grant(user, role, *codes):
    UserRole.objects.get_or_create(user=user, role=role)
    for code in codes:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"name": code})
        RolePermission.objects.get_or_create(role=role, permission=permission)


def _context(user, product, suppliers, *, with_second_item=False):
    request = PurchaseRequest.objects.create(
        request_no="PR-C4-001",
        requester=user,
        status=PurchaseRequest.Status.SOURCING,
        purpose="C4 評分測試",
    )
    first = PurchaseRequestItem.objects.create(
        request=request,
        line_no=1,
        product=product,
        description_snapshot="辦公椅",
        quantity=Decimal("5.000"),
        unit_of_measure="EA",
    )
    items = [first]
    if with_second_item:
        items.append(PurchaseRequestItem.objects.create(
            request=request,
            line_no=2,
            product=product,
            description_snapshot="辦公桌",
            quantity=Decimal("2.000"),
            unit_of_measure="EA",
        ))
    rfq = Rfq.objects.create(
        rfq_no="RFQ-C4-001",
        request=request,
        status=Rfq.Status.DRAFT,
        response_due_at=timezone.now() + timedelta(days=1),
    )
    for sequence, (code, label, weight, method) in enumerate(DEFAULT_CRITERIA, 1):
        RfqScoringCriterion.objects.create(
            rfq=rfq,
            code=code,
            label=label,
            weight=Decimal(weight),
            calculation_method=method,
            sequence=sequence,
        )
    rfq.status = Rfq.Status.COLLECTING
    rfq.save(update_fields=["status"])
    invitations = [
        RfqSupplier.objects.create(
            rfq=rfq,
            supplier=supplier,
            status=RfqSupplier.Status.RESPONDED,
            invited_at=timezone.now(),
            responded_at=timezone.now(),
        )
        for supplier in suppliers
    ]
    return rfq, items, invitations


def _quote(invitation, number, item_prices):
    subtotal = sum((quantity * price for _, quantity, price, _ in item_prices), Decimal("0.00"))
    quote = SupplierQuote.objects.create(
        quote_no=number,
        rfq_supplier=invitation,
        status=SupplierQuote.Status.SUBMITTED,
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=subtotal,
        landed_total_twd=subtotal,
        valid_until=timezone.now() + timedelta(days=7),
        submitted_at=timezone.now(),
    )
    for item, quantity, price, lead_time in item_prices:
        SupplierQuoteItem.objects.create(
            supplier_quote=quote,
            request_item=item,
            quantity=quantity,
            unit_price=price,
            subtotal=quantity * price,
            lead_time_days=lead_time,
        )
    return quote


@pytest.mark.django_db
def test_evaluation_compares_same_item_cost_and_returns_human_readable_matrix(
    api_client, user, role_employee, product
):
    _grant(user, role_employee, "rfq.manage")
    suppliers = [Supplier.objects.create(name="供應商 A"), Supplier.objects.create(name="供應商 B")]
    rfq, items, invitations = _context(user, product, suppliers)
    _quote(invitations[0], "SQ-C4-A", [(items[0], Decimal(5), Decimal(100), 10)])
    _quote(invitations[1], "SQ-C4-B", [(items[0], Decimal(5), Decimal(125), 5)])
    api_client.force_authenticate(user=user)

    response = api_client.post(f"/api/v1/rfqs/{rfq.id}/evaluate/", {}, format="json")

    assert response.status_code == 200
    assert response.data["rfq_no"] == "RFQ-C4-001"
    assert response.data["items"][0]["description"] == "辦公椅"
    rows = response.data["items"][0]["quotes"]
    assert rows[0]["supplier_name"] == "供應商 A"
    assert rows[0]["scores"]["landed_cost"]["normalized_score"] == "100.00"
    assert rows[1]["scores"]["landed_cost"]["normalized_score"] == "80.00"
    assert response.data["recommendations"][0]["supplier_names"] == ["供應商 B"]


@pytest.mark.django_db
def test_partial_quote_can_win_item_but_cannot_be_whole_request_recommendation(
    api_client, user, role_employee, product
):
    _grant(user, role_employee, "rfq.manage")
    suppliers = [Supplier.objects.create(name="完整供應商"), Supplier.objects.create(name="部分供應商")]
    rfq, items, invitations = _context(user, product, suppliers, with_second_item=True)
    _quote(invitations[0], "SQ-C4-FULL", [
        (items[0], Decimal(5), Decimal(110), 7),
        (items[1], Decimal(2), Decimal(200), 7),
    ])
    partial = _quote(invitations[1], "SQ-C4-PART", [(items[0], Decimal(5), Decimal(100), 5)])
    api_client.force_authenticate(user=user)

    response = api_client.post(f"/api/v1/rfqs/{rfq.id}/evaluate/", {}, format="json")

    assert response.status_code == 200
    partial_summary = next(row for row in response.data["quote_summaries"] if row["quote_id"] == partial.id)
    assert partial_summary["covers_all_items"] is False
    assert partial_summary["whole_request_recommended"] is False
    first_item = response.data["items"][0]
    assert first_item["recommended_supplier_names"] == ["部分供應商"]


@pytest.mark.django_db
def test_failed_mandatory_requirement_blocks_item_recommendation(
    api_client, user, role_employee, product
):
    _grant(user, role_employee, "rfq.manage")
    suppliers = [Supplier.objects.create(name="合格供應商"), Supplier.objects.create(name="不合格供應商")]
    rfq, items, invitations = _context(user, product, suppliers)
    requirement = RequestItemRequirement.objects.create(
        request_item=items[0], code="material", label="材質", data_type="string",
        operator="equals", expected_value="網布", is_mandatory=True,
    )
    good = _quote(invitations[0], "SQ-C4-GOOD", [(items[0], Decimal(5), Decimal(110), 7)])
    bad = _quote(invitations[1], "SQ-C4-BAD", [(items[0], Decimal(5), Decimal(90), 5)])
    good_item = good.items.get()
    bad_item = bad.items.get()
    QuoteRequirementResult.objects.create(
        quote_item=good_item, requirement=requirement, result=QuoteRequirementResult.Result.PASS,
    )
    QuoteRequirementResult.objects.create(
        quote_item=bad_item, requirement=requirement, result=QuoteRequirementResult.Result.FAIL,
    )
    api_client.force_authenticate(user=user)

    response = api_client.post(f"/api/v1/rfqs/{rfq.id}/evaluate/", {}, format="json")

    assert response.status_code == 200
    bad_row = next(row for row in response.data["items"][0]["quotes"] if row["quote_id"] == bad.id)
    assert bad_row["eligible"] is False
    assert bad_row["eligibility_reason"] == "必要條件未通過"
    assert response.data["items"][0]["recommended_supplier_names"] == ["合格供應商"]


@pytest.mark.django_db
def test_missing_formal_data_is_unavailable_and_not_fabricated(
    api_client, user, role_employee, product, supplier
):
    _grant(user, role_employee, "rfq.manage")
    rfq, items, invitations = _context(user, product, [supplier])
    quote = _quote(invitations[0], "SQ-C4-NODATA", [(items[0], Decimal(5), Decimal(100), 7)])
    api_client.force_authenticate(user=user)

    response = api_client.post(f"/api/v1/rfqs/{rfq.id}/evaluate/", {}, format="json")

    summary = response.data["quote_summaries"][0]
    assert summary["scores"]["supplier_performance"]["status"] == "unavailable"
    assert summary["scores"]["sustainability_risk"]["status"] == "unavailable"
    assert summary["data_completeness_pct"] == "45.00"
    assert not SupplierQuoteScore.objects.filter(
        supplier_quote=quote,
        criterion__code__in=["supplier_performance", "sustainability_risk"],
    ).exists()


@pytest.mark.django_db
def test_evaluation_replaces_score_snapshot_without_duplicates(
    api_client, user, role_employee, product, supplier
):
    _grant(user, role_employee, "rfq.manage")
    rfq, items, invitations = _context(user, product, [supplier])
    quote = _quote(invitations[0], "SQ-C4-IDEMPOTENT", [(items[0], Decimal(5), Decimal(100), 7)])
    api_client.force_authenticate(user=user)

    first = api_client.post(f"/api/v1/rfqs/{rfq.id}/evaluate/", {}, format="json")
    second = api_client.post(f"/api/v1/rfqs/{rfq.id}/evaluate/", {}, format="json")

    assert first.status_code == second.status_code == 200
    assert SupplierQuoteScore.objects.filter(supplier_quote=quote).count() == 2


@pytest.mark.django_db
def test_evaluation_requires_rfq_manage_permission(api_client, user, product, supplier):
    rfq, _, _ = _context(user, product, [supplier])
    api_client.force_authenticate(user=user)

    response = api_client.post(f"/api/v1/rfqs/{rfq.id}/evaluate/", {}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
