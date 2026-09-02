"""Phase 5／FR-2／FR-16：供應商可供應品項與版本化價格主檔 API（先前完全沒有這組契約）。"""
from decimal import Decimal

import pytest

from apps.core.models import Permission, RolePermission, UserRole
from apps.procurement.models import SupplierProduct


def _grant(user, role, code, name=None):
    UserRole.objects.get_or_create(user=user, role=role)
    permission, _ = Permission.objects.get_or_create(code=code, defaults={"name": name or code})
    RolePermission.objects.get_or_create(role=role, permission=permission)


@pytest.mark.django_db
def test_list_requires_master_data_read(api_client, user, role_employee):
    api_client.force_authenticate(user=user)

    resp = api_client.get("/api/v1/supplier-products/")

    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_requires_master_data_manage(api_client, user, role_employee, supplier, product):
    _grant(user, role_employee, "master_data.read", "讀取主檔")
    api_client.force_authenticate(user=user)

    resp = api_client.post(
        "/api/v1/supplier-products/",
        {"supplier": supplier.id, "product": product.id, "minimum_order_quantity": "10"},
        format="json",
    )

    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_list_retrieve_and_deactivate(api_client, user, role_employee, supplier, product):
    _grant(user, role_employee, "master_data.manage", "管理主檔")
    _grant(user, role_employee, "master_data.read", "讀取主檔")
    api_client.force_authenticate(user=user)

    create_resp = api_client.post(
        "/api/v1/supplier-products/",
        {
            "supplier": supplier.id, "product": product.id,
            "supplier_sku": "SKU-001", "lead_time_days": 7,
            "minimum_order_quantity": "10.000",
        },
        format="json",
    )
    assert create_resp.status_code == 201
    supplier_product_id = create_resp.data["id"]
    assert create_resp.data["is_active"] is True

    list_resp = api_client.get("/api/v1/supplier-products/")
    assert list_resp.status_code == 200
    assert supplier_product_id in [row["id"] for row in list_resp.data]

    detail_resp = api_client.get(f"/api/v1/supplier-products/{supplier_product_id}/")
    assert detail_resp.status_code == 200
    assert detail_resp.data["supplier_sku"] == "SKU-001"

    deactivate_resp = api_client.patch(
        f"/api/v1/supplier-products/{supplier_product_id}/", {"is_active": False}, format="json",
    )
    assert deactivate_resp.status_code == 200
    assert deactivate_resp.data["is_active"] is False

    destroy_resp = api_client.delete(f"/api/v1/supplier-products/{supplier_product_id}/")
    assert destroy_resp.status_code == 409
    assert destroy_resp.data["code"] == "physical_delete_forbidden"
    assert SupplierProduct.objects.filter(pk=supplier_product_id).exists()


@pytest.mark.django_db
def test_create_rejects_duplicate_supplier_product_pair(api_client, user, role_employee, supplier, product):
    _grant(user, role_employee, "master_data.manage", "管理主檔")
    api_client.force_authenticate(user=user)
    SupplierProduct.objects.create(supplier=supplier, product=product, minimum_order_quantity=Decimal(1))

    resp = api_client.post(
        "/api/v1/supplier-products/",
        {"supplier": supplier.id, "product": product.id},
        format="json",
    )

    assert resp.status_code == 409


@pytest.mark.django_db
def test_add_price_version_and_reject_overlap(api_client, user, role_employee, supplier, product):
    _grant(user, role_employee, "master_data.manage", "管理主檔")
    api_client.force_authenticate(user=user)
    supplier_product = SupplierProduct.objects.create(
        supplier=supplier, product=product, minimum_order_quantity=Decimal(1),
    )

    first = api_client.post(
        f"/api/v1/supplier-products/{supplier_product.id}/price-versions/",
        {
            "unit_price": "150.00", "currency": "TWD", "minimum_quantity": "1",
            "valid_from": "2026-01-01T00:00:00Z",
        },
        format="json",
    )
    assert first.status_code == 201
    assert len(first.data["price_versions"]) == 1
    assert first.data["price_versions"][0]["unit_price"] == "150.00"

    overlapping = api_client.post(
        f"/api/v1/supplier-products/{supplier_product.id}/price-versions/",
        {
            "unit_price": "160.00", "currency": "TWD", "minimum_quantity": "1",
            "valid_from": "2026-06-01T00:00:00Z",
        },
        format="json",
    )
    assert overlapping.status_code == 409

    non_overlapping = api_client.post(
        f"/api/v1/supplier-products/{supplier_product.id}/price-versions/",
        {
            "unit_price": "160.00", "currency": "TWD", "minimum_quantity": "1",
            "valid_from": "2026-06-01T00:00:00Z", "valid_until": None,
        },
        format="json",
    )
    # 只有先把第一版設定 valid_until 才能新增不重疊版本；此處驗證未設定 valid_until 時仍會擋下。
    assert non_overlapping.status_code == 409


@pytest.mark.django_db
def test_add_price_version_requires_positive_unit_price(api_client, user, role_employee, supplier, product):
    _grant(user, role_employee, "master_data.manage", "管理主檔")
    api_client.force_authenticate(user=user)
    supplier_product = SupplierProduct.objects.create(
        supplier=supplier, product=product, minimum_order_quantity=Decimal(1),
    )

    resp = api_client.post(
        f"/api/v1/supplier-products/{supplier_product.id}/price-versions/",
        {"unit_price": "-1.00", "currency": "TWD"},
        format="json",
    )

    assert resp.status_code == 400
