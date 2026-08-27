from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from apps.audit.models import AuditLog, ManualReviewQueue
from apps.core.models import Role, User
from apps.crm.models import Supplier
from apps.procurement.models import Quote
from services import manual_review_service as svc
from services.inquiry_resume_service import InquiryResumeError


@pytest.fixture
def admin_user(db, role_admin):
    return User.objects.create(
        name="Admin User",
        email="admin.user@groundtruth.demo",
        password="hashed-not-tested-here",
        role=role_admin,
    )


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

def test_claim_review_success(hallucination_review, admin_user):
    review = svc.claim_review(hallucination_review.id, admin_user.id)
    assert review.status == ManualReviewQueue.Status.CLAIMED
    assert review.user_id == admin_user.id


def test_claim_review_not_found(admin_user):
    with pytest.raises(svc.ManualReviewError):
        svc.claim_review(99999, admin_user.id)


def test_claim_review_user_not_found(hallucination_review):
    with pytest.raises(svc.ManualReviewError):
        svc.claim_review(hallucination_review.id, 99999)


def test_claim_review_non_admin_rejected(hallucination_review, employee_user):
    with pytest.raises(svc.ManualReviewError):
        svc.claim_review(hallucination_review.id, employee_user.id)


def test_claim_review_already_claimed_conflicts(hallucination_review, admin_user):
    svc.claim_review(hallucination_review.id, admin_user.id)
    with pytest.raises(svc.ManualReviewConflictError):
        svc.claim_review(hallucination_review.id, admin_user.id)


# ---- decide：共通驗證 ----

def test_decide_review_invalid_decision_value(hallucination_review, admin_user):
    svc.claim_review(hallucination_review.id, admin_user.id)
    with pytest.raises(svc.ManualReviewError):
        svc.decide_review(hallucination_review.id, admin_user.id, "maybe")


def test_decide_review_not_claimed_conflicts(hallucination_review, admin_user):
    with pytest.raises(svc.ManualReviewConflictError):
        svc.decide_review(hallucination_review.id, admin_user.id, ManualReviewQueue.Decision.APPROVED)


def test_decide_review_wrong_user_conflicts(hallucination_review, admin_user, db, role_admin):
    svc.claim_review(hallucination_review.id, admin_user.id)
    other_admin = User.objects.create(
        name="Other Admin", email="other.admin@groundtruth.demo",
        password="x", role=role_admin,
    )
    with pytest.raises(svc.ManualReviewConflictError):
        svc.decide_review(hallucination_review.id, other_admin.id, ManualReviewQueue.Decision.APPROVED)


# ---- decide：hallucination_mismatch ----

def test_decide_hallucination_approved_uses_system_template(hallucination_review, hallucination_quote, admin_user):
    svc.claim_review(hallucination_review.id, admin_user.id)
    review = svc.decide_review(
        hallucination_review.id, admin_user.id, ManualReviewQueue.Decision.APPROVED,
    )

    assert review.status == ManualReviewQueue.Status.RESOLVED
    assert review.decision == ManualReviewQueue.Decision.APPROVED

    hallucination_quote.refresh_from_db()
    assert hallucination_quote.status == Quote.Status.PENDING_APPROVAL
    assert "系統核定摘要" in hallucination_quote.ai_summary_text
    assert "測試供應商" in hallucination_quote.ai_summary_text

    assert AuditLog.objects.filter(quote=hallucination_quote, action_type="review_decision").exists()


def test_decide_hallucination_rejected_cancels_quote(hallucination_review, hallucination_quote, admin_user):
    svc.claim_review(hallucination_review.id, admin_user.id)
    svc.decide_review(hallucination_review.id, admin_user.id, ManualReviewQueue.Decision.REJECTED)

    hallucination_quote.refresh_from_db()
    assert hallucination_quote.status == Quote.Status.CANCELLED


def test_decide_hallucination_missing_quote_raises(db, admin_user):
    review = ManualReviewQueue.objects.create(
        quote=None,
        review_type=ManualReviewQueue.ReviewType.HALLUCINATION_MISMATCH,
        ai_generated_text="x",
        expected_value="{}",
    )
    svc.claim_review(review.id, admin_user.id)
    with pytest.raises(svc.ManualReviewError):
        svc.decide_review(review.id, admin_user.id, ManualReviewQueue.Decision.APPROVED)


# ---- decide：supplier_fuzzy_match ----

@patch("services.manual_review_service.trigger_resume")
def test_decide_fuzzy_match_approved_with_prefilled_supplier(mock_trigger, db, supplier, admin_user, user):
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
    assert result.resume_triggered is True
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
    assert result.resume_triggered is False


def test_decide_fuzzy_match_rejected_does_not_trigger_resume(fuzzy_review, admin_user):
    svc.claim_review(fuzzy_review.id, admin_user.id)
    with patch("services.manual_review_service.trigger_resume") as mock_trigger:
        result = svc.decide_review(fuzzy_review.id, admin_user.id, ManualReviewQueue.Decision.REJECTED)
    mock_trigger.assert_not_called()
    assert not hasattr(result, "resume_triggered")


@patch("services.manual_review_service.trigger_resume")
def test_decide_fuzzy_match_approved_with_explicit_supplier_override(mock_trigger, db, admin_user):
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
