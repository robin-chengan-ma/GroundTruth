from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import Permission, RolePermission, UserRole
from apps.crm.models import Supplier
from apps.erp.models import Product
from apps.procurement.models import SupplierPriceVersion, SupplierProduct


def _grant_create_permission(user, role):
    UserRole.objects.create(user=user, role=role)
    permission = Permission.objects.create(
        code="purchase_request.create", name="建立採購需求",
    )
    RolePermission.objects.create(role=role, permission=permission)


@pytest.mark.django_db
def test_supplier_product_coverage_distinguishes_relationship_price_and_quality(
    api_client, user, role_employee,
):
    _grant_create_permission(user, role_employee)
    api_client.force_authenticate(user=user)
    chair = Product.objects.create(name="A產品-辦公椅", price="1500", currency="TWD")
    desk = Product.objects.create(name="F產品-辦公桌", price="3500", currency="TWD")
    first = Supplier.objects.create(name="優品科技")
    second = Supplier.objects.create(name="大和物產")
    priced = SupplierProduct.objects.create(supplier=first, product=chair)
    SupplierPriceVersion.objects.create(
        supplier_product=priced,
        unit_price=Decimal("1500.00"),
        currency="TWD",
        minimum_quantity=Decimal("1.000"),
        valid_from=timezone.now() - timedelta(days=1),
        created_by=user,
    )
    SupplierProduct.objects.create(
        supplier=second,
        product=chair,
        quality_status="blocked",
    )
    SupplierProduct.objects.create(supplier=first, product=desk)

    response = api_client.post(
        "/api/v1/supplier-product-coverage/",
        {
            "currency": "TWD",
            "supplier_ids": [first.id, second.id],
            "items": [
                {"product_id": chair.id, "quantity": "5"},
                {"product_id": desk.id, "quantity": "3"},
            ],
        },
        format="json",
    )

    assert response.status_code == 200
    matrix = {
        (row["supplier_id"], row["product_id"]): row
        for row in response.data["rows"]
    }
    assert matrix[(first.id, chair.id)]["status"] == "priced"
    assert matrix[(first.id, chair.id)]["unit_price"] == "1500.00"
    assert matrix[(first.id, desk.id)]["status"] == "unpriced"
    assert matrix[(second.id, chair.id)]["status"] == "blocked"
    assert matrix[(second.id, desk.id)]["status"] == "not_configured"


@pytest.mark.django_db
def test_supplier_product_coverage_requires_create_permission(api_client, user):
    api_client.force_authenticate(user=user)

    response = api_client.post(
        "/api/v1/supplier-product-coverage/",
        {"currency": "TWD", "supplier_ids": [], "items": []},
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
