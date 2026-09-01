from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.core.models import Permission, Role, RolePermission, User, UserRole
from apps.procurement.models import (
    ApprovalCase,
    ApprovalPolicy,
    ApprovalPolicyStep,
    ApprovalStep,
    AwardDecision,
    AwardLine,
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


def _actor(name, role, *permissions):
    user = User.objects.create(
        name=name,
        email=f"{name.lower().replace(' ', '.')}@example.invalid",
        password="not-a-real-password-hash",
        role=role,
    )
    _grant(user, role, *permissions)
    return user


def _award_context(requester, product, supplier, *, waiver_by=None):
    request = PurchaseRequest.objects.create(
        request_no=f"PR-C5-2-{requester.id}",
        requester=requester,
        status=PurchaseRequest.Status.AWARDING,
        purpose="C5-2 簽核測試",
    )
    item = PurchaseRequestItem.objects.create(
        request=request,
        line_no=1,
        product=product,
        description_snapshot="企業用辦公椅",
        quantity=Decimal("2.000"),
        unit_of_measure="EA",
    )
    rfq = Rfq.objects.create(
        rfq_no=f"RFQ-C5-2-{requester.id}",
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
    invitation = RfqSupplier.objects.create(
        rfq=rfq,
        supplier=supplier,
        status=RfqSupplier.Status.RESPONDED,
        invited_at=timezone.now(),
        responded_at=timezone.now(),
    )
    quote = SupplierQuote.objects.create(
        quote_no=f"SQ-C5-2-{requester.id}",
        rfq_supplier=invitation,
        status=SupplierQuote.Status.ACCEPTED_FOR_EVALUATION,
        currency="TWD",
        exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("200.00"),
        landed_total_twd=Decimal("200.00"),
        valid_until=timezone.now() + timedelta(days=7),
        submitted_at=timezone.now(),
    )
    quote_item = SupplierQuoteItem.objects.create(
        supplier_quote=quote,
        request_item=item,
        quantity=Decimal("2.000"),
        unit_price=Decimal("100.00"),
        subtotal=Decimal("200.00"),
        lead_time_days=7,
    )
    waiver = None
    if waiver_by is not None:
        requirement = RequestItemRequirement.objects.create(
            request_item=item,
            code="fireproof",
            label="防火認證",
            data_type="boolean",
            operator="equals",
            expected_value=True,
            is_mandatory=True,
        )
        waiver = QuoteRequirementResult.objects.create(
            quote_item=quote_item,
            requirement=requirement,
            result=QuoteRequirementResult.Result.WAIVED,
            evidence={"provided": False},
            waiver_reason="緊急替代品已取得原始核准",
            waived_by=waiver_by,
            waived_at=timezone.now(),
        )
    award = AwardDecision.objects.create(
        rfq=rfq,
        selected_by=requester,
        selection_reason="",
    )
    AwardLine.objects.create(
        award=award,
        request_item=item,
        supplier_quote_item=quote_item,
        awarded_quantity=Decimal("2.000"),
        unit_price_snapshot=Decimal("100.00"),
        amount_snapshot=Decimal("200.00"),
    )
    return award, waiver


def _policy(amount_role, waiver_role):
    policy = ApprovalPolicy.objects.create(
        name="C5-2 TWD 政策",
        currency="TWD",
        min_amount=Decimal("0.00"),
        max_amount=None,
        active_from=timezone.now() - timedelta(days=1),
        waiver_role=waiver_role,
    )
    ApprovalPolicyStep.objects.create(
        policy=policy,
        sequence=1,
        role=amount_role,
        decision_mode="any_one",
    )
    return policy


def _submit(api_client, requester, award):
    api_client.force_authenticate(user=requester)
    return api_client.post(f"/api/v1/award-decisions/{award.id}/submit/", {}, format="json")


@pytest.mark.django_db
def test_award_submit_atomically_creates_amount_approval_case(api_client, user, role_employee, product, supplier):
    amount_role = Role.objects.create(role="amount_approver")
    waiver_role = Role.objects.create(role="exception_reviewer")
    _grant(user, role_employee, "award.recommend")
    policy = _policy(amount_role, waiver_role)
    award, _ = _award_context(user, product, supplier)

    response = _submit(api_client, user, award)

    assert response.status_code == 200
    case = ApprovalCase.objects.get(award=award)
    assert response.data["approval_case_id"] == case.id
    assert case.policy == policy
    assert case.total_amount == Decimal("200.00")
    assert list(case.steps.values_list("step_type", "role_id")) == [("amount_approval", amount_role.id)]
    assert AuditLog.objects.filter(action_type="approval_case_created").exists()


@pytest.mark.django_db
def test_waiver_step_is_created_before_amount_step_and_links_results(
    api_client, user, role_employee, product, supplier
):
    amount_role = Role.objects.create(role="amount_approver")
    waiver_role = Role.objects.create(role="exception_reviewer")
    original = _actor("Original Waiver", waiver_role, "requirement.waive", "approval.decide")
    _grant(user, role_employee, "award.recommend")
    _policy(amount_role, waiver_role)
    award, waiver = _award_context(user, product, supplier, waiver_by=original)

    response = _submit(api_client, user, award)

    assert response.status_code == 200
    steps = list(ApprovalCase.objects.get(award=award).steps.order_by("sequence"))
    assert [step.step_type for step in steps] == ["waiver_exception", "amount_approval"]
    assert list(steps[0].waivers.values_list("quote_requirement_result_id", flat=True)) == [waiver.id]


@pytest.mark.django_db
def test_original_waiver_approver_cannot_claim_exception_step(
    api_client, user, role_employee, product, supplier
):
    amount_role = Role.objects.create(role="amount_approver")
    waiver_role = Role.objects.create(role="exception_reviewer")
    original = _actor(
        "Original Reviewer", waiver_role,
        "requirement.waive", "approval.claim", "approval.decide", "approval.read_all",
    )
    _grant(user, role_employee, "award.recommend")
    _policy(amount_role, waiver_role)
    award, _ = _award_context(user, product, supplier, waiver_by=original)
    _submit(api_client, user, award)
    step = ApprovalCase.objects.get(award=award).steps.get(step_type="waiver_exception")
    api_client.force_authenticate(user=original)

    response = api_client.post(f"/api/v1/approval-steps/{step.id}/claim/", {}, format="json")

    assert response.status_code == 403
    step.refresh_from_db()
    assert step.status == ApprovalStep.Status.PENDING


@pytest.mark.django_db
def test_requester_cannot_claim_own_approval(api_client, user, role_employee, product, supplier):
    waiver_role = Role.objects.create(role="exception_reviewer")
    _grant(user, role_employee, "award.recommend", "approval.claim", "approval.decide", "approval.read_all")
    _policy(role_employee, waiver_role)
    award, _ = _award_context(user, product, supplier)
    _submit(api_client, user, award)
    step = ApprovalCase.objects.get(award=award).steps.get()

    response = api_client.post(f"/api/v1/approval-steps/{step.id}/claim/", {}, format="json")

    assert response.status_code == 403


@pytest.mark.django_db
def test_later_step_cannot_be_claimed_before_previous_step(api_client, user, role_employee, product, supplier):
    amount_role = Role.objects.create(role="amount_approver")
    waiver_role = Role.objects.create(role="exception_reviewer")
    original = _actor("First Waiver", waiver_role, "requirement.waive")
    amount_approver = _actor(
        "Amount Approver", amount_role, "approval.claim", "approval.decide", "approval.read_all"
    )
    _grant(user, role_employee, "award.recommend")
    _policy(amount_role, waiver_role)
    award, _ = _award_context(user, product, supplier, waiver_by=original)
    _submit(api_client, user, award)
    amount_step = ApprovalCase.objects.get(award=award).steps.get(step_type="amount_approval")
    api_client.force_authenticate(user=amount_approver)

    response = api_client.post(f"/api/v1/approval-steps/{amount_step.id}/claim/", {}, format="json")

    assert response.status_code == 409


@pytest.mark.django_db
def test_claim_conflict_and_full_approval_flow(api_client, user, role_employee, product, supplier):
    amount_role = Role.objects.create(role="amount_approver")
    waiver_role = Role.objects.create(role="exception_reviewer")
    original = _actor("Waiver One", waiver_role, "requirement.waive")
    reviewer = _actor(
        "Waiver Two", waiver_role,
        "requirement.waive", "approval.claim", "approval.decide", "approval.read_all",
    )
    competitor = _actor(
        "Waiver Three", waiver_role,
        "requirement.waive", "approval.claim", "approval.decide", "approval.read_all",
    )
    amount_approver = _actor(
        "Final Approver", amount_role, "approval.claim", "approval.decide", "approval.read_all"
    )
    _grant(user, role_employee, "award.recommend")
    _policy(amount_role, waiver_role)
    award, _ = _award_context(user, product, supplier, waiver_by=original)
    _submit(api_client, user, award)
    case = ApprovalCase.objects.get(award=award)
    waiver_step, amount_step = list(case.steps.order_by("sequence"))

    api_client.force_authenticate(user=reviewer)
    assert api_client.post(f"/api/v1/approval-steps/{waiver_step.id}/claim/", {}).status_code == 200
    api_client.force_authenticate(user=competitor)
    assert api_client.post(f"/api/v1/approval-steps/{waiver_step.id}/claim/", {}).status_code == 409
    api_client.force_authenticate(user=reviewer)
    assert api_client.post(
        f"/api/v1/approval-steps/{waiver_step.id}/decide/",
        {"decision": "approved", "reason": "獨立審查後同意例外"}, format="json",
    ).status_code == 200
    api_client.force_authenticate(user=amount_approver)
    assert api_client.post(f"/api/v1/approval-steps/{amount_step.id}/claim/", {}).status_code == 200
    decided = api_client.post(
        f"/api/v1/approval-steps/{amount_step.id}/decide/",
        {"decision": "approved", "reason": "金額與預算符合"}, format="json",
    )

    assert decided.status_code == 200
    case.refresh_from_db()
    award.refresh_from_db()
    assert case.status == ApprovalCase.Status.APPROVED
    assert award.status == AwardDecision.Status.APPROVED
    assert award.rfq.request.__class__.objects.get(pk=award.rfq.request_id).status == PurchaseRequest.Status.ORDERED


@pytest.mark.django_db
def test_rejection_closes_case_and_rejects_request(api_client, user, role_employee, product, supplier):
    amount_role = Role.objects.create(role="amount_approver")
    waiver_role = Role.objects.create(role="exception_reviewer")
    approver = _actor(
        "Reject Approver", amount_role, "approval.claim", "approval.decide", "approval.read_all"
    )
    _grant(user, role_employee, "award.recommend")
    _policy(amount_role, waiver_role)
    award, _ = _award_context(user, product, supplier)
    _submit(api_client, user, award)
    case = ApprovalCase.objects.get(award=award)
    step = case.steps.get()
    api_client.force_authenticate(user=approver)
    api_client.post(f"/api/v1/approval-steps/{step.id}/claim/", {})

    response = api_client.post(
        f"/api/v1/approval-steps/{step.id}/decide/",
        {"decision": "rejected", "reason": "預算不足"}, format="json",
    )

    assert response.status_code == 200
    case.refresh_from_db()
    award.refresh_from_db()
    assert case.status == ApprovalCase.Status.REJECTED
    assert award.status == AwardDecision.Status.REJECTED
    assert PurchaseRequest.objects.get(pk=award.rfq.request_id).status == PurchaseRequest.Status.REJECTED


@pytest.mark.django_db
def test_missing_policy_rolls_back_award_submission(api_client, user, role_employee, product, supplier):
    _grant(user, role_employee, "award.recommend")
    award, _ = _award_context(user, product, supplier)

    response = _submit(api_client, user, award)

    assert response.status_code == 409
    award.refresh_from_db()
    assert award.status == AwardDecision.Status.DRAFT
    assert PurchaseRequest.objects.get(pk=award.rfq.request_id).status == PurchaseRequest.Status.AWARDING
    assert not ApprovalCase.objects.filter(award=award).exists()


@pytest.mark.django_db
def test_approval_case_queue_is_scoped_by_active_role(api_client, user, role_employee, product, supplier):
    amount_role = Role.objects.create(role="amount_approver")
    waiver_role = Role.objects.create(role="exception_reviewer")
    approver = _actor("Queue Approver", amount_role, "approval.read_all")
    outsider_role = Role.objects.create(role="queue_outsider")
    outsider = _actor("Queue Outsider", outsider_role, "approval.read_all")
    _grant(user, role_employee, "award.recommend")
    _policy(amount_role, waiver_role)
    award, _ = _award_context(user, product, supplier)
    _submit(api_client, user, award)

    api_client.force_authenticate(user=approver)
    visible = api_client.get("/api/v1/approval-cases/")
    api_client.force_authenticate(user=outsider)
    hidden = api_client.get("/api/v1/approval-cases/")

    assert visible.status_code == 200
    assert [row["award_id"] for row in visible.data] == [award.id]
    assert visible.data[0]["purpose"] == "C5-2 簽核測試"
    assert hidden.status_code == 200
    assert hidden.data == []


@pytest.mark.django_db
def test_auditor_can_read_all_cases_without_business_decision_role(
    api_client, user, role_employee, product, supplier
):
    amount_role = Role.objects.create(role="amount_approver")
    waiver_role = Role.objects.create(role="exception_reviewer")
    audit_role = Role.objects.create(role="auditor")
    auditor = _actor("Audit Reader", audit_role, "audit.read")
    _grant(user, role_employee, "award.recommend")
    _policy(amount_role, waiver_role)
    award, _ = _award_context(user, product, supplier)
    _submit(api_client, user, award)
    api_client.force_authenticate(user=auditor)

    response = api_client.get("/api/v1/approval-cases/")

    assert response.status_code == 200
    assert [row["award_id"] for row in response.data] == [award.id]


@pytest.mark.django_db
def test_decision_requires_claim_and_nonempty_reason(api_client, user, role_employee, product, supplier):
    amount_role = Role.objects.create(role="amount_approver")
    waiver_role = Role.objects.create(role="exception_reviewer")
    approver = _actor(
        "Reason Approver", amount_role, "approval.claim", "approval.decide", "approval.read_all"
    )
    _grant(user, role_employee, "award.recommend")
    _policy(amount_role, waiver_role)
    award, _ = _award_context(user, product, supplier)
    _submit(api_client, user, award)
    step = ApprovalCase.objects.get(award=award).steps.get()
    api_client.force_authenticate(user=approver)

    unclaimed = api_client.post(
        f"/api/v1/approval-steps/{step.id}/decide/",
        {"decision": "approved", "reason": "預算符合"}, format="json",
    )
    api_client.post(f"/api/v1/approval-steps/{step.id}/claim/", {})
    empty_reason = api_client.post(
        f"/api/v1/approval-steps/{step.id}/decide/",
        {"decision": "approved", "reason": "  "}, format="json",
    )

    assert unclaimed.status_code == 409
    assert empty_reason.status_code == 400


@pytest.mark.django_db
def test_waiver_without_reviewer_role_rolls_back_submission(
    api_client, user, role_employee, product, supplier
):
    amount_role = Role.objects.create(role="amount_approver")
    waiver_role = Role.objects.create(role="exception_reviewer")
    original = _actor("Unrouted Waiver", waiver_role, "requirement.waive")
    _grant(user, role_employee, "award.recommend")
    policy = _policy(amount_role, waiver_role)
    policy.waiver_role = None
    policy.save(update_fields=["waiver_role", "updated_at"])
    award, _ = _award_context(user, product, supplier, waiver_by=original)

    response = _submit(api_client, user, award)

    assert response.status_code == 409
    award.refresh_from_db()
    assert award.status == AwardDecision.Status.DRAFT


@pytest.mark.django_db
def test_all_decision_mode_is_rejected_without_partial_case(
    api_client, user, role_employee, product, supplier
):
    amount_role = Role.objects.create(role="amount_approver")
    waiver_role = Role.objects.create(role="exception_reviewer")
    _grant(user, role_employee, "award.recommend")
    policy = _policy(amount_role, waiver_role)
    policy.steps.update(decision_mode="all")
    award, _ = _award_context(user, product, supplier)

    response = _submit(api_client, user, award)

    assert response.status_code == 409
    assert not ApprovalCase.objects.filter(award=award).exists()
