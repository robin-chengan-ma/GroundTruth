from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import Permission, RolePermission, UserRole
from apps.procurement.models import (
    PurchaseRequest,
    PurchaseRequestItem,
    QuoteRequirementResult,
    RequestItemRequirement,
    Rfq,
    RfqScoringCriterion,
    RfqSupplier,
    SupplierQuote,
)
from services.rfq_quote_service import _matches


def _grant(user, role, *codes):
    UserRole.objects.get_or_create(user=user, role=role)
    for code in codes:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"name": code})
        RolePermission.objects.get_or_create(role=role, permission=permission)


def _submitted_request(user, supplier, product, *, requirement=False):
    request = PurchaseRequest.objects.create(
        request_no="PR-C3-001",
        requester=user,
        status=PurchaseRequest.Status.SUBMITTED,
        purpose="C3 測試",
    )
    item = PurchaseRequestItem.objects.create(
        request=request,
        line_no=1,
        product=product,
        description_snapshot=product.name,
        quantity=Decimal("5.000"),
        unit_of_measure="EA",
    )
    if requirement:
        RequestItemRequirement.objects.create(
            request_item=item,
            code="material",
            label="材質",
            data_type="string",
            operator="equals",
            expected_value="網布",
            is_mandatory=True,
        )
    rfq = Rfq.objects.create(rfq_no="RFQ-C3-001", request=request)
    invitation = RfqSupplier.objects.create(
        rfq=rfq,
        supplier=supplier,
        invited_at=timezone.now(),
    )
    return request, item, rfq, invitation


@pytest.mark.django_db
def test_issue_rfq_freezes_default_criteria_and_moves_request_to_sourcing(
    api_client, user, role_employee, supplier, product,
):
    _grant(user, role_employee, "rfq.manage")
    api_client.force_authenticate(user=user)
    request, _, rfq, _ = _submitted_request(user, supplier, product)
    due_at = timezone.now() + timedelta(days=7)

    response = api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 1, "response_due_at": due_at.isoformat()},
        format="json",
    )

    assert response.status_code == 200
    request.refresh_from_db()
    rfq.refresh_from_db()
    assert request.status == PurchaseRequest.Status.SOURCING
    assert rfq.status == Rfq.Status.ISSUED
    assert rfq.version == 2
    assert RfqScoringCriterion.objects.filter(rfq=rfq).count() == 6
    assert sum(rfq.scoring_criteria.values_list("weight", flat=True)) == Decimal("100.00")


@pytest.mark.django_db
def test_issue_rfq_rejects_stale_version_and_past_deadline(
    api_client, user, role_employee, supplier, product,
):
    _grant(user, role_employee, "rfq.manage")
    api_client.force_authenticate(user=user)
    _, _, rfq, _ = _submitted_request(user, supplier, product)

    stale = api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 99, "response_due_at": (timezone.now() + timedelta(days=1)).isoformat()},
        format="json",
    )
    past = api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 1, "response_due_at": (timezone.now() - timedelta(seconds=1)).isoformat()},
        format="json",
    )

    assert stale.status_code == 409
    assert past.status_code == 400
    rfq.refresh_from_db()
    assert rfq.status == Rfq.Status.DRAFT


@pytest.mark.django_db
def test_create_and_submit_quote_recalculates_amounts_and_requirements(
    api_client, user, role_employee, supplier, product,
):
    _grant(user, role_employee, "rfq.manage", "supplier_quote.manage")
    api_client.force_authenticate(user=user)
    _, item, rfq, invitation = _submitted_request(user, supplier, product, requirement=True)
    due_at = timezone.now() + timedelta(days=7)
    api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 1, "response_due_at": due_at.isoformat()},
        format="json",
    )

    created = api_client.post(
        "/api/v1/supplier-quotes/",
        {
            "rfq_supplier_id": invitation.id,
            "currency": "TWD",
            "exchange_rate_to_twd": "1",
            "tax_amount": "50",
            "shipping_amount": "20",
            "discount_amount": "10",
            "valid_until": (timezone.now() + timedelta(days=3)).isoformat(),
            "items": [{
                "request_item_id": item.id,
                "quantity": "5",
                "unit_price": "100",
                "subtotal": "1",
                "specifications": {"material": "網布"},
            }],
        },
        format="json",
    )
    submitted = api_client.post(f"/api/v1/supplier-quotes/{created.data['id']}/submit/", {}, format="json")

    assert created.status_code == 201
    assert created.data["items_subtotal"] == "500.00"
    assert created.data["landed_total_twd"] == "560.00"
    assert submitted.status_code == 200
    assert submitted.data["status"] == SupplierQuote.Status.SUBMITTED
    result = QuoteRequirementResult.objects.get(quote_item__supplier_quote_id=created.data["id"])
    assert result.result == QuoteRequirementResult.Result.PASS
    assert invitation.__class__.objects.get(pk=invitation.pk).status == RfqSupplier.Status.RESPONDED


@pytest.mark.django_db
def test_quote_submission_rejects_expired_quote(api_client, user, role_employee, supplier, product):
    _grant(user, role_employee, "rfq.manage", "supplier_quote.manage")
    api_client.force_authenticate(user=user)
    _, item, rfq, invitation = _submitted_request(user, supplier, product)
    api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 1, "response_due_at": (timezone.now() + timedelta(days=2)).isoformat()},
        format="json",
    )
    created = api_client.post(
        "/api/v1/supplier-quotes/",
        {
            "rfq_supplier_id": invitation.id,
            "currency": "TWD",
            "exchange_rate_to_twd": "1",
            "valid_until": (timezone.now() - timedelta(seconds=1)).isoformat(),
            "items": [{"request_item_id": item.id, "quantity": "5", "unit_price": "100"}],
        },
        format="json",
    )

    response = api_client.post(f"/api/v1/supplier-quotes/{created.data['id']}/submit/", {}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "quote_expired"
    assert SupplierQuote.objects.get(pk=created.data["id"]).status == SupplierQuote.Status.EXPIRED


@pytest.mark.django_db
def test_quote_revision_keeps_old_version_immutable(api_client, user, role_employee, supplier, product):
    _grant(user, role_employee, "rfq.manage", "supplier_quote.manage")
    api_client.force_authenticate(user=user)
    _, item, rfq, invitation = _submitted_request(user, supplier, product)
    api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 1, "response_due_at": (timezone.now() + timedelta(days=7)).isoformat()},
        format="json",
    )
    first = api_client.post(
        "/api/v1/supplier-quotes/",
        {
            "rfq_supplier_id": invitation.id,
            "currency": "TWD",
            "exchange_rate_to_twd": "1",
            "items": [{"request_item_id": item.id, "quantity": "5", "unit_price": "100"}],
        },
        format="json",
    )
    api_client.post(f"/api/v1/supplier-quotes/{first.data['id']}/submit/", {}, format="json")

    second = api_client.post(
        f"/api/v1/supplier-quotes/{first.data['id']}/revise/",
        {"items": [{"request_item_id": item.id, "quantity": "5", "unit_price": "95"}]},
        format="json",
    )

    assert second.status_code == 201
    assert second.data["revision"] == 2
    assert second.data["items_subtotal"] == "475.00"
    assert SupplierQuote.objects.get(pk=first.data["id"]).status == SupplierQuote.Status.REVISED


@pytest.mark.django_db
def test_requirement_waiver_requires_separate_permission_and_reason(
    api_client, user, role_employee, supplier, product,
):
    _grant(user, role_employee, "rfq.manage", "supplier_quote.manage")
    api_client.force_authenticate(user=user)
    _, item, rfq, invitation = _submitted_request(user, supplier, product, requirement=True)
    api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 1, "response_due_at": (timezone.now() + timedelta(days=7)).isoformat()},
        format="json",
    )
    quote = api_client.post(
        "/api/v1/supplier-quotes/",
        {
            "rfq_supplier_id": invitation.id,
            "currency": "TWD",
            "exchange_rate_to_twd": "1",
            "items": [{
                "request_item_id": item.id,
                "quantity": "5",
                "unit_price": "100",
                "specifications": {"material": "皮革"},
            }],
        },
        format="json",
    )
    api_client.post(f"/api/v1/supplier-quotes/{quote.data['id']}/submit/", {}, format="json")
    result = QuoteRequirementResult.objects.get(quote_item__supplier_quote_id=quote.data["id"])

    forbidden = api_client.post(
        f"/api/v1/quote-requirement-results/{result.id}/waive/",
        {"reason": "接受替代材質"},
        format="json",
    )
    _grant(user, role_employee, "requirement.waive")
    missing = api_client.post(
        f"/api/v1/quote-requirement-results/{result.id}/waive/", {"reason": ""}, format="json",
    )
    waived = api_client.post(
        f"/api/v1/quote-requirement-results/{result.id}/waive/",
        {"reason": "交期優先，接受同等級替代材質"},
        format="json",
    )

    assert forbidden.status_code == 403
    assert missing.status_code == 400
    assert waived.status_code == 200
    result.refresh_from_db()
    assert result.result == QuoteRequirementResult.Result.WAIVED
    assert result.waived_by == user


@pytest.mark.django_db
def test_issue_and_quote_commands_require_rbac(api_client, user, supplier, product):
    api_client.force_authenticate(user=user)
    _, item, rfq, invitation = _submitted_request(user, supplier, product)

    issue = api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 1, "response_due_at": (timezone.now() + timedelta(days=1)).isoformat()},
        format="json",
    )
    create = api_client.post(
        "/api/v1/supplier-quotes/",
        {
            "rfq_supplier_id": invitation.id,
            "currency": "TWD",
            "exchange_rate_to_twd": "1",
            "items": [{"request_item_id": item.id, "quantity": "1", "unit_price": "10"}],
        },
        format="json",
    )

    assert issue.status_code == 403
    assert create.status_code == 403
    assert SupplierQuote.objects.count() == 0


@pytest.mark.django_db
def test_create_quote_rejects_second_active_quote(api_client, user, role_employee, supplier, product):
    _grant(user, role_employee, "rfq.manage", "supplier_quote.manage")
    api_client.force_authenticate(user=user)
    _, item, rfq, invitation = _submitted_request(user, supplier, product)
    api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 1, "response_due_at": (timezone.now() + timedelta(days=2)).isoformat()},
        format="json",
    )
    payload = {
        "rfq_supplier_id": invitation.id,
        "currency": "TWD",
        "exchange_rate_to_twd": "1",
        "items": [{"request_item_id": item.id, "quantity": "1", "unit_price": "10"}],
    }

    first = api_client.post("/api/v1/supplier-quotes/", payload, format="json")
    second = api_client.post("/api/v1/supplier-quotes/", payload, format="json")

    assert first.status_code == 201
    assert second.status_code == 409
    assert SupplierQuote.objects.count() == 1


@pytest.mark.django_db
def test_create_quote_rejects_closed_response_window(api_client, user, role_employee, supplier, product):
    _grant(user, role_employee, "rfq.manage", "supplier_quote.manage")
    api_client.force_authenticate(user=user)
    _, item, rfq, invitation = _submitted_request(user, supplier, product)
    api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 1, "response_due_at": (timezone.now() + timedelta(days=2)).isoformat()},
        format="json",
    )
    Rfq.objects.filter(pk=rfq.pk).update(response_due_at=timezone.now() - timedelta(seconds=1))

    response = api_client.post(
        "/api/v1/supplier-quotes/",
        {
            "rfq_supplier_id": invitation.id,
            "currency": "TWD",
            "exchange_rate_to_twd": "1",
            "items": [{"request_item_id": item.id, "quantity": "1", "unit_price": "10"}],
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "quote_expired"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "invalid_item",
    [
        {"request_item_id": True, "quantity": "1", "unit_price": "10"},
        {"request_item_id": 1, "quantity": "0", "unit_price": "10"},
        {"request_item_id": 1, "quantity": "1.0001", "unit_price": "10"},
        {"request_item_id": 1, "quantity": "1", "unit_price": "NaN"},
        {"request_item_id": 1, "quantity": "1", "unit_price": "10", "lead_time_days": -1},
    ],
)
def test_create_quote_rejects_invalid_item_values(
    api_client, user, role_employee, supplier, product, invalid_item,
):
    _grant(user, role_employee, "rfq.manage", "supplier_quote.manage")
    api_client.force_authenticate(user=user)
    _, item, rfq, invitation = _submitted_request(user, supplier, product)
    invalid_item = {
        **invalid_item,
        "request_item_id": item.id if type(invalid_item["request_item_id"]) is int else True,
    }
    api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 1, "response_due_at": (timezone.now() + timedelta(days=2)).isoformat()},
        format="json",
    )

    response = api_client.post(
        "/api/v1/supplier-quotes/",
        {
            "rfq_supplier_id": invitation.id,
            "currency": "TWD",
            "exchange_rate_to_twd": "1",
            "items": [invalid_item],
        },
        format="json",
    )

    assert response.status_code == 400
    assert SupplierQuote.objects.count() == 0


@pytest.mark.django_db
def test_missing_specification_is_recorded_as_not_provided(
    api_client, user, role_employee, supplier, product,
):
    _grant(user, role_employee, "rfq.manage", "supplier_quote.manage")
    api_client.force_authenticate(user=user)
    _, item, rfq, invitation = _submitted_request(user, supplier, product, requirement=True)
    api_client.post(
        f"/api/v1/rfqs/{rfq.id}/issue/",
        {"version": 1, "response_due_at": (timezone.now() + timedelta(days=2)).isoformat()},
        format="json",
    )
    quote = api_client.post(
        "/api/v1/supplier-quotes/",
        {
            "rfq_supplier_id": invitation.id,
            "currency": "TWD",
            "exchange_rate_to_twd": "1",
            "items": [{"request_item_id": item.id, "quantity": "1", "unit_price": "10"}],
        },
        format="json",
    )

    api_client.post(f"/api/v1/supplier-quotes/{quote.data['id']}/submit/", {}, format="json")

    result = QuoteRequirementResult.objects.get(quote_item__supplier_quote_id=quote.data["id"])
    assert result.result == QuoteRequirementResult.Result.NOT_PROVIDED


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("data_type", "operator", "expected", "actual", "matches"),
    [
        ("string", "equals", "網布", "網布", True),
        ("string", "not_equals", "皮革", "網布", True),
        ("number", "gte", 100, "100.5", True),
        ("number", "lte", 100, "100.5", False),
        ("enum", "in", ["黑", "灰"], "灰", True),
        ("string", "contains", "人體工學", "高背人體工學椅", True),
        ("boolean", "equals", True, "true", False),
    ],
)
def test_requirement_operators_use_declared_data_type(
    user, product, data_type, operator, expected, actual, matches,
):
    request = PurchaseRequest.objects.create(request_no="PR-C3-TYPE", requester=user, purpose="型別測試")
    item = PurchaseRequestItem.objects.create(
        request=request,
        line_no=1,
        product=product,
        description_snapshot=product.name,
        quantity=Decimal("1.000"),
        unit_of_measure="EA",
    )
    requirement = RequestItemRequirement.objects.create(
        request_item=item,
        code="typed",
        label="型別條件",
        data_type=data_type,
        operator=operator,
        expected_value=expected,
    )

    assert _matches(requirement, actual) is matches
