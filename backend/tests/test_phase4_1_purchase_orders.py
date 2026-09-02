from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import Role
from apps.erp.models import InventoryBalance, InventoryMovement
from apps.procurement.models import (
    ApprovalCase,
    AwardDecision,
    AwardLine,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    RfqSupplier,
    SupplierQuote,
    SupplierQuoteItem,
)
from tests.test_phase4_1_approval_workflow import (
    _actor,
    _award_context,
    _grant,
    _policy,
    _submit,
)


def _approve(api_client, approver, case):
    step = case.steps.get(step_type="amount_approval")
    api_client.force_authenticate(user=approver)
    claimed = api_client.post(f"/api/v1/approval-steps/{step.id}/claim/", {}, format="json")
    decided = api_client.post(
        f"/api/v1/approval-steps/{step.id}/decide/",
        {"decision": "approved", "reason": "金額與預算已確認"},
        format="json",
    )
    return claimed, decided


def _approved_award(api_client, requester, requester_role, product, supplier):
    amount_role = Role.objects.create(role=f"po_approver_{requester.id}")
    waiver_role = Role.objects.create(role=f"po_waiver_{requester.id}")
    approver = _actor(
        f"PO Approver {requester.id}",
        amount_role,
        "approval.claim",
        "approval.decide",
        "approval.read_all",
    )
    _grant(requester, requester_role, "award.recommend", "purchase_request.read_own")
    _policy(amount_role, waiver_role)
    award, _ = _award_context(requester, product, supplier)
    submitted = _submit(api_client, requester, award)
    case = ApprovalCase.objects.get(award=award)
    return award, case, approver, submitted


@pytest.mark.django_db
def test_final_approval_creates_draft_po_and_orders_request(
    api_client, user, role_employee, product, supplier
):
    award, case, approver, submitted = _approved_award(
        api_client, user, role_employee, product, supplier
    )

    claimed, decided = _approve(api_client, approver, case)

    assert submitted.status_code == 200
    assert claimed.status_code == 200
    assert decided.status_code == 200
    purchase_order = PurchaseOrder.objects.get(award=award, supplier=supplier)
    assert purchase_order.status == PurchaseOrder.Status.DRAFT
    assert purchase_order.total_amount == Decimal("200.00")
    assert purchase_order.items.count() == 1
    assert PurchaseRequest.objects.get(pk=award.rfq.request_id).status == PurchaseRequest.Status.ORDERED


@pytest.mark.django_db
def test_award_is_split_into_one_po_per_supplier_with_request_snapshots(
    api_client, user, role_employee, product, supplier
):
    amount_role = Role.objects.create(role="split_po_approver")
    waiver_role = Role.objects.create(role="split_po_waiver")
    approver = _actor(
        "Split PO Approver",
        amount_role,
        "approval.claim",
        "approval.decide",
        "approval.read_all",
    )
    _grant(user, role_employee, "award.recommend")
    _policy(amount_role, waiver_role)
    award, _ = _award_context(user, product, supplier)
    first_line = award.lines.select_related("request_item").get()
    first_line.awarded_quantity = Decimal("1.000")
    first_line.amount_snapshot = Decimal("100.00")
    first_line.save(update_fields=["awarded_quantity", "amount_snapshot"])
    second_supplier = supplier.__class__.objects.create(name="第二得標供應商")
    invitation = RfqSupplier.objects.create(
        rfq=award.rfq,
        supplier=second_supplier,
        status=RfqSupplier.Status.RESPONDED,
        invited_at=timezone.now(),
        responded_at=timezone.now(),
    )
    quote = SupplierQuote.objects.create(
        quote_no="SQ-C5-3-SPLIT",
        rfq_supplier=invitation,
        status=SupplierQuote.Status.ACCEPTED_FOR_EVALUATION,
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("120.00"),
        landed_total_twd=Decimal("120.00"),
        valid_until=timezone.now() + timedelta(days=7),
        submitted_at=timezone.now(),
    )
    quote_item = SupplierQuoteItem.objects.create(
        supplier_quote=quote,
        request_item=first_line.request_item,
        quantity=Decimal("1.000"),
        unit_price=Decimal("120.00"),
        subtotal=Decimal("120.00"),
    )
    AwardLine.objects.create(
        award=award,
        request_item=first_line.request_item,
        supplier_quote_item=quote_item,
        awarded_quantity=Decimal("1.000"),
        unit_price_snapshot=Decimal("120.00"),
        amount_snapshot=Decimal("120.00"),
    )
    award.selection_reason = "以第二供應來源分散交期風險"
    award.save(update_fields=["selection_reason"])
    _submit(api_client, user, award)
    case = ApprovalCase.objects.get(award=award)

    _, decided = _approve(api_client, approver, case)

    assert decided.status_code == 200
    orders = list(PurchaseOrder.objects.filter(award=award).order_by("supplier_id"))
    assert len(orders) == 2
    assert {order.total_amount for order in orders} == {Decimal("100.00"), Decimal("120.00")}
    items = list(PurchaseOrderItem.objects.filter(purchase_order__award=award))
    assert {item.product_name_snapshot for item in items} == {"企業用辦公椅"}
    assert all(item.specification_snapshot == first_line.request_item.specification_snapshot for item in items)


@pytest.mark.django_db
def test_changed_award_amount_after_submission_rolls_back_final_approval(
    api_client, user, role_employee, product, supplier
):
    award, case, approver, _ = _approved_award(api_client, user, role_employee, product, supplier)
    line = award.lines.get()
    line.amount_snapshot = Decimal("999.00")
    line.save(update_fields=["amount_snapshot"])

    _, decided = _approve(api_client, approver, case)

    assert decided.status_code == 409
    case.refresh_from_db()
    award.refresh_from_db()
    assert case.status == ApprovalCase.Status.IN_PROGRESS
    assert award.status == AwardDecision.Status.SUBMITTED
    assert not PurchaseOrder.objects.filter(award=award).exists()


@pytest.mark.django_db
def test_nonfinal_approval_does_not_create_purchase_order(
    api_client, user, role_employee, product, supplier
):
    amount_role = Role.objects.create(role="po_amount_after_waiver")
    waiver_role = Role.objects.create(role="po_exception_first")
    original = _actor("PO Original Waiver", waiver_role, "requirement.waive")
    reviewer = _actor(
        "PO Second Reviewer",
        waiver_role,
        "requirement.waive",
        "approval.claim",
        "approval.decide",
        "approval.read_all",
    )
    _grant(user, role_employee, "award.recommend")
    _policy(amount_role, waiver_role)
    award, _ = _award_context(user, product, supplier, waiver_by=original)
    _submit(api_client, user, award)
    case = ApprovalCase.objects.get(award=award)
    waiver_step = case.steps.get(step_type="waiver_exception")
    api_client.force_authenticate(user=reviewer)
    api_client.post(f"/api/v1/approval-steps/{waiver_step.id}/claim/", {})

    response = api_client.post(
        f"/api/v1/approval-steps/{waiver_step.id}/decide/",
        {"decision": "approved", "reason": "例外證據符合"},
        format="json",
    )

    assert response.status_code == 200
    assert not PurchaseOrder.objects.filter(award=award).exists()


@pytest.mark.django_db
def test_incomplete_existing_po_rolls_back_final_approval(
    api_client, user, role_employee, product, supplier
):
    award, case, approver, _ = _approved_award(api_client, user, role_employee, product, supplier)
    PurchaseOrder.objects.create(
        po_no="PO-INCOMPLETE",
        award=award,
        supplier=supplier,
        currency="TWD",
        total_amount=Decimal("0.00"),
    )

    _, decided = _approve(api_client, approver, case)

    assert decided.status_code == 409
    case.refresh_from_db()
    award.refresh_from_db()
    assert case.status == ApprovalCase.Status.IN_PROGRESS
    assert award.status == AwardDecision.Status.SUBMITTED
    assert case.steps.get().status == "claimed"


@pytest.mark.django_db
def test_po_list_visibility_is_own_request_or_business_permission(
    api_client, user, role_employee, product, supplier
):
    award, case, approver, _ = _approved_award(api_client, user, role_employee, product, supplier)
    _approve(api_client, approver, case)
    manager_role = Role.objects.create(role="po_manager")
    manager = _actor("PO Manager", manager_role, "purchase_order.manage")
    outsider_role = Role.objects.create(role="po_outsider")
    outsider = _actor("PO Outsider", outsider_role)

    api_client.force_authenticate(user=user)
    owner_response = api_client.get("/api/v1/purchase-orders/")
    api_client.force_authenticate(user=manager)
    manager_response = api_client.get("/api/v1/purchase-orders/")
    api_client.force_authenticate(user=outsider)
    denied_response = api_client.get("/api/v1/purchase-orders/")

    assert owner_response.status_code == 200
    assert [row["award_id"] for row in owner_response.data["results"]] == [award.id]
    assert manager_response.status_code == 200
    assert [row["award_id"] for row in manager_response.data["results"]] == [award.id]
    assert denied_response.status_code == 403


@pytest.mark.django_db
def test_issue_po_requires_permission_and_matching_version(
    api_client, user, role_employee, product, supplier
):
    award, case, approver, _ = _approved_award(api_client, user, role_employee, product, supplier)
    _approve(api_client, approver, case)
    purchase_order = PurchaseOrder.objects.get(award=award)
    manager_role = Role.objects.create(role="po_manager")
    manager = _actor("Issue Manager", manager_role, "purchase_order.manage")

    api_client.force_authenticate(user=user)
    denied = api_client.post(
        f"/api/v1/purchase-orders/{purchase_order.id}/issue/", {"version": 1}, format="json"
    )
    api_client.force_authenticate(user=manager)
    stale = api_client.post(
        f"/api/v1/purchase-orders/{purchase_order.id}/issue/", {"version": 99}, format="json"
    )
    issued = api_client.post(
        f"/api/v1/purchase-orders/{purchase_order.id}/issue/", {"version": 1}, format="json"
    )

    assert denied.status_code == 403
    assert stale.status_code == 409
    assert issued.status_code == 200
    assert issued.data["status"] == "issued"
    assert issued.data["version"] == 2


@pytest.mark.django_db
def test_creating_and_issuing_po_only_updates_in_transit_snapshot(
    api_client, user, role_employee, product, supplier
):
    award, case, approver, _ = _approved_award(api_client, user, role_employee, product, supplier)
    _approve(api_client, approver, case)
    purchase_order = PurchaseOrder.objects.get(award=award)
    manager_role = Role.objects.create(role="inventory_safe_po_manager")
    manager = _actor("Inventory Safe Manager", manager_role, "purchase_order.manage")
    api_client.force_authenticate(user=manager)

    response = api_client.post(
        f"/api/v1/purchase-orders/{purchase_order.id}/issue/", {"version": 1}, format="json"
    )

    assert response.status_code == 200
    assert InventoryMovement.objects.count() == 0
    balance = InventoryBalance.objects.get(product=product)
    assert balance.on_hand_quantity == Decimal("0.000")
    assert balance.in_transit_quantity == Decimal("2.000")
