from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import IntegrityError

from apps.audit.models import ManualReviewQueue
from apps.core.models import Permission, RolePermission, User, UserRole
from apps.crm.models import Supplier
from apps.procurement.models import PurchaseRequest, Quote
from services import manual_review_service as svc
from services.inquiry_resume_service import RESUME_ERROR_DATA_INTEGRITY, InquiryResumeError


def _create_draft(user, *, request_no="PR-TEST-0001"):
    return PurchaseRequest.objects.create(
        request_no=request_no, requester=user, purpose="測試草稿", currency="TWD",
        source="manual_review_resume",
    )


@pytest.fixture
def admin_user(db, role_admin):
    user = User.objects.create(
        name="Admin User",
        email="admin.user@groundtruth.demo",
        password="hashed-not-tested-here",
        role=role_admin,
    )
    UserRole.objects.create(user=user, role=role_admin)
    for code in ("manual_review.claim", "manual_review.decide"):
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"name": code})
        RolePermission.objects.create(role=role_admin, permission=permission)
    return user


@pytest.fixture
def employee_user(db, user):
    return user  # conftest 的 user fixture 掛在 role_employee 底下


@pytest.fixture
def hallucination_quote(db, user, supplier, product):
    return Quote.objects.create(
        user=user,
        supplier=supplier,
        product=product,
        quantity=20,
        price=Decimal("1500.00"),
        total_amount=Decimal("30000.00"),
        currency="TWD",
        status=Quote.Status.PENDING_REVIEW,
    )


@pytest.fixture
def hallucination_review(db, hallucination_quote):
    return ManualReviewQueue.objects.create(
        quote=hallucination_quote,
        review_type=ManualReviewQueue.ReviewType.HALLUCINATION_MISMATCH,
        ai_generated_text="測試供應商採購測試產品，數量20，總金額30000元",
        expected_value=(
            '{"quantity": "20", "unit_price": "1500.00", "total_amount": "30000.00", '
            '"supplier_name": "測試供應商", "product_name": "測試產品"}'
        ),
    )


@pytest.fixture
def fuzzy_review(db, supplier):
    return ManualReviewQueue.objects.create(
        quote=None,
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        raw_input_text="跟優品科採購A產品",
        supplier=None,
    )


# ---- claim ----

def test_claim_review_success(fuzzy_review, admin_user):
    review = svc.claim_review(fuzzy_review.id, admin_user.id)
    assert review.status == ManualReviewQueue.Status.CLAIMED
    assert review.user_id == admin_user.id


def test_claim_review_not_found(admin_user):
    with pytest.raises(svc.ManualReviewError):
        svc.claim_review(99999, admin_user.id)


def test_claim_review_user_not_found(fuzzy_review):
    with pytest.raises(svc.ManualReviewError):
        svc.claim_review(fuzzy_review.id, 99999)


def test_claim_review_non_admin_rejected(fuzzy_review, employee_user):
    with pytest.raises(svc.ManualReviewError):
        svc.claim_review(fuzzy_review.id, employee_user.id)


def test_claim_review_already_claimed_conflicts(fuzzy_review, admin_user):
    svc.claim_review(fuzzy_review.id, admin_user.id)
    with pytest.raises(svc.ManualReviewConflictError):
        svc.claim_review(fuzzy_review.id, admin_user.id)


# ---- decide：共通驗證 ----

def test_decide_review_invalid_decision_value(fuzzy_review, admin_user):
    svc.claim_review(fuzzy_review.id, admin_user.id)
    with pytest.raises(svc.ManualReviewError):
        svc.decide_review(fuzzy_review.id, admin_user.id, "maybe")


def test_decide_review_not_claimed_conflicts(fuzzy_review, admin_user):
    with pytest.raises(svc.ManualReviewConflictError):
        svc.decide_review(fuzzy_review.id, admin_user.id, ManualReviewQueue.Decision.APPROVED)


def test_decide_review_wrong_user_conflicts(fuzzy_review, admin_user, db, role_admin):
    svc.claim_review(fuzzy_review.id, admin_user.id)
    other_admin = User.objects.create(
        name="Other Admin", email="other.admin@groundtruth.demo",
        password="x", role=role_admin,
    )
    UserRole.objects.create(user=other_admin, role=role_admin)
    with pytest.raises(svc.ManualReviewConflictError):
        svc.decide_review(fuzzy_review.id, other_admin.id, ManualReviewQueue.Decision.APPROVED)


# ---- decide：hallucination_mismatch ----

def test_decide_hallucination_approved_is_retired(hallucination_review, hallucination_quote, admin_user):
    with pytest.raises(svc.LegacyManualReviewRetiredError):
        svc.claim_review(hallucination_review.id, admin_user.id)
    hallucination_quote.refresh_from_db()
    assert hallucination_quote.status == Quote.Status.PENDING_REVIEW


def test_decide_hallucination_rejected_is_retired(hallucination_review, hallucination_quote, admin_user):
    with pytest.raises(svc.LegacyManualReviewRetiredError):
        svc.claim_review(hallucination_review.id, admin_user.id)
    hallucination_quote.refresh_from_db()
    assert hallucination_quote.status == Quote.Status.PENDING_REVIEW


def test_decide_hallucination_missing_quote_raises(db, admin_user):
    review = ManualReviewQueue.objects.create(
        quote=None,
        review_type=ManualReviewQueue.ReviewType.HALLUCINATION_MISMATCH,
        ai_generated_text="x",
        expected_value="{}",
    )
    with pytest.raises(svc.LegacyManualReviewRetiredError):
        svc.claim_review(review.id, admin_user.id)


# ---- decide：supplier_fuzzy_match ----

@patch("services.manual_review_service.trigger_resume")
def test_decide_fuzzy_match_approved_with_prefilled_supplier(mock_trigger, db, supplier, admin_user, user):
    draft = _create_draft(user)
    mock_trigger.return_value = (draft, None)
    review = ManualReviewQueue.objects.create(
        quote=None,
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        raw_input_text="跟優品科採購A產品",
        supplier=supplier,
        requester=user,
    )
    svc.claim_review(review.id, admin_user.id)
    result = svc.decide_review(review.id, admin_user.id, ManualReviewQueue.Decision.APPROVED)

    assert result.status == ManualReviewQueue.Status.RESOLVED
    assert result.supplier_id == supplier.id
    assert result.resume_status == ManualReviewQueue.ResumeStatus.SUCCEEDED
    assert result.resume_error_code is None
    assert result.created_purchase_request_id == draft.id
    mock_trigger.assert_called_once_with(
        review_id=review.id, raw_input_text="跟優品科採購A產品",
        requester_id=user.id, supplier_id=supplier.id,
    )


@patch("services.manual_review_service.trigger_resume")
def test_decide_fuzzy_match_approved_resume_failure_does_not_fail_decision(mock_trigger, db, supplier, admin_user):
    mock_trigger.side_effect = InquiryResumeError("boom")
    review = ManualReviewQueue.objects.create(
        quote=None,
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        raw_input_text="跟優品科採購A產品",
        supplier=supplier,
    )
    svc.claim_review(review.id, admin_user.id)
    result = svc.decide_review(review.id, admin_user.id, ManualReviewQueue.Decision.APPROVED)

    assert result.status == ManualReviewQueue.Status.RESOLVED
    assert result.resume_status == ManualReviewQueue.ResumeStatus.FAILED
    assert result.resume_error_code == RESUME_ERROR_DATA_INTEGRITY
    assert result.created_purchase_request_id is None


def test_decide_fuzzy_match_rejected_does_not_trigger_resume(fuzzy_review, admin_user):
    svc.claim_review(fuzzy_review.id, admin_user.id)
    with patch("services.manual_review_service.trigger_resume") as mock_trigger:
        result = svc.decide_review(fuzzy_review.id, admin_user.id, ManualReviewQueue.Decision.REJECTED)
    mock_trigger.assert_not_called()
    assert result.resume_status == ManualReviewQueue.ResumeStatus.NOT_APPLICABLE


@patch("services.manual_review_service.trigger_resume")
def test_decide_fuzzy_match_approved_with_explicit_supplier_override(mock_trigger, db, admin_user, user):
    draft = _create_draft(user)
    mock_trigger.return_value = (draft, None)
    supplier_a = Supplier.objects.create(name="優品科技", tier=Supplier.Tier.NORMAL)
    supplier_b = Supplier.objects.create(name="優品資訊", tier=Supplier.Tier.NORMAL)
    review = ManualReviewQueue.objects.create(
        quote=None,
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        raw_input_text="優品科技跟優品資訊我都有詢價",
        supplier=None,
    )
    svc.claim_review(review.id, admin_user.id)
    result = svc.decide_review(
        review.id, admin_user.id, ManualReviewQueue.Decision.APPROVED, supplier_id=supplier_b.id,
    )
    assert result.supplier_id == supplier_b.id
    assert supplier_a.id != supplier_b.id
    mock_trigger.assert_called_once()


def test_decide_fuzzy_match_approved_without_supplier_raises(fuzzy_review, admin_user):
    svc.claim_review(fuzzy_review.id, admin_user.id)
    with pytest.raises(svc.ManualReviewError):
        svc.decide_review(fuzzy_review.id, admin_user.id, ManualReviewQueue.Decision.APPROVED)


def test_decide_fuzzy_match_rejected_leaves_supplier_null(fuzzy_review, admin_user):
    svc.claim_review(fuzzy_review.id, admin_user.id)
    result = svc.decide_review(fuzzy_review.id, admin_user.id, ManualReviewQueue.Decision.REJECTED)
    assert result.status == ManualReviewQueue.Status.RESOLVED
    assert result.supplier_id is None


# ---- ManualReviewQueue CheckConstraint（2026-09-02 新增：持久化續傳狀態） ----

@pytest.mark.django_db
def test_resume_status_succeeded_without_purchase_request_violates_constraint(fuzzy_review):
    fuzzy_review.resume_status = ManualReviewQueue.ResumeStatus.SUCCEEDED
    with pytest.raises(IntegrityError):
        fuzzy_review.save(update_fields=["resume_status"])


@pytest.mark.django_db
def test_resume_status_failed_without_error_code_violates_constraint(fuzzy_review):
    fuzzy_review.resume_status = ManualReviewQueue.ResumeStatus.FAILED
    with pytest.raises(IntegrityError):
        fuzzy_review.save(update_fields=["resume_status"])


@pytest.mark.django_db
def test_resume_status_failed_with_error_code_is_valid(fuzzy_review):
    fuzzy_review.resume_status = ManualReviewQueue.ResumeStatus.FAILED
    fuzzy_review.resume_error_code = "parse_failed"
    fuzzy_review.save(update_fields=["resume_status", "resume_error_code"])
    fuzzy_review.refresh_from_db()
    assert fuzzy_review.resume_status == ManualReviewQueue.ResumeStatus.FAILED


# ---- retry_resume（2026-09-02 新增：持久化續傳狀態與重試） ----

def test_retry_resume_success_after_prior_failure(db, supplier, admin_user, user):
    review = ManualReviewQueue.objects.create(
        quote=None,
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        raw_input_text="跟優品科採購A產品",
        supplier=supplier,
        requester=user,
    )
    with patch("services.manual_review_service.trigger_resume") as mock_trigger:
        mock_trigger.side_effect = InquiryResumeError("boom")
        svc.claim_review(review.id, admin_user.id)
        failed = svc.decide_review(review.id, admin_user.id, ManualReviewQueue.Decision.APPROVED)
    assert failed.resume_status == ManualReviewQueue.ResumeStatus.FAILED

    draft = _create_draft(user, request_no="PR-TEST-RETRY-0001")
    with patch("services.manual_review_service.trigger_resume") as mock_trigger:
        mock_trigger.return_value = (draft, None)
        result = svc.retry_resume(review.id, admin_user.id)

    assert result.resume_status == ManualReviewQueue.ResumeStatus.SUCCEEDED
    assert result.resume_error_code is None
    assert result.created_purchase_request_id == draft.id
    mock_trigger.assert_called_once_with(
        review_id=review.id, raw_input_text="跟優品科採購A產品",
        requester_id=user.id, supplier_id=supplier.id,
    )


def test_retry_resume_wrong_status_conflicts(db, supplier, admin_user, user):
    review = ManualReviewQueue.objects.create(
        quote=None,
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        raw_input_text="跟優品科採購A產品",
        supplier=supplier,
        requester=user,
    )
    draft = _create_draft(user, request_no="PR-TEST-RETRY-0002")
    with patch("services.manual_review_service.trigger_resume") as mock_trigger:
        mock_trigger.return_value = (draft, None)
        svc.claim_review(review.id, admin_user.id)
        result = svc.decide_review(review.id, admin_user.id, ManualReviewQueue.Decision.APPROVED)
    assert result.resume_status == ManualReviewQueue.ResumeStatus.SUCCEEDED

    with pytest.raises(svc.ManualReviewConflictError):
        svc.retry_resume(review.id, admin_user.id)


def test_retry_resume_wrong_review_type_rejected(hallucination_review, admin_user):
    with pytest.raises(svc.LegacyManualReviewRetiredError):
        svc.retry_resume(hallucination_review.id, admin_user.id)


def test_retry_resume_not_approved_rejected(fuzzy_review, admin_user):
    svc.claim_review(fuzzy_review.id, admin_user.id)
    svc.decide_review(fuzzy_review.id, admin_user.id, ManualReviewQueue.Decision.REJECTED)
    with pytest.raises(svc.ManualReviewError):
        svc.retry_resume(fuzzy_review.id, admin_user.id)


def test_retry_resume_not_found_raises(admin_user):
    with pytest.raises(svc.ManualReviewError):
        svc.retry_resume(99999, admin_user.id)


def test_retry_resume_non_admin_rejected(db, supplier, admin_user, user):
    review = ManualReviewQueue.objects.create(
        quote=None,
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        raw_input_text="跟優品科採購A產品",
        supplier=supplier,
        requester=user,
    )
    with patch("services.manual_review_service.trigger_resume") as mock_trigger:
        mock_trigger.side_effect = InquiryResumeError("boom")
        svc.claim_review(review.id, admin_user.id)
        svc.decide_review(review.id, admin_user.id, ManualReviewQueue.Decision.APPROVED)
    with pytest.raises(svc.ManualReviewError):
        svc.retry_resume(review.id, user.id)
