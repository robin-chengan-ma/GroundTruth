from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import Permission, RolePermission, UserRole
from apps.crm.models import Supplier
from apps.procurement.models import (
    ApprovalPolicy,
    ApprovalPolicyStep,
    AwardDecision,
    PurchaseRequest,
    PurchaseRequestItem,
    QuoteRequirementResult,
    RequestItemRequirement,
    Rfq,
    RfqScoringCriterion,
    RfqSupplier,
    SupplierQuote,
    SupplierQuoteItem,
)
from services.rfq_quote_service import DEFAULT_CRITERIA


def _grant(user, role, *codes):
    UserRole.objects.get_or_create(user=user, role=role)
    for code in codes:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"name": code})
        RolePermission.objects.get_or_create(role=role, permission=permission)


def _context(user, product, suppliers, *, quantities=("5.000",)):
    request = PurchaseRequest.objects.create(
        request_no="PR-C5-001",
        requester=user,
        status=PurchaseRequest.Status.AWARDING,
        purpose="C5 選商測試",
    )
    items = [
        PurchaseRequestItem.objects.create(
            request=request,
            line_no=index,
            product=product,
            description_snapshot=f"品項 {index}",
            quantity=Decimal(quantity),
            unit_of_measure="EA",
        )
        for index, quantity in enumerate(quantities, 1)
    ]
    rfq = Rfq.objects.create(
        rfq_no="RFQ-C5-001",
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
    rfq.status = Rfq.Status.EVALUATING
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


def _quote(invitation, number, item_prices, *, valid=True, shipping="0.00"):
    subtotal = sum((quantity * price for _, quantity, price in item_prices), Decimal("0.00"))
    quote = SupplierQuote.objects.create(
        quote_no=number,
        rfq_supplier=invitation,
        status=SupplierQuote.Status.ACCEPTED_FOR_EVALUATION,
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=subtotal,
        shipping_amount=Decimal(shipping),
        landed_total_twd=subtotal + Decimal(shipping),
        valid_until=timezone.now() + timedelta(days=7 if valid else -1),
        submitted_at=timezone.now(),
    )
    quote_items = []
    for item, quantity, price in item_prices:
        quote_items.append(SupplierQuoteItem.objects.create(
            supplier_quote=quote,
            request_item=item,
            quantity=quantity,
            unit_price=price,
            subtotal=quantity * price,
            lead_time_days=7,
        ))
    return quote, quote_items


def _create_award(api_client, rfq, lines, reason=""):
    return api_client.post(
        "/api/v1/award-decisions/",
        {"rfq_id": rfq.id, "selection_reason": reason, "lines": lines},
        format="json",
    )


def _approval_policy(role):
    policy = ApprovalPolicy.objects.create(
        name="C5 得標提交測試政策",
        currency="TWD",
        min_amount=Decimal("0.00"),
        max_amount=None,
        active_from=timezone.now() - timedelta(days=1),
    )
    ApprovalPolicyStep.objects.create(policy=policy, sequence=1, role=role)


@pytest.mark.django_db
def test_create_whole_request_award_and_submit_with_landed_cost_snapshot(
    api_client, user, role_employee, product
):
    _grant(user, role_employee, "award.recommend")
    _approval_policy(role_employee)
    supplier = Supplier.objects.create(name="整單供應商")
    rfq, items, invitations = _context(user, product, [supplier], quantities=("5", "2"))
    _, quote_items = _quote(
        invitations[0],
        "SQ-C5-WHOLE",
        [(items[0], Decimal(5), Decimal(100)), (items[1], Decimal(2), Decimal(200))],
        shipping="90.00",
    )
    api_client.force_authenticate(user=user)

    created = _create_award(api_client, rfq, [
        {"request_item_id": items[0].id, "supplier_quote_item_id": quote_items[0].id, "quantity": "5.000"},
        {"request_item_id": items[1].id, "supplier_quote_item_id": quote_items[1].id, "quantity": "2.000"},
    ])
    submitted = api_client.post(f"/api/v1/award-decisions/{created.data['id']}/submit/", {}, format="json")

    assert created.status_code == 201
    assert submitted.status_code == 200
    assert submitted.data["status"] == "submitted"
    assert submitted.data["total_amount_twd"] == "990.00"
    assert rfq.request.__class__.objects.get(pk=rfq.request_id).status == PurchaseRequest.Status.APPROVAL


@pytest.mark.django_db
def test_item_level_and_split_award_are_supported(api_client, user, role_employee, product):
    _grant(user, role_employee, "award.recommend")
    _approval_policy(role_employee)
    suppliers = [Supplier.objects.create(name="供應商 A"), Supplier.objects.create(name="供應商 B")]
    rfq, items, invitations = _context(user, product, suppliers)
    _, a_items = _quote(invitations[0], "SQ-C5-A", [(items[0], Decimal(5), Decimal(100))])
    _, b_items = _quote(invitations[1], "SQ-C5-B", [(items[0], Decimal(5), Decimal(100))])
    api_client.force_authenticate(user=user)

    response = _create_award(api_client, rfq, [
        {"request_item_id": items[0].id, "supplier_quote_item_id": a_items[0].id, "quantity": "3.000"},
        {"request_item_id": items[0].id, "supplier_quote_item_id": b_items[0].id, "quantity": "2.000"},
    ])
    submitted = api_client.post(f"/api/v1/award-decisions/{response.data['id']}/submit/", {}, format="json")

    assert response.status_code == 201
    assert submitted.status_code == 200
    assert len(submitted.data["lines"]) == 2


@pytest.mark.django_db
def test_non_recommended_supplier_requires_reason(api_client, user, role_employee, product):
    _grant(user, role_employee, "award.recommend")
    suppliers = [Supplier.objects.create(name="推薦供應商"), Supplier.objects.create(name="非推薦供應商")]
    rfq, items, invitations = _context(user, product, suppliers)
    _quote(invitations[0], "SQ-C5-BEST", [(items[0], Decimal(5), Decimal(90))])
    _, expensive_items = _quote(invitations[1], "SQ-C5-OTHER", [(items[0], Decimal(5), Decimal(150))])
    api_client.force_authenticate(user=user)

    response = _create_award(api_client, rfq, [{
        "request_item_id": items[0].id,
        "supplier_quote_item_id": expensive_items[0].id,
        "quantity": "5.000",
    }])

    assert response.status_code == 400
    assert response.data["code"] == "reason_required"


@pytest.mark.django_db
def test_award_rejects_expired_or_mandatory_failed_quote(api_client, user, role_employee, product):
    _grant(user, role_employee, "award.recommend")
    suppliers = [Supplier.objects.create(name="過期供應商"), Supplier.objects.create(name="不合格供應商")]
    rfq, items, invitations = _context(user, product, suppliers)
    _, expired_items = _quote(
        invitations[0], "SQ-C5-EXPIRED", [(items[0], Decimal(5), Decimal(100))], valid=False
    )
    _, failed_items = _quote(invitations[1], "SQ-C5-FAILED", [(items[0], Decimal(5), Decimal(100))])
    requirement = RequestItemRequirement.objects.create(
        request_item=items[0], code="material", label="材質", data_type="string",
        operator="equals", expected_value="網布", is_mandatory=True,
    )
    QuoteRequirementResult.objects.create(
        quote_item=failed_items[0], requirement=requirement, result=QuoteRequirementResult.Result.FAIL,
    )
    api_client.force_authenticate(user=user)

    expired = _create_award(api_client, rfq, [{
        "request_item_id": items[0].id, "supplier_quote_item_id": expired_items[0].id, "quantity": "5.000"
    }], reason="特殊交期需求")
    failed = _create_award(api_client, rfq, [{
        "request_item_id": items[0].id, "supplier_quote_item_id": failed_items[0].id, "quantity": "5.000"
    }], reason="價格考量")

    assert expired.status_code == 409
    assert failed.status_code == 409


@pytest.mark.django_db
def test_award_submit_rejects_incomplete_allocation(api_client, user, role_employee, product):
    _grant(user, role_employee, "award.recommend")
    supplier = Supplier.objects.create(name="部分分配供應商")
    rfq, items, invitations = _context(user, product, [supplier])
    _, quote_items = _quote(invitations[0], "SQ-C5-PARTIAL", [(items[0], Decimal(5), Decimal(100))])
    api_client.force_authenticate(user=user)
    created = _create_award(api_client, rfq, [{
        "request_item_id": items[0].id, "supplier_quote_item_id": quote_items[0].id, "quantity": "4.000"
    }])

    response = api_client.post(f"/api/v1/award-decisions/{created.data['id']}/submit/", {}, format="json")

    assert created.status_code == 201
    assert response.status_code == 409
    assert AwardDecision.objects.get(pk=created.data["id"]).status == AwardDecision.Status.DRAFT


@pytest.mark.django_db
def test_award_requires_permission(api_client, user, product, supplier):
    rfq, items, invitations = _context(user, product, [supplier])
    _, quote_items = _quote(invitations[0], "SQ-C5-NOAUTH", [(items[0], Decimal(5), Decimal(100))])
    api_client.force_authenticate(user=user)

    response = _create_award(api_client, rfq, [{
        "request_item_id": items[0].id, "supplier_quote_item_id": quote_items[0].id, "quantity": "5.000"
    }])

    assert response.status_code == 403


@pytest.mark.django_db
def test_draft_can_be_replaced_but_second_active_award_is_rejected(
    api_client, user, role_employee, product, supplier
):
    _grant(user, role_employee, "award.recommend")
    rfq, items, invitations = _context(user, product, [supplier])
    _, quote_items = _quote(invitations[0], "SQ-C5-EDIT", [(items[0], Decimal(5), Decimal(100))])
    api_client.force_authenticate(user=user)
    original = _create_award(api_client, rfq, [{
        "request_item_id": items[0].id, "supplier_quote_item_id": quote_items[0].id, "quantity": "4.000"
    }])

    updated = api_client.patch(
        f"/api/v1/award-decisions/{original.data['id']}/",
        {
            "selection_reason": "",
            "lines": [{
                "request_item_id": items[0].id,
                "supplier_quote_item_id": quote_items[0].id,
                "quantity": "5.000",
            }],
        },
        format="json",
    )
    duplicate = _create_award(api_client, rfq, [{
        "request_item_id": items[0].id, "supplier_quote_item_id": quote_items[0].id, "quantity": "5.000"
    }])

    assert updated.status_code == 200
    assert updated.data["lines"][0]["quantity"] == "5.000"
    assert duplicate.status_code == 409
