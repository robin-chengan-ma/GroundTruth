"""Phase 6：庫存餘額／流水查詢 API（FR-10a）。

/api/v1/inventory/ 是 Phase 1 舊 Inventory model（stock_qty/threshold），FR-10a 起真正的
庫存真相來源已切到 InventoryBalance（查詢快照）／InventoryMovement（不可覆寫流水帳），
但至今沒有對應查詢端點；Phase 6 庫存頁面需要這兩個新端點才能顯示正確資料。
"""
from decimal import Decimal

import pytest

from apps.erp.models import Inventory, InventoryBalance, InventoryMovement


@pytest.mark.django_db
def test_inventory_balance_requires_inventory_read(api_client, user, role_employee, product):
    api_client.force_authenticate(user=user)
    resp = api_client.get("/api/v1/inventory-balances/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_inventory_balance_list_shows_threshold_and_available(admin_api_client, product):
    Inventory.objects.create(product=product, stock_qty=0, threshold=10)
    InventoryBalance.objects.create(
        product=product,
        on_hand_quantity=Decimal("8.000"),
        reserved_quantity=Decimal("2.000"),
        in_transit_quantity=Decimal("5.000"),
    )

    resp = admin_api_client.get("/api/v1/inventory-balances/")

    assert resp.status_code == 200
    rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
    row = next(r for r in rows if r["product"] == product.id)
    assert row["on_hand_quantity"] == "8.000"
    assert row["reserved_quantity"] == "2.000"
    assert row["in_transit_quantity"] == "5.000"
    assert row["threshold"] == 10
    assert row["available_quantity"] == "11.000"  # 8 - 2 + 5


@pytest.mark.django_db
def test_inventory_balance_without_legacy_threshold_row_returns_null_threshold(admin_api_client, product):
    InventoryBalance.objects.create(product=product)

    resp = admin_api_client.get("/api/v1/inventory-balances/")

    row = next(r for r in resp.data["results"] if r["product"] == product.id)
    assert row["threshold"] is None


@pytest.mark.django_db
def test_inventory_movement_list_requires_inventory_read(api_client, user, role_employee):
    api_client.force_authenticate(user=user)
    resp = api_client.get("/api/v1/inventory-movements/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_inventory_movement_list_shows_history(admin_api_client, product, admin_user):
    InventoryMovement.objects.create(
        product=product,
        movement_type=InventoryMovement.MovementType.ADJUSTMENT_IN,
        quantity_delta=Decimal("5.000"),
        reference_type="manual_adjustment",
        reference_id=1,
        reason="盤點調整",
        posted_by=admin_user,
    )

    resp = admin_api_client.get("/api/v1/inventory-movements/")

    assert resp.status_code == 200
    rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
    assert len(rows) == 1
    assert rows[0]["movement_type"] == "adjustment_in"
    assert rows[0]["quantity_delta"] == "5.000"
    assert rows[0]["product_name"] == product.name
