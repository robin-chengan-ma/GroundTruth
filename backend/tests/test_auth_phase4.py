import pytest
from django.contrib.auth.hashers import make_password
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from apps.core.models import Permission, RefreshSession, RolePermission, UserRole
from lib.jwt_authentication import BusinessJwtAuthentication
from services.authentication_service import AuthenticationError, issue_token_pair, rotate_refresh_token


@pytest.fixture
def login_user(user):
    user.password = make_password("correct-password")
    user.save(update_fields=["password"])
    return user


@pytest.mark.django_db
def test_login_sets_refresh_cookie_and_returns_access_token(api_client, login_user):
    response = api_client.post(
        "/api/v1/auth/login/",
        {"email": login_user.email, "password": "correct-password"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["access"]
    assert response.data["user"]["id"] == login_user.id
    assert response.data["user"]["role"] == "employee"
    assert response.data["user"]["permissions"] == []
    assert response.cookies["groundtruth_refresh"].value
    assert response.cookies["groundtruth_refresh"]["httponly"] is True
    assert RefreshSession.objects.filter(user=login_user, revoked_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_login_failure_does_not_reveal_account_existence(api_client, login_user):
    wrong_password = api_client.post(
        "/api/v1/auth/login/",
        {"email": login_user.email, "password": "wrong"},
        format="json",
    )
    missing_account = api_client.post(
        "/api/v1/auth/login/",
        {"email": "missing@example.com", "password": "wrong"},
        format="json",
    )

    assert wrong_password.status_code == 401
    assert missing_account.status_code == 401
    assert wrong_password.data == missing_account.data == {"detail": "帳號或密碼錯誤"}


@pytest.mark.django_db
def test_refresh_rotates_cookie_and_revokes_old_session(api_client, login_user):
    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": login_user.email, "password": "correct-password"},
        format="json",
    )
    old_cookie = login.cookies["groundtruth_refresh"].value
    csrf_token = login.cookies["csrftoken"].value

    response = api_client.post(
        "/api/v1/auth/refresh/",
        HTTP_X_CSRFTOKEN=csrf_token,
    )

    assert response.status_code == 200
    assert response.data["access"]
    assert response.cookies["groundtruth_refresh"].value != old_cookie
    assert RefreshSession.objects.filter(user=login_user, revoked_at__isnull=False).count() == 1
    assert RefreshSession.objects.filter(user=login_user, revoked_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_refresh_requires_matching_csrf_token(api_client, login_user):
    api_client.post(
        "/api/v1/auth/login/",
        {"email": login_user.email, "password": "correct-password"},
        format="json",
    )

    response = api_client.post("/api/v1/auth/refresh/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_logout_revokes_refresh_session(api_client, login_user):
    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": login_user.email, "password": "correct-password"},
        format="json",
    )
    csrf_token = login.cookies["csrftoken"].value

    response = api_client.post("/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=csrf_token)

    assert response.status_code == 204
    assert RefreshSession.objects.get(user=login_user).revoked_at is not None
    assert response.cookies["groundtruth_refresh"]["max-age"] == 0


@pytest.mark.django_db
def test_me_requires_access_token(api_client, login_user):
    anonymous = api_client.get("/api/v1/auth/me/")
    assert anonymous.status_code == 401

    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": login_user.email, "password": "correct-password"},
        format="json",
    )
    authenticated = api_client.get(
        "/api/v1/auth/me/",
        HTTP_AUTHORIZATION=f"Bearer {login.data['access']}",
    )

    assert authenticated.status_code == 200
    assert authenticated.data == {
        "id": login_user.id,
        "name": login_user.name,
        "email": login_user.email,
        "role": "employee",
        "permissions": [],
    }


@pytest.mark.django_db
def test_login_and_me_return_permissions_from_all_active_roles(api_client, login_user, role_admin):
    create_permission = Permission.objects.create(
        code="purchase_request.create", name="建立採購需求"
    )
    review_permission = Permission.objects.create(
        code="manual_review.decide", name="決議人工複核"
    )
    RolePermission.objects.create(role=login_user.role, permission=create_permission)
    RolePermission.objects.create(role=role_admin, permission=review_permission)
    UserRole.objects.create(user=login_user, role=login_user.role)
    UserRole.objects.create(user=login_user, role=role_admin)

    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": login_user.email, "password": "correct-password"},
        format="json",
    )
    me = api_client.get(
        "/api/v1/auth/me/",
        HTTP_AUTHORIZATION=f"Bearer {login.data['access']}",
    )

    expected = ["manual_review.decide", "purchase_request.create"]
    assert login.data["user"]["permissions"] == expected
    assert me.data["permissions"] == expected


@pytest.mark.django_db
@pytest.mark.parametrize("raw_token", [None, "not-a-jwt"])
def test_refresh_rejects_missing_or_invalid_token(raw_token):
    with pytest.raises(AuthenticationError):
        rotate_refresh_token(raw_token)


@pytest.mark.django_db
def test_refresh_rejects_replayed_token(api_client, login_user):
    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": login_user.email, "password": "correct-password"},
        format="json",
    )
    old_token = login.cookies["groundtruth_refresh"].value
    csrf_token = login.cookies["csrftoken"].value
    api_client.post("/api/v1/auth/refresh/", HTTP_X_CSRFTOKEN=csrf_token)
    api_client.cookies["groundtruth_refresh"] = old_token

    replay = api_client.post("/api/v1/auth/refresh/", HTTP_X_CSRFTOKEN=csrf_token)

    assert replay.status_code == 401
    assert replay.data == {"detail": "Refresh Token 已失效"}


@pytest.mark.django_db
def test_logout_without_refresh_token_is_idempotent(api_client, login_user):
    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": login_user.email, "password": "correct-password"},
        format="json",
    )
    csrf_token = login.cookies["csrftoken"].value
    del api_client.cookies["groundtruth_refresh"]

    response = api_client.post("/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=csrf_token)

    assert response.status_code == 204


@pytest.mark.django_db
def test_business_jwt_rejects_malformed_and_deleted_user(login_user):
    authentication = BusinessJwtAuthentication()
    factory = APIRequestFactory()

    malformed = factory.get("/", HTTP_AUTHORIZATION="Basic invalid")
    with pytest.raises(AuthenticationFailed, match="無效的認證資訊"):
        authentication.authenticate(malformed)

    access, _, _ = issue_token_pair(login_user)
    login_user.delete()
    deleted = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {access}")
    with pytest.raises(AuthenticationFailed, match="登入狀態已失效"):
        authentication.authenticate(deleted)

    assert authentication.authenticate_header(deleted) == "Bearer"
