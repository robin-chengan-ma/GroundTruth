from decimal import Decimal

import pytest
from django.utils import timezone

from api.core.permissions import HasPermissionCode
from apps.audit.models import ManualReviewQueue
from apps.core.models import Permission, RolePermission, UserRole
from apps.erp.models import Inventory
from apps.procurement.models import (
    ApprovalCase,
    ApprovalPolicy,
    ApprovalStep,
    AwardLine,
    PurchaseRequest,
    Quote,
)
from services import approval_case_service, manual_review_service
from services.purchase_request_draft_service import withdraw_request
from tests.test_phase4_1_award_approval_po import create_award_context


def _grant(user, role, code, name=None):
    UserRole.objects.get_or_create(user=user, role=role)
    permission, _ = Permission.objects.get_or_create(
        code=code, defaults={"name": name or code},
    )
    RolePermission.objects.get_or_create(role=role, permission=permission)


def test_rest_framework_defaults_to_fail_closed(settings):
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated",
    ]


@pytest.mark.django_db
def test_permission_class_uses_active_permission_codes(rf, user):
    request = rf.get("/")
    request.user = user
    permission = HasPermissionCode()

    class View:
        required_permission = "manual_review.decide"

    assert permission.has_permission(request, View()) is False


@pytest.mark.django_db
def test_legacy_hallucination_review_cannot_mutate_quote(
    user, supplier, product, role_admin,
):
    reviewer = user
    reviewer.role = role_admin
    reviewer.save(update_fields=["role"])
    UserRole.objects.create(user=reviewer, role=role_admin)
    permission = Permission.objects.create(
        code="manual_review.claim", name="認領人工複核",
    )
    RolePermission.objects.create(role=role_admin, permission=permission)
    quote = Quote.objects.create(
        user=user,
        supplier=supplier,
        product=product,
        quantity=5,
        price=Decimal("1500.00"),
        total_amount=Decimal("7500.00"),
        currency="TWD",
        status=Quote.Status.PENDING_REVIEW,
    )
    review = ManualReviewQueue.objects.create(
        quote=quote,
        review_type=ManualReviewQueue.ReviewType.HALLUCINATION_MISMATCH,
        expected_value="{}",
    )

    with pytest.raises(manual_review_service.LegacyManualReviewRetiredError):
        manual_review_service.claim_review(review.id, reviewer.id)

    quote.refresh_from_db()
    review.refresh_from_db()
    assert quote.status == Quote.Status.PENDING_REVIEW
    assert review.status == ManualReviewQueue.Status.UNCLAIMED


@pytest.mark.django_db
def test_inventory_read_requires_inventory_read_permission_code(
    api_client, user, role_employee, product,
):
    """master_data.read 不得替代 inventory.read，庫存查詢須有自己的權限碼。"""
    _grant(user, role_employee, "master_data.read", "讀取主檔")
    Inventory.objects.create(product=product, stock_qty=3, threshold=10)
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/inventory/")

    assert resp.status_code == 403


@pytest.mark.django_db
def test_inventory_read_allowed_with_inventory_read_permission_code(
    api_client, user, role_employee, product,
):
    _grant(user, role_employee, "inventory.read", "讀取庫存")
    Inventory.objects.create(product=product, stock_qty=3, threshold=10)
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/inventory/")

    assert resp.status_code == 200
    assert resp.data["count"] == 1


@pytest.fixture
def employee_user(db, role_employee):
    from apps.core.models import User

    return User.objects.create(
        name="Approver Employee",
        email="approver.employee@groundtruth.demo",
        password="hashed-not-tested-here",
        role=role_employee,
    )


def _build_pending_approval_case(user, supplier, product, role_employee, *, request_no):
    request, request_item, quote_item, award = create_award_context(
        user, supplier, product,
    )
    request.request_no = request_no
    request.status = PurchaseRequest.Status.APPROVAL
    request.save(update_fields=["request_no", "status"])
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
    policy = ApprovalPolicy.objects.create(
        name=f"{request_no} 政策",
        currency="TWD",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("10000.00"),
        active_from=timezone.now(),
    )
    case = ApprovalCase.objects.create(
        award=award,
        policy=policy,
        requester=request.requester,
        policy_snapshot={"name": policy.name},
        total_amount=Decimal("500.00"),
        currency="TWD",
        submitted_at=timezone.now(),
    )
    step = ApprovalStep.objects.create(
        approval_case=case,
        sequence=1,
        role=role_employee,
        role_snapshot={"role": role_employee.role, "decision_mode": "any_one"},
    )
    return request, case, step


@pytest.mark.django_db
def test_claim_step_rejected_after_request_withdrawn_cancels_case(
    user, supplier, product, role_employee, employee_user,
):
    """FR-9b／FR-18：撤回需求連動取消簽核案件後，該案件關卡不得再被認領。"""
    _grant(user, role_employee, "purchase_request.withdraw", "撤回採購需求")
    _grant(employee_user, role_employee, "approval.claim", "認領簽核案件")
    _grant(employee_user, role_employee, "approval.decide", "決議簽核案件")
    request, case, step = _build_pending_approval_case(
        user, supplier, product, role_employee, request_no="PR-WD-CLAIM-001",
    )

    withdraw_request(user, request.id, version=request.version, reason="需求異動")

    case.refresh_from_db()
    assert case.status == ApprovalCase.Status.CANCELLED
    with pytest.raises(approval_case_service.ApprovalWorkflowConflict):
        approval_case_service.claim_step(employee_user, step.id)


@pytest.mark.django_db
def test_decide_step_rejected_after_request_withdrawn_cancels_case(
    user, supplier, product, role_employee, employee_user,
):
    """已認領但尚未決議的關卡，於需求撤回取消案件後不得再決議。"""
    _grant(user, role_employee, "purchase_request.withdraw", "撤回採購需求")
    _grant(employee_user, role_employee, "approval.claim", "認領簽核案件")
    _grant(employee_user, role_employee, "approval.decide", "決議簽核案件")
    request, _case, step = _build_pending_approval_case(
        user, supplier, product, role_employee, request_no="PR-WD-DECIDE-001",
    )
    approval_case_service.claim_step(employee_user, step.id)

    withdraw_request(user, request.id, version=request.version, reason="需求異動")

    with pytest.raises(approval_case_service.ApprovalWorkflowConflict):
        approval_case_service.decide_step(
            employee_user, step.id, ApprovalStep.Status.APPROVED, "覆核通過",
        )


@pytest.mark.django_db
def test_withdraw_cancels_still_draft_award_without_violating_submission_time_constraint(
    user, supplier, product, role_employee,
):
    """award_decisions_submission_time_consistent：撤回時得標方案仍是 draft（尚未送出簽核）
    也必須能連動取消，不得違反『非 draft 必有 submitted_at』的 DB CHECK constraint。"""
    _grant(user, role_employee, "purchase_request.withdraw", "撤回採購需求")
    request, _, _, award = create_award_context(user, supplier, product)
    request.status = PurchaseRequest.Status.AWARDING
    request.save(update_fields=["status"])
    assert award.status == "draft"
    assert award.submitted_at is None

    updated = withdraw_request(user, request.id, version=request.version, reason="需求異動")

    assert updated.status == PurchaseRequest.Status.WITHDRAWN
    award.refresh_from_db()
    assert award.status == "cancelled"
    assert award.submitted_at is not None
