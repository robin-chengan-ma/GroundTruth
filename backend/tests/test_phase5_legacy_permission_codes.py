"""Phase 5 補強：legacy Quote／Approval 歷史查詢與忽略採購建議改用 permission code 授權。

背景：Codex 程式碼審查發現 QuoteViewSet／ApprovalViewSet 的 get_queryset() 仍用
`user.role.role == "admin"／"employee"` 字串比對決定可視範圍，且兩者 permission_classes
只有 IsAuthenticated，未掛任何 permission code；purchase_suggestion_service.dismiss() 也
直接檢查 `user.role.role == "admin"`，違反 docs/ADR/discuss/erp.md 2026-08-28 已 accepted 的
「忽略操作改由 purchase_suggestion.dismiss 權限控制，不綁定系統管理員角色」決策。這批測試鎖定
改用 permission code 後的授權行為，防止之後又退回角色字串判斷。
"""
from decimal import Decimal

import pytest

from apps.core.models import Permission, RolePermission, UserRole
from apps.procurement.models import Approval, Quote
from services.purchase_suggestion_service import PurchaseSuggestionPermissionDenied, dismiss


def _grant(user, role, code, name=None):
    UserRole.objects.get_or_create(user=user, role=role)
    permission, _ = Permission.objects.get_or_create(code=code, defaults={"name": name or code})
    RolePermission.objects.get_or_create(role=role, permission=permission)


@pytest.fixture
def quote_fixture(user, supplier, product):
    return Quote.objects.create(
        user=user, supplier=supplier, product=product,
        quantity=5, price=Decimal("100.00"), total_amount=Decimal("500.00"), currency="TWD",
    )


@pytest.fixture
def approval_fixture(quote_fixture, role_employee):
    return Approval.objects.create(
        quote=quote_fixture, role=role_employee, approval_level=Approval.Level.SMALL,
    )


@pytest.mark.django_db
def test_quote_list_rejects_user_without_any_relevant_permission(api_client, user, quote_fixture):
    api_client.force_authenticate(user=user)
    resp = api_client.get("/api/v1/quotes/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_quote_list_with_read_own_only_sees_self(api_client, user, role_employee, supplier, product, quote_fixture):
    other_user_quote = Quote.objects.create(
        user=user, supplier=supplier, product=product,
        quantity=1, price=Decimal("10.00"), total_amount=Decimal("10.00"), currency="TWD",
    )
    _grant(user, role_employee, "purchase_request.read_own", "讀取自己的採購需求")
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/quotes/")

    assert resp.status_code == 200
    ids = {row["id"] for row in resp.data["results"]}
    assert ids == {quote_fixture.id, other_user_quote.id}


@pytest.mark.django_db
def test_quote_list_with_audit_read_sees_all(api_client, user, role_employee, quote_fixture):
    _grant(user, role_employee, "audit.read", "讀取稽核紀錄")
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/quotes/")

    assert resp.status_code == 200
    assert quote_fixture.id in {row["id"] for row in resp.data["results"]}


@pytest.mark.django_db
def test_approval_list_rejects_user_without_any_relevant_permission(api_client, user, approval_fixture):
    api_client.force_authenticate(user=user)
    resp = api_client.get("/api/v1/approvals/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_approval_list_with_read_all_sees_own_role_scope(
    api_client, user, role_employee, approval_fixture
):
    _grant(user, role_employee, "approval.read_all", "讀取可簽核案件")
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/approvals/")

    assert resp.status_code == 200
    assert approval_fixture.id in {row["id"] for row in resp.data["results"]}


@pytest.mark.django_db
def test_approval_list_with_audit_read_sees_all(api_client, user, role_employee, approval_fixture):
    _grant(user, role_employee, "audit.read", "讀取稽核紀錄")
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/approvals/")

    assert resp.status_code == 200
    assert approval_fixture.id in {row["id"] for row in resp.data["results"]}


@pytest.mark.django_db
def test_dismiss_purchase_suggestion_requires_dismiss_permission_not_admin_role(
    user, role_admin, product,
):
    from apps.erp.models import PurchaseSuggestion

    suggestion = PurchaseSuggestion.objects.create(product=product, suggested_qty=10)
    admin_like_user_without_permission = user
    admin_like_user_without_permission.role = role_admin
    admin_like_user_without_permission.save(update_fields=["role"])

    with pytest.raises(PurchaseSuggestionPermissionDenied):
        dismiss(admin_like_user_without_permission, suggestion.id)


@pytest.mark.django_db
def test_dismiss_purchase_suggestion_succeeds_with_permission_granted(
    user, role_employee, product,
):
    from apps.erp.models import PurchaseSuggestion

    suggestion = PurchaseSuggestion.objects.create(product=product, suggested_qty=10)
    _grant(user, role_employee, "purchase_suggestion.dismiss", "忽略採購建議")

    result = dismiss(user, suggestion.id)

    result.refresh_from_db()
    assert result.status == PurchaseSuggestion.Status.DISMISSED
