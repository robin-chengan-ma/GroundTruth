from unittest.mock import patch

import pytest

from apps.audit.models import AuditLog
from apps.core.models import Permission, RolePermission, UserRole
from apps.procurement.models import PurchaseRequest


def _grant_create_permission(user, role):
    UserRole.objects.create(user=user, role=role)
    permission = Permission.objects.create(code="purchase_request.create", name="建立採購需求")
    RolePermission.objects.create(role=role, permission=permission)


@pytest.mark.django_db
@patch("api.procurement.views.parse_purchase_request_candidate")
def test_parse_candidate_api_uses_authenticated_user_and_does_not_create_document(
    mock_parse, api_client, user, role_employee,
):
    _grant_create_permission(user, role_employee)
    api_client.force_authenticate(user=user)
    mock_parse.return_value = {"ready_for_draft": True, "items": [], "supplier_candidates": []}

    response = api_client.post(
        "/api/v1/inquiries/parse/",
        {"raw_text": "跟優品科技買 5 張辦公椅", "user_id": 999},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["candidate_token"]
    mock_parse.assert_called_once_with("跟優品科技買 5 張辦公椅", user_id=user.id)
    assert PurchaseRequest.objects.count() == 0
    assert AuditLog.objects.filter(action_type="candidate_parsed", user=user).count() == 1


@pytest.mark.django_db
def test_parse_candidate_api_requires_create_permission(api_client, user):
    api_client.force_authenticate(user=user)

    response = api_client.post("/api/v1/inquiries/parse/", {"raw_text": "測試"}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


@pytest.mark.django_db
@patch("api.procurement.views.parse_purchase_request_candidate")
def test_parse_candidate_api_keeps_missing_quantity_editable_without_coverage_error(
    mock_parse, api_client, user, role_employee,
):
    _grant_create_permission(user, role_employee)
    api_client.force_authenticate(user=user)
    mock_parse.return_value = {
        "currency": "TWD",
        "supplier_candidates": [],
        "items": [{"product_id": 10, "quantity": None}],
        "missing_fields": ["items.0.quantity"],
        "ready_for_draft": False,
    }

    response = api_client.post(
        "/api/v1/inquiries/parse/", {"raw_text": "採購一些辦公椅"}, format="json",
    )

    assert response.status_code == 200
    assert response.data["supplier_product_coverage"] == []
