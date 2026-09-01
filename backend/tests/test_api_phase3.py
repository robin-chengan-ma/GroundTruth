from decimal import Decimal

import pytest

from apps.audit.models import ManualReviewQueue
from apps.core.models import User
from apps.procurement.models import Quote
from services.authentication_service import issue_token_pair


def bearer(user):
    access, _, _ = issue_token_pair(user)
    return f"Bearer {access}"

# ---- masking/mask/、masking/unmask/ ----

@pytest.mark.django_db
def test_mask_requires_internal_api_key(api_client, supplier, settings):
    settings.INTERNAL_API_KEY = "test-internal-key"
    resp = api_client.post("/api/v1/masking/mask/", {"raw_text": f"跟{supplier.name}採購"})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_mask_with_valid_key_masks_supplier(api_client, supplier, settings):
    settings.INTERNAL_API_KEY = "test-internal-key"
    resp = api_client.post(
        "/api/v1/masking/mask/",
        {"raw_text": f"跟{supplier.name}採購20個A產品"},
        HTTP_X_INTERNAL_API_KEY="test-internal-key",
    )
    assert resp.status_code == 200
    assert resp.data["outcome"] == "masked"
    assert supplier.name not in resp.data["masked_text"]


@pytest.mark.django_db
def test_mask_empty_raw_text_returns_400(api_client, settings):
    settings.INTERNAL_API_KEY = "test-internal-key"
    resp = api_client.post(
        "/api/v1/masking/mask/", {"raw_text": ""}, HTTP_X_INTERNAL_API_KEY="test-internal-key",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_unmask_restores_real_values(api_client, settings):
    settings.INTERNAL_API_KEY = "test-internal-key"
    resp = api_client.post(
        "/api/v1/masking/unmask/",
        {"masked_text": "跟SUP_001採購", "mapping": {"SUP_001": "優品科技"}},
        HTTP_X_INTERNAL_API_KEY="test-internal-key",
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["text"] == "跟優品科技採購"


# ---- quotes/verify-hallucination/ ----

@pytest.fixture
def verify_quote(db, user, supplier, product):
    return Quote.objects.create(
        user=user, supplier=supplier, product=product,
        quantity=20, price=Decimal("1500.00"), total_amount=Decimal("30000.00"),
        currency="TWD", status=Quote.Status.PENDING_VERIFICATION,
    )


@pytest.mark.django_db
def test_verify_hallucination_requires_internal_api_key(api_client, verify_quote):
    resp = api_client.post(
        "/api/v1/quotes/verify-hallucination/",
        {"quote_id": verify_quote.id, "summary_text": "x"},
    )
    assert resp.status_code == 401


# ---- manual-review-queue claim/decide ----

@pytest.fixture
def review_admin(db, role_admin):
    return User.objects.create(
        name="Review Admin", email="review.admin@groundtruth.demo",
        password="x", role=role_admin,
    )


@pytest.fixture
def review_for_claim(db, verify_quote):
    verify_quote.status = Quote.Status.PENDING_REVIEW
    verify_quote.save(update_fields=["status"])
    return ManualReviewQueue.objects.create(
        quote=verify_quote,
        review_type=ManualReviewQueue.ReviewType.HALLUCINATION_MISMATCH,
        ai_generated_text="x",
        expected_value=(
            '{"quantity": "20", "unit_price": "1500.00", "total_amount": "30000.00", '
            f'"supplier_name": "{verify_quote.supplier.name}", "product_name": "{verify_quote.product.name}"}}'
        ),
    )


@pytest.mark.django_db
def test_claim_action_success(api_client, review_for_claim, review_admin):
    resp = api_client.post(
        f"/api/v1/manual-review-queue/{review_for_claim.id}/claim/",
        HTTP_AUTHORIZATION=bearer(review_admin),
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "claimed"


@pytest.mark.django_db
def test_claim_action_requires_login(api_client, review_for_claim):
    resp = api_client.post(f"/api/v1/manual-review-queue/{review_for_claim.id}/claim/", {})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_claim_action_double_claim_conflicts(api_client, review_for_claim, review_admin):
    authorization = bearer(review_admin)
    api_client.post(
        f"/api/v1/manual-review-queue/{review_for_claim.id}/claim/", HTTP_AUTHORIZATION=authorization
    )
    resp = api_client.post(
        f"/api/v1/manual-review-queue/{review_for_claim.id}/claim/", HTTP_AUTHORIZATION=authorization,
    )
    assert resp.status_code == 409


@pytest.mark.django_db
def test_decide_action_missing_fields(api_client, review_for_claim, review_admin):
    authorization = bearer(review_admin)
    api_client.post(
        f"/api/v1/manual-review-queue/{review_for_claim.id}/claim/", HTTP_AUTHORIZATION=authorization
    )
    resp = api_client.post(
        f"/api/v1/manual-review-queue/{review_for_claim.id}/decide/", HTTP_AUTHORIZATION=authorization,
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_decide_action_approved_advances_quote(api_client, review_for_claim, review_admin, verify_quote):
    authorization = bearer(review_admin)
    api_client.post(
        f"/api/v1/manual-review-queue/{review_for_claim.id}/claim/", HTTP_AUTHORIZATION=authorization
    )
    resp = api_client.post(
        f"/api/v1/manual-review-queue/{review_for_claim.id}/decide/",
        {"decision": "approved"},
        HTTP_AUTHORIZATION=authorization,
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "resolved"

    verify_quote.refresh_from_db()
    assert verify_quote.status == Quote.Status.PENDING_APPROVAL


@pytest.mark.django_db
def test_decide_action_not_claimed_conflicts(api_client, review_for_claim, review_admin):
    resp = api_client.post(
        f"/api/v1/manual-review-queue/{review_for_claim.id}/decide/",
        {"decision": "approved"},
        HTTP_AUTHORIZATION=bearer(review_admin),
    )
    assert resp.status_code == 409
