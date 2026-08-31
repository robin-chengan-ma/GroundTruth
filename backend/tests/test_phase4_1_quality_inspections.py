from decimal import Decimal

import pytest

from apps.core.models import Role
from apps.erp.models import GoodsReceipt, InventoryBalance, InventoryMovement, QualityInspection
from apps.procurement.models import PurchaseOrder, PurchaseRequest
from tests.test_phase4_1_approval_workflow import _actor
from tests.test_phase4_1_goods_receipts import _issue, _issue_ready_order, _receiver


def _inspector(name="C6 Inspector"):
    role = Role.objects.create(role=name.lower().replace(" ", "_"))
    return _actor(name, role, "inspection.decide")


def _submitted_receipt(api_client, user, supplier, product, *, suffix, quantity="5.000"):
    order, item, manager = _issue_ready_order(
        user, supplier, product, suffix=suffix, quantity=quantity
    )
    _issue(api_client, manager, order)
    receiver = _receiver(f"Receiver {suffix}")
    api_client.force_authenticate(user=receiver)
    created = api_client.post(
        "/api/v1/goods-receipts/",
        {
            "purchase_order_id": order.id,
            "items": [
                {
                    "purchase_order_item_id": item.id,
                    "received_quantity": quantity,
                }
            ],
        },
        format="json",
    )
    submitted = api_client.post(
        f"/api/v1/goods-receipts/{created.data['id']}/submit/",
        {"version": created.data["version"]},
        format="json",
    )
    return order, item, receiver, submitted.data


def _inspect(api_client, inspector, receipt, **allocation):
    api_client.force_authenticate(user=inspector)
    return api_client.post(
        f"/api/v1/goods-receipts/{receipt['id']}/inspect/",
        {
            "version": receipt["version"],
            "items": [{"receipt_item_id": receipt["items"][0]["id"], **allocation}],
        },
        format="json",
    )


@pytest.mark.django_db
def test_full_acceptance_posts_inventory_and_completes_order_and_request(
    api_client, user, supplier, product
):
    order, _, _, receipt = _submitted_receipt(
        api_client, user, supplier, product, suffix="C6-ACCEPT"
    )

    response = _inspect(
        api_client,
        _inspector(),
        receipt,
        accepted_quantity="5.000",
        defective_quantity="0",
        rejected_quantity="0",
        notes="外觀與尺寸符合",
    )

    order.refresh_from_db()
    request = order.award.rfq.request
    request.refresh_from_db()
    balance = InventoryBalance.objects.get(product=product)
    movement = InventoryMovement.objects.get()
    assert response.status_code == 200
    assert response.data["status"] == GoodsReceipt.Status.POSTED
    assert response.data["items"][0]["inspection"]["status"] == "accepted"
    assert balance.on_hand_quantity == Decimal("5.000")
    assert movement.movement_type == InventoryMovement.MovementType.RECEIPT_ACCEPT
    assert movement.quantity_delta == Decimal("5.000")
    assert order.status == PurchaseOrder.Status.RECEIVED
    assert request.status == PurchaseRequest.Status.COMPLETED


@pytest.mark.django_db
def test_partial_acceptance_only_posts_accepted_quantity_and_keeps_flow_partial(
    api_client, user, supplier, product
):
    order, _, _, receipt = _submitted_receipt(
        api_client, user, supplier, product, suffix="C6-PARTIAL"
    )

    response = _inspect(
        api_client,
        _inspector("Partial Inspector"),
        receipt,
        accepted_quantity="3",
        defective_quantity="1",
        rejected_quantity="1",
        defect_details="一件椅背刮傷",
    )

    order.refresh_from_db()
    request = order.award.rfq.request
    request.refresh_from_db()
    assert response.status_code == 200
    assert response.data["status"] == GoodsReceipt.Status.PARTIALLY_ACCEPTED
    assert InventoryBalance.objects.get(product=product).on_hand_quantity == Decimal("3.000")
    assert InventoryMovement.objects.get().quantity_delta == Decimal("3.000")
    assert order.status == PurchaseOrder.Status.PARTIALLY_RECEIVED
    assert request.status == PurchaseRequest.Status.PARTIALLY_RECEIVED


@pytest.mark.django_db
def test_rejected_receipt_does_not_create_inventory_movement(
    api_client, user, supplier, product
):
    order, _, _, receipt = _submitted_receipt(
        api_client, user, supplier, product, suffix="C6-REJECT"
    )

    response = _inspect(
        api_client,
        _inspector("Reject Inspector"),
        receipt,
        accepted_quantity="0",
        defective_quantity="0",
        rejected_quantity="5",
        notes="規格不符，整批拒收",
    )

    order.refresh_from_db()
    assert response.status_code == 200
    assert response.data["status"] == GoodsReceipt.Status.REJECTED
    assert InventoryMovement.objects.count() == 0
    assert InventoryBalance.objects.get(product=product).on_hand_quantity == Decimal("0.000")
    assert order.status == PurchaseOrder.Status.PARTIALLY_RECEIVED


@pytest.mark.django_db
def test_inspection_requires_permission_and_separates_receiver_from_inspector(
    api_client, user, supplier, product
):
    _, _, receiver, receipt = _submitted_receipt(
        api_client, user, supplier, product, suffix="C6-SOD"
    )

    denied = _inspect(
        api_client,
        receiver,
        receipt,
        accepted_quantity="5",
        defective_quantity="0",
        rejected_quantity="0",
    )
    both_role = Role.objects.create(role="receiver_and_inspector")
    both = _actor(
        "Receiver Inspector",
        both_role,
        "receipt.record",
        "inspection.decide",
    )
    GoodsReceipt.objects.filter(pk=receipt["id"]).update(received_by=both)
    separated = _inspect(
        api_client,
        both,
        receipt,
        accepted_quantity="5",
        defective_quantity="0",
        rejected_quantity="0",
    )

    assert denied.status_code == 403
    assert separated.status_code == 403
    assert QualityInspection.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("allocation", "expected_status"),
    [
        (
            {
                "accepted_quantity": "4",
                "defective_quantity": "0",
                "rejected_quantity": "0",
            },
            400,
        ),
        (
            {
                "accepted_quantity": "4",
                "defective_quantity": "1",
                "rejected_quantity": "0",
            },
            400,
        ),
        (
            {
                "accepted_quantity": "NaN",
                "defective_quantity": "0",
                "rejected_quantity": "0",
            },
            400,
        ),
    ],
)
def test_inspection_rejects_quantity_mismatch_missing_defect_details_and_invalid_number(
    api_client, user, supplier, product, allocation, expected_status
):
    _, _, _, receipt = _submitted_receipt(
        api_client, user, supplier, product, suffix=f"C6-INVALID-{allocation['accepted_quantity']}"
    )

    response = _inspect(
        api_client, _inspector(f"Invalid {allocation['accepted_quantity']}"), receipt, **allocation
    )

    assert response.status_code == expected_status
    assert QualityInspection.objects.count() == 0
    assert InventoryMovement.objects.count() == 0


@pytest.mark.django_db
def test_inspection_is_idempotent_and_cannot_post_inventory_twice(
    api_client, user, supplier, product
):
    _, _, _, receipt = _submitted_receipt(
        api_client, user, supplier, product, suffix="C6-IDEMPOTENT"
    )
    inspector = _inspector("Idempotent Inspector")
    payload = {
        "accepted_quantity": "5",
        "defective_quantity": "0",
        "rejected_quantity": "0",
    }

    first = _inspect(api_client, inspector, receipt, **payload)
    repeated = _inspect(api_client, inspector, receipt, **payload)

    assert first.status_code == 200
    assert repeated.status_code == 409
    assert QualityInspection.objects.count() == 1
    assert InventoryMovement.objects.count() == 1
    assert InventoryBalance.objects.get(product=product).on_hand_quantity == Decimal("5.000")


@pytest.mark.django_db
def test_inspection_rejects_invalid_version_missing_receipt_and_incomplete_payload(
    api_client, user, supplier, product
):
    _, _, _, receipt = _submitted_receipt(
        api_client, user, supplier, product, suffix="C6-GUARDS"
    )
    inspector = _inspector("Guard Inspector")
    api_client.force_authenticate(user=inspector)

    invalid_version = api_client.post(
        f"/api/v1/goods-receipts/{receipt['id']}/inspect/",
        {"version": 0, "items": []},
        format="json",
    )
    stale_version = api_client.post(
        f"/api/v1/goods-receipts/{receipt['id']}/inspect/",
        {"version": 999, "items": []},
        format="json",
    )
    missing_receipt = api_client.post(
        "/api/v1/goods-receipts/999999/inspect/",
        {"version": 1, "items": []},
        format="json",
    )
    incomplete = api_client.post(
        f"/api/v1/goods-receipts/{receipt['id']}/inspect/",
        {"version": receipt["version"], "items": []},
        format="json",
    )

    assert invalid_version.status_code == 400
    assert stale_version.status_code == 409
    assert missing_receipt.status_code == 404
    assert incomplete.status_code == 400
    assert QualityInspection.objects.count() == 0


@pytest.mark.django_db
def test_inspection_rolls_back_when_po_item_has_no_inventory_product(
    api_client, user, supplier, product
):
    _, item, _, receipt = _submitted_receipt(
        api_client, user, supplier, product, suffix="C6-NO-PRODUCT"
    )
    item.product = None
    item.save(update_fields=["product"])

    response = _inspect(
        api_client,
        _inspector("No Product Inspector"),
        receipt,
        accepted_quantity="5",
        defective_quantity="0",
        rejected_quantity="0",
    )

    assert response.status_code == 409
    assert QualityInspection.objects.count() == 0
    assert InventoryMovement.objects.count() == 0
