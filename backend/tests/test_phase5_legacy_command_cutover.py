from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.audit.models import ManualReviewQueue
from apps.procurement.models import Approval, Quote
from services.authentication_service import issue_token_pair


def bearer(user):
    access, _, _ = issue_token_pair(user)
    return f"Bearer {access}"


@pytest.mark.django_db
@patch("services.inquiry_service.trigger_inquiry")
def test_legacy_inquiry_trigger_is_retired_without_calling_upstream(
    trigger, api_client, user,
):
    response = api_client.post(
        "/api/v1/inquiries/trigger/",
        {"raw_text": "幫我訂 5 個 A產品-辦公椅"},
        HTTP_AUTHORIZATION=bearer(user),
    )

    assert response.status_code == 410
    assert response.data == {
        "detail": "舊版詢價建單流程已停用，請改用採購需求流程",
        "code": "legacy_command_retired",
    }
    trigger.assert_not_called()


@pytest.mark.django_db
def test_legacy_quote_calculate_is_retired_without_creating_quote(
    api_client, user, supplier, product, settings,
):
    settings.INTERNAL_API_KEY = "test-internal-key"

    response = api_client.post(
        "/api/v1/quotes/calculate/",
        {
            "user_id": user.id,
            "product_id": product.id,
            "supplier_id": supplier.id,
            "quantity": 5,
        },
        HTTP_X_INTERNAL_API_KEY="test-internal-key",
    )

    assert response.status_code == 410
    assert response.data["code"] == "legacy_command_retired"
    assert not Quote.objects.exists()


@pytest.mark.django_db
def test_legacy_hallucination_verification_is_retired_without_mutation(
    api_client, user, supplier, product, settings,
):
    settings.INTERNAL_API_KEY = "test-internal-key"
    quote = Quote.objects.create(
        user=user,
        supplier=supplier,
        product=product,
        quantity=5,
        price=Decimal("1500.00"),
        total_amount=Decimal("7500.00"),
        currency="TWD",
        status=Quote.Status.PENDING_VERIFICATION,
    )

    response = api_client.post(
        "/api/v1/quotes/verify-hallucination/",
        {"quote_id": quote.id, "summary_text": "任意摘要"},
        HTTP_X_INTERNAL_API_KEY="test-internal-key",
    )

    assert response.status_code == 410
    assert response.data["code"] == "legacy_command_retired"
    quote.refresh_from_db()
    assert quote.status == Quote.Status.PENDING_VERIFICATION
    assert not Approval.objects.exists()
    assert not ManualReviewQueue.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "payload"),
    [
        ("claim", {}),
        ("decide", {"decision": "approved"}),
    ],
)
def test_legacy_approval_commands_are_retired_without_mutation(
    action, payload, api_client, user, supplier, product, role_employee,
):
    quote = Quote.objects.create(
        user=user,
        supplier=supplier,
        product=product,
        quantity=5,
        price=Decimal("1500.00"),
        total_amount=Decimal("7500.00"),
        currency="TWD",
        status=Quote.Status.PENDING_APPROVAL,
    )
    approval = Approval.objects.create(
        quote=quote,
        role=role_employee,
        approval_level=Approval.Level.SMALL,
    )

    response = api_client.post(
        f"/api/v1/approvals/{approval.id}/{action}/",
        payload,
        format="json",
        HTTP_AUTHORIZATION=bearer(user),
    )

    assert response.status_code == 410
    assert response.data["code"] == "legacy_command_retired"
    approval.refresh_from_db()
    assert approval.status == Approval.Status.PENDING
    assert approval.approver_id is None
