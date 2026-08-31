from decimal import Decimal

import pytest

from apps.core.models import Role
from apps.erp.models import GoodsReceipt, InventoryBalance, InventoryMovement
from apps.procurement.models import PurchaseOrder
from tests.test_phase4_1_approval_workflow import _actor, _grant
from tests.test_phase4_1_receiving_inventory import create_purchase_order


def _receiver(name="C6 Receiver"):
    role = Role.objects.create(role=name.lower().replace(" ", "_"))
    return _actor(name, role, "receipt.record")


def _issue_ready_order(user, supplier, product, *, suffix="C6", quantity="5.000"):
    order, item = create_purchase_order(
        user, supplier, product, suffix=suffix, quantity=quantity
    )
    order.status = PurchaseOrder.Status.DRAFT
    order.issued_at = None
    order.save(update_fields=["status", "issued_at"])
    manager_role = Role.objects.create(role=f"po_manager_{suffix.lower()}")
    manager = _actor(f"PO Manager {suffix}", manager_role, "purchase_order.manage")
    return order, item, manager


def _issue(api_client, manager, order):
    api_client.force_authenticate(user=manager)
    return api_client.post(
        f"/api/v1/purchase-orders/{order.id}/issue/",
        {"version": order.version},
        format="json",
    )


@pytest.mark.django_db
def test_issue_po_adds_in_transit_without_on_hand_or_movement(
    api_client, user, supplier, product
):
    order, _, manager = _issue_ready_order(user, supplier, product)

    response = _issue(api_client, manager, order)

    balance = InventoryBalance.objects.get(product=product)
    assert response.status_code == 200
    assert balance.in_transit_quantity == Decimal("5.000")
    assert balance.on_hand_quantity == Decimal("0.000")
    assert InventoryMovement.objects.count() == 0


@pytest.mark.django_db
def test_receiver_can_create_partial_receipt_draft_for_issued_po(
    api_client, user, supplier, product
):
    order, item, manager = _issue_ready_order(user, supplier, product)
    _issue(api_client, manager, order)
    receiver = _receiver()
    api_client.force_authenticate(user=receiver)

    response = api_client.post(
        "/api/v1/goods-receipts/",
        {
            "purchase_order_id": order.id,
            "items": [
                {
                    "purchase_order_item_id": item.id,
                    "received_quantity": "2.000",
                    "lot_no": "LOT-C6-001",
                }
            ],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["status"] == "draft"
    assert response.data["version"] == 1
    assert response.data["items"][0]["received_quantity"] == "2.000"
    assert response.data["received_at"] is None
    assert InventoryBalance.objects.get(product=product).in_transit_quantity == Decimal("5.000")


@pytest.mark.django_db
def test_receipt_creation_rejects_permission_wrong_po_state_and_duplicate_items(
    api_client, user, role_employee, supplier, product
):
    order, item = create_purchase_order(user, supplier, product, suffix="C6-GUARD")
    _grant(user, role_employee, "purchase_request.read_own")
    payload = {
        "purchase_order_id": order.id,
        "items": [
            {"purchase_order_item_id": item.id, "received_quantity": "1.000"},
            {"purchase_order_item_id": item.id, "received_quantity": "1.000"},
        ],
    }

    api_client.force_authenticate(user=user)
    denied = api_client.post("/api/v1/goods-receipts/", payload, format="json")
    receiver = _receiver("Guard Receiver")
    api_client.force_authenticate(user=receiver)
    duplicate = api_client.post("/api/v1/goods-receipts/", payload, format="json")
    order.status = PurchaseOrder.Status.DRAFT
    order.save(update_fields=["status"])
    wrong_state = api_client.post(
        "/api/v1/goods-receipts/",
        {
            "purchase_order_id": order.id,
            "items": [{"purchase_order_item_id": item.id, "received_quantity": "1.000"}],
        },
        format="json",
    )

    assert denied.status_code == 403
    assert duplicate.status_code == 400
    assert wrong_state.status_code == 409
    assert GoodsReceipt.objects.count() == 0


@pytest.mark.django_db
def test_receipt_creation_rejects_over_receipt_and_item_from_other_po(
    api_client, user, supplier, product
):
    order, item = create_purchase_order(user, supplier, product, suffix="C6-OVER")
    _, other_item = create_purchase_order(user, supplier, product, suffix="C6-OTHER")
    receiver = _receiver("Over Receiver")
    api_client.force_authenticate(user=receiver)

    over = api_client.post(
        "/api/v1/goods-receipts/",
        {
            "purchase_order_id": order.id,
            "items": [{"purchase_order_item_id": item.id, "received_quantity": "5.001"}],
        },
        format="json",
    )
    wrong_po = api_client.post(
        "/api/v1/goods-receipts/",
        {
            "purchase_order_id": order.id,
            "items": [
                {"purchase_order_item_id": other_item.id, "received_quantity": "1.000"}
            ],
        },
        format="json",
    )

    assert over.status_code == 409
    assert wrong_po.status_code == 400
    assert GoodsReceipt.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("quantity", [None, "0", "1.0001", "NaN"])
def test_receipt_creation_rejects_invalid_quantities(
    api_client, user, supplier, product, quantity
):
    order, item = create_purchase_order(user, supplier, product, suffix=f"C6-QTY-{quantity}")
    receiver = _receiver(f"Quantity Receiver {quantity}")
    api_client.force_authenticate(user=receiver)

    response = api_client.post(
        "/api/v1/goods-receipts/",
        {
            "purchase_order_id": order.id,
            "items": [
                {"purchase_order_item_id": item.id, "received_quantity": quantity}
            ],
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_receipt_detail_hides_inaccessible_or_missing_receipt(
    api_client, user, role_employee
):
    _grant(user, role_employee, "purchase_request.read_own")
    api_client.force_authenticate(user=user)

    response = api_client.get("/api/v1/goods-receipts/999999/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_submit_receipt_requires_matching_version_and_decrements_in_transit_once(
    api_client, user, supplier, product
):
    order, item, manager = _issue_ready_order(user, supplier, product, suffix="C6-SUBMIT")
    _issue(api_client, manager, order)
    receiver = _receiver("Submit Receiver")
    api_client.force_authenticate(user=receiver)
    created = api_client.post(
        "/api/v1/goods-receipts/",
        {
            "purchase_order_id": order.id,
            "items": [{"purchase_order_item_id": item.id, "received_quantity": "2.000"}],
        },
        format="json",
    )
    receipt_id = created.data["id"]

    stale = api_client.post(
        f"/api/v1/goods-receipts/{receipt_id}/submit/", {"version": 99}, format="json"
    )
    submitted = api_client.post(
        f"/api/v1/goods-receipts/{receipt_id}/submit/", {"version": 1}, format="json"
    )
    repeated = api_client.post(
        f"/api/v1/goods-receipts/{receipt_id}/submit/", {"version": 2}, format="json"
    )

    balance = InventoryBalance.objects.get(product=product)
    assert stale.status_code == 409
    assert submitted.status_code == 200
    assert submitted.data["status"] == "inspecting"
    assert submitted.data["received_at"] is not None
    assert repeated.status_code == 409
    assert balance.in_transit_quantity == Decimal("3.000")
    assert balance.on_hand_quantity == Decimal("0.000")
    assert InventoryMovement.objects.count() == 0


@pytest.mark.django_db
def test_receipt_visibility_is_own_request_or_receiving_or_audit_permission(
    api_client, user, role_employee, supplier, product
):
    order, item = create_purchase_order(user, supplier, product, suffix="C6-VIS")
    receiver = _receiver("Visibility Receiver")
    api_client.force_authenticate(user=receiver)
    created = api_client.post(
        "/api/v1/goods-receipts/",
        {
            "purchase_order_id": order.id,
            "items": [{"purchase_order_item_id": item.id, "received_quantity": "1.000"}],
        },
        format="json",
    )
    _grant(user, role_employee, "purchase_request.read_own")
    auditor_role = Role.objects.create(role="receipt_auditor")
    auditor = _actor("Receipt Auditor", auditor_role, "audit.read")
    outsider_role = Role.objects.create(role="receipt_outsider")
    outsider = _actor("Receipt Outsider", outsider_role)

    api_client.force_authenticate(user=user)
    owner_result = api_client.get("/api/v1/goods-receipts/")
    api_client.force_authenticate(user=auditor)
    audit_result = api_client.get("/api/v1/goods-receipts/")
    api_client.force_authenticate(user=outsider)
    denied = api_client.get("/api/v1/goods-receipts/")

    assert created.status_code == 201
    assert [row["id"] for row in owner_result.data] == [created.data["id"]]
    assert [row["id"] for row in audit_result.data] == [created.data["id"]]
    assert denied.status_code == 403
