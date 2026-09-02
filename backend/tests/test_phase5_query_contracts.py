"""Phase 5：RFQ／供應商報價／得標方案查詢契約補齊（FR-16）。

這三個資源先前只有寫入 action（issue/evaluate、create/submit/revise、create/submit），
router 雖有註冊路由但 ViewSet 未實作 list／retrieve，等同完全沒有查詢契約。
"""
from decimal import Decimal

import pytest

from apps.core.models import Permission, RolePermission, UserRole
from apps.procurement.models import AwardLine
from tests.test_phase4_1_award_approval_po import create_award_context


def _grant(user, role, code, name=None):
    UserRole.objects.get_or_create(user=user, role=role)
    permission, _ = Permission.objects.get_or_create(code=code, defaults={"name": name or code})
    RolePermission.objects.get_or_create(role=role, permission=permission)


@pytest.fixture
def award_fixture(user, supplier, product, role_employee):
    request, request_item, quote_item, award = create_award_context(user, supplier, product)
    AwardLine.objects.create(
        award=award,
        request_item=request_item,
        supplier_quote_item=quote_item,
        awarded_quantity=Decimal("5.000"),
        unit_price_snapshot=Decimal("100.00"),
        amount_snapshot=Decimal("500.00"),
    )
    return request, award


# ---- RFQ ----


@pytest.mark.django_db
def test_rfq_list_requires_rfq_manage_or_audit_permission(api_client, user, role_employee, award_fixture):
    _request, _award = award_fixture
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/rfqs/")

    assert resp.status_code == 403


@pytest.mark.django_db
def test_rfq_list_and_retrieve_visible_with_rfq_manage(api_client, user, role_employee, award_fixture):
    request, award = award_fixture
    rfq = award.rfq
    _grant(user, role_employee, "rfq.manage", "管理 RFQ")
    api_client.force_authenticate(user=user)

    list_resp = api_client.get("/api/v1/rfqs/")
    detail_resp = api_client.get(f"/api/v1/rfqs/{rfq.id}/")

    assert list_resp.status_code == 200
    assert rfq.id in [row["id"] for row in list_resp.data["results"]]
    assert detail_resp.status_code == 200
    assert detail_resp.data["id"] == rfq.id
    assert detail_resp.data["request_id"] == request.id


@pytest.mark.django_db
def test_rfq_list_visible_with_audit_read(api_client, user, role_employee, award_fixture):
    _grant(user, role_employee, "audit.read", "讀取稽核紀錄")
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/rfqs/")

    assert resp.status_code == 200


@pytest.mark.django_db
def test_rfq_retrieve_404_for_missing_id(api_client, user, role_employee):
    _grant(user, role_employee, "rfq.manage", "管理 RFQ")
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/rfqs/999999/")

    assert resp.status_code == 404


# ---- Supplier quotes ----


@pytest.mark.django_db
def test_supplier_quote_list_requires_permission(api_client, user, role_employee, award_fixture):
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/supplier-quotes/")

    assert resp.status_code == 403


@pytest.mark.django_db
def test_supplier_quote_list_and_retrieve_visible_with_supplier_quote_manage(
    api_client, user, role_employee, award_fixture,
):
    _request, award = award_fixture
    quote_item = award.lines.get().supplier_quote_item
    quote = quote_item.supplier_quote
    _grant(user, role_employee, "supplier_quote.manage", "管理供應商報價")
    api_client.force_authenticate(user=user)

    list_resp = api_client.get("/api/v1/supplier-quotes/")
    detail_resp = api_client.get(f"/api/v1/supplier-quotes/{quote.id}/")

    assert list_resp.status_code == 200
    assert quote.id in [row["id"] for row in list_resp.data["results"]]
    assert detail_resp.status_code == 200
    assert detail_resp.data["id"] == quote.id


@pytest.mark.django_db
def test_supplier_quote_retrieve_404_for_missing_id(api_client, user, role_employee):
    _grant(user, role_employee, "supplier_quote.manage", "管理供應商報價")
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/supplier-quotes/999999/")

    assert resp.status_code == 404


# ---- Award decisions ----


@pytest.mark.django_db
def test_award_list_requires_permission(api_client, user, role_employee, award_fixture):
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/award-decisions/")

    assert resp.status_code == 403


@pytest.mark.django_db
def test_award_list_and_retrieve_visible_with_award_recommend(api_client, user, role_employee, award_fixture):
    _request, award = award_fixture
    _grant(user, role_employee, "award.recommend", "建立與提交得標方案")
    api_client.force_authenticate(user=user)

    list_resp = api_client.get("/api/v1/award-decisions/")
    detail_resp = api_client.get(f"/api/v1/award-decisions/{award.id}/")

    assert list_resp.status_code == 200
    assert award.id in [row["id"] for row in list_resp.data["results"]]
    assert detail_resp.status_code == 200
    assert detail_resp.data["id"] == award.id
    assert detail_resp.data["total_amount_twd"] == "500.00"


@pytest.mark.django_db
def test_award_list_visible_with_audit_read_only(api_client, user, role_employee, award_fixture):
    _grant(user, role_employee, "audit.read", "讀取稽核紀錄")
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/award-decisions/")

    assert resp.status_code == 200


@pytest.mark.django_db
def test_award_retrieve_404_for_missing_id(api_client, user, role_employee):
    _grant(user, role_employee, "award.recommend", "建立與提交得標方案")
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/award-decisions/999999/")

    assert resp.status_code == 404


# ---- 採購建議（purchase-suggestions）list／retrieve 權限收斂 ----


@pytest.mark.django_db
def test_purchase_suggestion_list_requires_dedicated_permission(api_client, user, role_employee):
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/purchase-suggestions/")

    assert resp.status_code == 403


@pytest.mark.django_db
def test_purchase_suggestion_list_and_retrieve_visible_with_permission(
    api_client, user, role_employee, product,
):
    from apps.erp.models import PurchaseSuggestion

    suggestion = PurchaseSuggestion.objects.create(product=product, suggested_qty="6.000")
    _grant(user, role_employee, "purchase_suggestion.read", "讀取採購建議")
    api_client.force_authenticate(user=user)

    list_resp = api_client.get("/api/v1/purchase-suggestions/")
    detail_resp = api_client.get(f"/api/v1/purchase-suggestions/{suggestion.id}/")

    assert list_resp.status_code == 200
    assert suggestion.id in [row["id"] for row in list_resp.data["results"]]
    assert detail_resp.status_code == 200
    assert detail_resp.data["id"] == suggestion.id


@pytest.mark.django_db
def test_purchase_suggestion_convert_and_dismiss_not_gated_by_read_permission(
    api_client, user, role_employee, admin_user, supplier, product,
):
    """convert／dismiss 各自的授權已由 service 層把關（purchase_request.create／admin 身分），
    不應該因為缺少 purchase_suggestion.read 而在 DRF 權限層被擋下——兩者是不同的能力。"""
    from apps.erp.models import PurchaseSuggestion

    _grant(user, role_employee, "purchase_request.create", "建立採購需求")
    api_client.force_authenticate(user=user)
    suggestion = PurchaseSuggestion.objects.create(product=product, suggested_qty="4.000")

    convert_resp = api_client.post(
        f"/api/v1/purchase-suggestions/{suggestion.id}/convert/",
        {"supplier_ids": [supplier.id]},
        format="json",
    )
    assert convert_resp.status_code == 201

    other_suggestion = PurchaseSuggestion.objects.create(product=product, suggested_qty="2.000")
    api_client.force_authenticate(user=admin_user)
    dismiss_resp = api_client.post(
        f"/api/v1/purchase-suggestions/{other_suggestion.id}/dismiss/", {}, format="json",
    )
    assert dismiss_resp.status_code == 200
