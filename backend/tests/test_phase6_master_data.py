"""Phase 6：主檔管理頁面所需的完整欄位與品項分類 CRUD（FR-16／CRM FR-1～2／ERP FR-1）。

既有 SupplierSerializer／ProductSerializer 只回傳極少欄位（id/name/tier/created_at、
id/name/price/currency），前端主檔管理頁面需要完整欄位才能顯示與編輯；ProductCategory
model 已存在（Product.category FK），但從未有對應 API。
"""

import pytest

from apps.erp.models import ProductCategory


@pytest.mark.django_db
def test_supplier_full_fields_returned_and_writable(admin_api_client):
    resp = admin_api_client.post(
        "/api/v1/suppliers/",
        {
            "name": "完整欄位供應商",
            "tier": "priority",
            "code": "SUP-FULL-001",
            "status": "active",
            "tax_id": "12345678",
            "contact": {"phone": "02-1234-5678", "email": "contact@example.com"},
            "payment_terms": "月結 30 天",
            "is_active": True,
        },
        format="json",
    )
    assert resp.status_code == 201
    for field in ("code", "status", "tax_id", "contact", "payment_terms", "is_active", "updated_at"):
        assert field in resp.data, field
    assert resp.data["contact"] == {"phone": "02-1234-5678", "email": "contact@example.com"}

    supplier_id = resp.data["id"]
    resp = admin_api_client.patch(f"/api/v1/suppliers/{supplier_id}/", {"is_active": False}, format="json")
    assert resp.status_code == 200
    assert resp.data["is_active"] is False


@pytest.mark.django_db
def test_supplier_list_still_readable_by_search(admin_api_client, supplier):
    resp = admin_api_client.get("/api/v1/suppliers/", {"search": supplier.name})
    assert resp.status_code == 200


@pytest.mark.django_db
def test_product_category_crud(admin_api_client):
    resp = admin_api_client.post(
        "/api/v1/product-categories/",
        {"code": "OFFICE", "name": "辦公傢俱", "spec_schema": {"material": {"type": "string"}}},
        format="json",
    )
    assert resp.status_code == 201
    category_id = resp.data["id"]
    assert resp.data["spec_schema"] == {"material": {"type": "string"}}

    resp = admin_api_client.patch(
        f"/api/v1/product-categories/{category_id}/", {"is_active": False}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["is_active"] is False

    resp = admin_api_client.delete(f"/api/v1/product-categories/{category_id}/")
    assert resp.status_code == 409
    assert resp.data["code"] == "physical_delete_forbidden"
    assert ProductCategory.objects.filter(pk=category_id).exists()


@pytest.mark.django_db
def test_product_full_fields_returned_and_writable(admin_api_client):
    category = ProductCategory.objects.create(code="TEST-CAT", name="測試分類")
    resp = admin_api_client.post(
        "/api/v1/products/",
        {
            "name": "完整欄位品項",
            "category": category.id,
            "sku": "SKU-001",
            "description": "測試描述",
            "specifications": {"material": "網布"},
            "unit_of_measure": "EA",
            "is_active": True,
            "price": "1500.00",
            "currency": "TWD",
        },
        format="json",
    )
    assert resp.status_code == 201
    for field in (
        "category", "category_name", "sku", "description", "specifications",
        "unit_of_measure", "is_active", "updated_at",
    ):
        assert field in resp.data, field
    assert resp.data["category_name"] == "測試分類"
    assert resp.data["specifications"] == {"material": "網布"}

    product_id = resp.data["id"]
    resp = admin_api_client.patch(f"/api/v1/products/{product_id}/", {"is_active": False}, format="json")
    assert resp.status_code == 200
    assert resp.data["is_active"] is False


@pytest.mark.django_db
def test_product_without_category_still_works(admin_api_client):
    resp = admin_api_client.post(
        "/api/v1/products/",
        {"name": "無分類品項", "price": "500.00", "currency": "TWD"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["category"] is None
    assert resp.data["category_name"] is None


@pytest.mark.django_db
def test_non_admin_cannot_write_supplier_or_product(api_client, user, role_employee, supplier, product):
    api_client.force_authenticate(user=user)
    resp = api_client.patch(f"/api/v1/suppliers/{supplier.id}/", {"is_active": False}, format="json")
    assert resp.status_code == 403
    resp = api_client.patch(f"/api/v1/products/{product.id}/", {"is_active": False}, format="json")
    assert resp.status_code == 403
    resp = api_client.post(
        "/api/v1/product-categories/", {"code": "X", "name": "X"}, format="json"
    )
    assert resp.status_code == 403
