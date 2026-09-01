from decimal import Decimal

import pytest
from django.contrib.auth.hashers import check_password

from apps.audit.models import ManualReviewQueue
from apps.core.models import Role, User
from apps.procurement.models import Quote
from services.approval_routing_service import route_quote
from services.authentication_service import issue_token_pair


def bearer(user):
    access, _, _ = issue_token_pair(user)
    return f"Bearer {access}"


@pytest.mark.django_db
def test_inquiry_requires_jwt(api_client):
    response = api_client.post("/api/v1/inquiries/trigger/", {"raw_text": "採購測試"})
    assert response.status_code == 401


@pytest.mark.django_db
def test_employee_quote_list_only_contains_own_quotes(api_client, user, supplier, product, role_employee):
    own = Quote.objects.create(
        user=user, supplier=supplier, product=product, quantity=1, price=10, total_amount=10, currency="TWD"
    )
    other_user = User.objects.create(name="Other", email="other@example.com", password="x", role=role_employee)
    Quote.objects.create(
        user=other_user, supplier=supplier, product=product, quantity=1, price=20, total_amount=20, currency="TWD"
    )

    response = api_client.get("/api/v1/quotes/", HTTP_AUTHORIZATION=bearer(user))

    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [own.id]


@pytest.mark.django_db
def test_approver_can_claim_and_decide_routed_approval(api_client, user, supplier, product):
    role = Role.objects.create(role="approver_10k", approval_amount_limit=Decimal(10000))
    approver = User.objects.create(name="Approver", email="approver@example.com", password="x", role=role)
    quote = Quote.objects.create(
        user=user,
        supplier=supplier,
        product=product,
        quantity=1,
        price=5000,
        total_amount=5000,
        currency="TWD",
        status=Quote.Status.PENDING_APPROVAL,
    )
    approval = route_quote(quote)
    authorization = bearer(approver)

    claim = api_client.post(f"/api/v1/approvals/{approval.id}/claim/", HTTP_AUTHORIZATION=authorization)
    decide = api_client.post(
        f"/api/v1/approvals/{approval.id}/decide/",
        {"decision": "approved"},
        HTTP_AUTHORIZATION=authorization,
    )

    assert claim.status_code == 200
    assert decide.status_code == 200
    assert decide.data["status"] == "approved"


@pytest.mark.django_db
def test_admin_cannot_claim_other_role_approval(api_client, user, supplier, product, role_admin):
    Role.objects.create(role="approver_10k", approval_amount_limit=Decimal(10000))
    admin = User.objects.create(name="Admin", email="admin@example.com", password="x", role=role_admin)
    quote = Quote.objects.create(
        user=user,
        supplier=supplier,
        product=product,
        quantity=1,
        price=5000,
        total_amount=5000,
        currency="TWD",
        status=Quote.Status.PENDING_APPROVAL,
    )
    approval = route_quote(quote)

    response = api_client.post(
        f"/api/v1/approvals/{approval.id}/claim/", HTTP_AUTHORIZATION=bearer(admin)
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_requester_can_withdraw_through_api(api_client, user, supplier, product):
    Role.objects.create(role="approver_10k", approval_amount_limit=Decimal(10000))
    quote = Quote.objects.create(
        user=user,
        supplier=supplier,
        product=product,
        quantity=1,
        price=5000,
        total_amount=5000,
        currency="TWD",
        status=Quote.Status.PENDING_APPROVAL,
    )
    route_quote(quote)

    response = api_client.post(
        f"/api/v1/quotes/{quote.id}/withdraw/", HTTP_AUTHORIZATION=bearer(user)
    )

    assert response.status_code == 200
    assert response.data["status"] == "cancelled"


@pytest.mark.django_db
def test_manual_review_requires_admin(api_client, user, role_admin):
    admin = User.objects.create(name="Admin", email="admin@example.com", password="x", role=role_admin)
    ManualReviewQueue.objects.create(review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH)

    employee_response = api_client.get(
        "/api/v1/manual-review-queue/", HTTP_AUTHORIZATION=bearer(user)
    )
    admin_response = api_client.get(
        "/api/v1/manual-review-queue/", HTTP_AUTHORIZATION=bearer(admin)
    )

    assert employee_response.status_code == 403
    assert admin_response.status_code == 200


@pytest.mark.django_db
def test_admin_user_crud_hashes_password(api_client, role_admin, role_employee):
    admin = User.objects.create(
        name="Admin", email="admin@example.com", password="unused", role=role_admin
    )
    authorization = bearer(admin)

    created = api_client.post(
        "/api/v1/users/",
        {
            "name": "New Employee",
            "email": "new@example.com",
            "password": "initial-secret",
            "role": role_employee.id,
        },
        format="json",
        HTTP_AUTHORIZATION=authorization,
    )

    assert created.status_code == 201
    created_user = User.objects.get(pk=created.data["id"])
    assert created_user.password != "initial-secret"
    assert check_password("initial-secret", created_user.password)

    updated = api_client.patch(
        f"/api/v1/users/{created_user.id}/",
        {"password": "rotated-secret"},
        format="json",
        HTTP_AUTHORIZATION=authorization,
    )

    assert updated.status_code == 200
    created_user.refresh_from_db()
    assert check_password("rotated-secret", created_user.password)
