"""FR-6b／FR-8：Gmail 通知服務測試。"""
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
import requests
from django.utils import timezone

from apps.audit.models import ManualReviewQueue
from apps.core.models import Permission, Role, RolePermission, User, UserRole
from apps.procurement.models import ApprovalCase, ApprovalPolicy, ApprovalStep, AwardDecision, PurchaseRequest, Rfq
from services import notification_service


@pytest.fixture
def review(db, user):
    return ManualReviewQueue.objects.create(
        quote=None,
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        raw_input_text="測試輸入",
        supplier=None,
        requester=user,
    )


class TestNotifyManualReviewCreated:
    def test_no_recipients_returns_false_without_calling_requests(self, review):
        with patch("services.notification_service.requests.post") as mock_post:
            result = notification_service.notify_manual_review_created(review)
        assert result is False
        mock_post.assert_not_called()

    def test_sends_to_all_active_manual_review_decide_holders(self, review, admin_user):
        with patch("services.notification_service.requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, raise_for_status=lambda: None)
            result = notification_service.notify_manual_review_created(review)
        assert result is True
        payload = mock_post.call_args.kwargs["json"]
        assert payload["recipients"] == [admin_user.email]
        assert str(review.id) in payload["subject"]

    def test_excludes_user_without_permission(self, review, admin_user, user):
        # `user` fixture (role_employee) 沒有 manual_review.decide 權限，不應收到通知。
        with patch("services.notification_service.requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, raise_for_status=lambda: None)
            notification_service.notify_manual_review_created(review)
        payload = mock_post.call_args.kwargs["json"]
        assert user.email not in payload["recipients"]

    def test_excludes_expired_role(self, review, admin_user):
        expired_role = Role.objects.create(role="expired_admin", approval_amount_limit=None)
        expired_user = User.objects.create(
            name="Expired Admin", email="expired@groundtruth.demo", password="x", role=expired_role,
        )
        permission = Permission.objects.get(code="manual_review.decide")
        RolePermission.objects.create(role=expired_role, permission=permission)
        UserRole.objects.create(
            user=expired_user,
            role=expired_role,
            valid_from=timezone.now() - timezone.timedelta(days=2),
            valid_until=timezone.now() - timezone.timedelta(days=1),
        )
        with patch("services.notification_service.requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, raise_for_status=lambda: None)
            notification_service.notify_manual_review_created(review)
        payload = mock_post.call_args.kwargs["json"]
        assert expired_user.email not in payload["recipients"]

    def test_excludes_not_yet_active_role(self, review, admin_user):
        future_role = Role.objects.create(role="future_admin", approval_amount_limit=None)
        future_user = User.objects.create(
            name="Future Admin", email="future@groundtruth.demo", password="x", role=future_role,
        )
        permission = Permission.objects.get(code="manual_review.decide")
        RolePermission.objects.create(role=future_role, permission=permission)
        UserRole.objects.create(
            user=future_user,
            role=future_role,
            valid_from=timezone.now() + timezone.timedelta(days=1),
            valid_until=None,
        )
        with patch("services.notification_service.requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, raise_for_status=lambda: None)
            notification_service.notify_manual_review_created(review)
        payload = mock_post.call_args.kwargs["json"]
        assert future_user.email not in payload["recipients"]

    def test_includes_reviews_page_link(self, review, admin_user, settings):
        settings.FRONTEND_BASE_URL = "http://localhost:5173"
        with patch("services.notification_service.requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, raise_for_status=lambda: None)
            notification_service.notify_manual_review_created(review)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["link"] == "http://localhost:5173/reviews"

    def test_connection_error_returns_false(self, review, admin_user):
        with patch("services.notification_service.requests.post", side_effect=requests.ConnectionError):
            result = notification_service.notify_manual_review_created(review)
        assert result is False

    def test_non_2xx_returns_false(self, review, admin_user):
        response = Mock(status_code=500)
        response.raise_for_status.side_effect = requests.HTTPError("500")
        with patch("services.notification_service.requests.post", return_value=response):
            result = notification_service.notify_manual_review_created(review)
        assert result is False


@pytest.fixture
def approval_role(db):
    return Role.objects.create(role="approver_finance", approval_amount_limit=None)


@pytest.fixture
def approval_case_with_step(db, approval_role, user):
    request = PurchaseRequest.objects.create(
        request_no="PR-NOTIFY-001", requester=user, purpose="通知測試",
    )
    rfq = Rfq.objects.create(rfq_no="RFQ-NOTIFY-001", request=request)
    award = AwardDecision.objects.create(rfq=rfq, revision=1, selected_by=user, selection_reason="測試")
    policy = ApprovalPolicy.objects.create(
        name="通知測試政策",
        currency="TWD",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("10000.00"),
        active_from=timezone.now(),
    )
    case = ApprovalCase.objects.create(
        award=award,
        policy=policy,
        requester=user,
        policy_snapshot={"name": policy.name},
        total_amount=Decimal("1000.00"),
        currency="TWD",
        submitted_at=timezone.now(),
    )
    step = ApprovalStep.objects.create(
        approval_case=case,
        sequence=1,
        step_type=ApprovalStep.StepType.AMOUNT_APPROVAL,
        role=approval_role,
        role_snapshot={},
    )
    return case, step


class TestNotifyApprovalStepActivated:
    def test_sends_to_all_users_with_target_role(self, approval_case_with_step, approval_role, db):
        _case, step = approval_case_with_step
        approver = User.objects.create(
            name="Finance Approver", email="finance@groundtruth.demo", password="x", role=approval_role,
        )
        UserRole.objects.create(user=approver, role=approval_role)
        with patch("services.notification_service.requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, raise_for_status=lambda: None)
            result = notification_service.notify_approval_step_activated(step)
        assert result is True
        payload = mock_post.call_args.kwargs["json"]
        assert payload["recipients"] == [approver.email]
        assert str(step.approval_case_id) in payload["subject"]

    def test_no_role_holders_returns_false(self, approval_case_with_step):
        _case, step = approval_case_with_step
        with patch("services.notification_service.requests.post") as mock_post:
            result = notification_service.notify_approval_step_activated(step)
        assert result is False
        mock_post.assert_not_called()

    def test_includes_approvals_page_link(self, approval_case_with_step, approval_role, settings):
        _case, step = approval_case_with_step
        approver = User.objects.create(
            name="Finance Approver 2", email="finance2@groundtruth.demo", password="x", role=approval_role,
        )
        UserRole.objects.create(user=approver, role=approval_role)
        settings.FRONTEND_BASE_URL = "http://localhost:5173"
        with patch("services.notification_service.requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, raise_for_status=lambda: None)
            notification_service.notify_approval_step_activated(step)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["link"] == "http://localhost:5173/approvals"


def _approve_step(step, user):
    now = timezone.now()
    step.status = ApprovalStep.Status.APPROVED
    step.claimed_by = user
    step.claimed_at = now
    step.decided_by = user
    step.decided_at = now
    step.decision_reason = "測試核准"
    step.save(
        update_fields=["status", "claimed_by", "claimed_at", "decided_by", "decided_at", "decision_reason"]
    )


class TestFirstClaimableStep:
    def test_returns_first_pending_step(self, approval_case_with_step):
        case, step = approval_case_with_step
        assert notification_service.first_claimable_step(case) == step

    def test_returns_next_pending_after_earlier_approved(self, approval_case_with_step, approval_role, user):
        case, step = approval_case_with_step
        _approve_step(step, user)
        second_step = ApprovalStep.objects.create(
            approval_case=case,
            sequence=2,
            step_type=ApprovalStep.StepType.AMOUNT_APPROVAL,
            role=approval_role,
            role_snapshot={},
        )
        assert notification_service.first_claimable_step(case) == second_step

    def test_returns_none_when_all_steps_approved(self, approval_case_with_step, user):
        case, step = approval_case_with_step
        _approve_step(step, user)
        assert notification_service.first_claimable_step(case) is None
