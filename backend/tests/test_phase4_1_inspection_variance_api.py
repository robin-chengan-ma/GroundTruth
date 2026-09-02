from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.core.models import Role
from apps.erp.models import (
    GoodsReceiptItem,
    InspectionVarianceCase,
    InspectionVarianceLine,
    InventoryBalance,
    InventoryMovement,
)
from apps.procurement.models import PurchaseOrder, PurchaseRequest
from tests.test_phase4_1_approval_workflow import _actor
from tests.test_phase4_1_goods_receipts import _receiver
from tests.test_phase4_1_inspection_variances import _partial_inspection
from tests.test_phase4_1_quality_inspections import _inspector


def _buyer(name="C6 Variance Buyer"):
    role = Role.objects.create(role=name.lower().replace(" ", "_"))
    return _actor(name, role, "purchase_order.manage")


def _payload(inspection_id, *, version=None):
    payload = {
        "quality_inspection_id": inspection_id,
        "lines": [
            {"action_type": "replacement", "quantity": "1.000", "reason": "補交一件"},
            {"action_type": "credit", "quantity": "1.000", "reason": "另一件折讓"},
        ],
    }
    if version is not None:
        payload["version"] = version
    return payload


@pytest.mark.django_db
def test_buyer_can_create_read_update_and_delete_variance_draft(
    api_client, user, supplier, product
):
    _, _, _, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-API-CRUD"
    )
    buyer = _buyer()
    api_client.force_authenticate(user=buyer)

    created = api_client.post(
        "/api/v1/inspection-variances/", _payload(inspection.id), format="json"
    )
    detail = api_client.get(f"/api/v1/inspection-variances/{created.data['id']}/")
    updated = api_client.put(
        f"/api/v1/inspection-variances/{created.data['id']}/",
        {
            "version": created.data["version"],
            "lines": [
                {"action_type": "return", "quantity": "2.000", "reason": "退回供應商"}
            ],
        },
        format="json",
    )
    deleted = api_client.delete(
        f"/api/v1/inspection-variances/{created.data['id']}/",
        {"version": updated.data["version"]},
        format="json",
    )

    assert created.status_code == 201
    assert detail.status_code == 200
    assert created.data["status"] == "draft"
    assert len(created.data["lines"]) == 2
    assert updated.status_code == 200
    assert updated.data["version"] == 2
    assert updated.data["lines"][0]["action_type"] == "return"
    assert deleted.status_code == 204
    assert not InspectionVarianceCase.objects.filter(pk=created.data["id"]).exists()


@pytest.mark.django_db
def test_submit_variance_opens_and_locks_full_allocation(
    api_client, user, supplier, product
):
    _, _, _, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-API-SUBMIT"
    )
    buyer = _buyer("C6 Submit Buyer")
    api_client.force_authenticate(user=buyer)
    created = api_client.post(
        "/api/v1/inspection-variances/", _payload(inspection.id), format="json"
    )

    submitted = api_client.post(
        f"/api/v1/inspection-variances/{created.data['id']}/submit/",
        {"version": created.data["version"]},
        format="json",
    )
    locked_update = api_client.put(
        f"/api/v1/inspection-variances/{created.data['id']}/",
        {"version": submitted.data["version"], "lines": []},
        format="json",
    )

    assert submitted.status_code == 200
    assert submitted.data["status"] == "open"
    assert submitted.data["submitted_by"]["id"] == buyer.id
    assert submitted.data["submitted_at"] is not None
    assert locked_update.status_code == 409
    assert AuditLog.objects.filter(action_type="inspection_variance_submitted").exists()


@pytest.mark.django_db
def test_variance_rejects_invalid_allocation_duplicate_inspection_and_stale_version(
    api_client, user, supplier, product
):
    _, _, _, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-API-GUARDS"
    )
    buyer = _buyer("C6 Guard Buyer")
    api_client.force_authenticate(user=buyer)

    invalid = api_client.post(
        "/api/v1/inspection-variances/",
        {
            "quality_inspection_id": inspection.id,
            "lines": [{"action_type": "credit", "quantity": "2.001", "reason": "超額"}],
        },
        format="json",
    )
    created = api_client.post(
        "/api/v1/inspection-variances/", _payload(inspection.id), format="json"
    )
    duplicate = api_client.post(
        "/api/v1/inspection-variances/", _payload(inspection.id), format="json"
    )
    stale = api_client.post(
        f"/api/v1/inspection-variances/{created.data['id']}/submit/",
        {"version": 99},
        format="json",
    )

    assert invalid.status_code == 400
    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert stale.status_code == 409
    assert InspectionVarianceCase.objects.count() == 1


@pytest.mark.django_db
def test_only_buyer_manages_variance_while_operational_roles_and_auditor_read(
    api_client, user, supplier, product
):
    _, _, _, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-API-RBAC"
    )
    buyer = _buyer("C6 RBAC Buyer")
    api_client.force_authenticate(user=buyer)
    created = api_client.post(
        "/api/v1/inspection-variances/", _payload(inspection.id), format="json"
    )

    inspector = _inspector("C6 Read Inspector")
    api_client.force_authenticate(user=inspector)
    inspector_list = api_client.get("/api/v1/inspection-variances/")
    inspector_write = api_client.post(
        "/api/v1/inspection-variances/", _payload(inspection.id), format="json"
    )
    audit_role = Role.objects.create(role="c6_variance_auditor")
    auditor = _actor("C6 Variance Auditor", audit_role, "audit.read")
    api_client.force_authenticate(user=auditor)
    audit_detail = api_client.get(f"/api/v1/inspection-variances/{created.data['id']}/")

    assert inspector_list.status_code == 200
    assert inspector_list.data["results"][0]["id"] == created.data["id"]
    assert inspector_write.status_code == 403
    assert audit_detail.status_code == 200


@pytest.mark.django_db
def test_variance_requires_failed_inspection_and_valid_line_fields(
    api_client, user, supplier, product
):
    _, _, _, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-API-FIELDS"
    )
    buyer = _buyer("C6 Fields Buyer")
    api_client.force_authenticate(user=buyer)

    invalid_action = api_client.post(
        "/api/v1/inspection-variances/",
        {
            "quality_inspection_id": inspection.id,
            "lines": [{"action_type": "refund", "quantity": "1", "reason": "x"}],
        },
        format="json",
    )
    invalid_quantity = api_client.post(
        "/api/v1/inspection-variances/",
        {
            "quality_inspection_id": inspection.id,
            "lines": [{"action_type": "credit", "quantity": "NaN", "reason": "x"}],
        },
        format="json",
    )
    blank_reason = api_client.post(
        "/api/v1/inspection-variances/",
        {
            "quality_inspection_id": inspection.id,
            "lines": [{"action_type": "credit", "quantity": "1", "reason": "  "}],
        },
        format="json",
    )

    assert invalid_action.status_code == 400
    assert invalid_quantity.status_code == 400
    assert blank_reason.status_code == 400
    assert InspectionVarianceLine.objects.count() == 0


def _create_and_submit_case(api_client, buyer, inspection, lines):
    api_client.force_authenticate(user=buyer)
    created = api_client.post(
        "/api/v1/inspection-variances/",
        {"quality_inspection_id": inspection.id, "lines": lines},
        format="json",
    )
    return api_client.post(
        f"/api/v1/inspection-variances/{created.data['id']}/submit/",
        {"version": created.data["version"]},
        format="json",
    )


@pytest.mark.django_db
def test_buyer_completes_commercial_lines_without_inventory_movement(
    api_client, user, supplier, product
):
    _, _, _, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-COMPLETE"
    )
    buyer = _buyer("C6 Complete Buyer")
    submitted = _create_and_submit_case(
        api_client,
        buyer,
        inspection,
        [
            {"action_type": "return", "quantity": "1", "reason": "拒收退回"},
            {"action_type": "credit", "quantity": "1", "reason": "折讓結案"},
        ],
    )

    first = api_client.post(
        f"/api/v1/inspection-variances/{submitted.data['id']}/complete-line/",
        {"version": submitted.data["version"], "line_id": submitted.data["lines"][0]["id"]},
        format="json",
    )
    second = api_client.post(
        f"/api/v1/inspection-variances/{submitted.data['id']}/complete-line/",
        {"version": first.data["version"], "line_id": submitted.data["lines"][1]["id"]},
        format="json",
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert all(line["status"] == "completed" for line in second.data["lines"])
    assert all(line["completed_by"]["id"] == buyer.id for line in second.data["lines"])
    assert InventoryMovement.objects.count() == 1  # 僅原驗收的合格入庫
    assert AuditLog.objects.filter(action_type="inspection_variance_line_completed").count() == 2


@pytest.mark.django_db
def test_replacement_must_be_received_and_reinspected_before_line_completes(
    api_client, user, supplier, product
):
    order, item, _, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-REPLACEMENT"
    )
    buyer = _buyer("C6 Replacement Buyer")
    submitted = _create_and_submit_case(
        api_client,
        buyer,
        inspection,
        [
            {"action_type": "replacement", "quantity": "2", "reason": "補交兩件"},
        ],
    )
    line = submitted.data["lines"][0]
    manual = api_client.post(
        f"/api/v1/inspection-variances/{submitted.data['id']}/complete-line/",
        {"version": submitted.data["version"], "line_id": line["id"]},
        format="json",
    )

    receiver = _receiver("C6 Replacement Receiver")
    api_client.force_authenticate(user=receiver)
    receipt = api_client.post(
        "/api/v1/goods-receipts/",
        {
            "purchase_order_id": order.id,
            "items": [{
                "purchase_order_item_id": item.id,
                "received_quantity": "2",
                "replacement_variance_line_id": line["id"],
            }],
        },
        format="json",
    )
    submitted_receipt = api_client.post(
        f"/api/v1/goods-receipts/{receipt.data['id']}/submit/",
        {"version": receipt.data["version"]},
        format="json",
    )
    balance_before = InventoryBalance.objects.get(product=product).in_transit_quantity
    inspector = _inspector("C6 Replacement Inspector")
    api_client.force_authenticate(user=inspector)
    inspected = api_client.post(
        f"/api/v1/goods-receipts/{receipt.data['id']}/inspect/",
        {
            "version": submitted_receipt.data["version"],
            "items": [{
                "receipt_item_id": receipt.data["items"][0]["id"],
                "accepted_quantity": "2",
                "defective_quantity": "0",
                "rejected_quantity": "0",
            }],
        },
        format="json",
    )

    assert manual.status_code == 409
    assert receipt.status_code == 201
    assert receipt.data["items"][0]["replacement_variance_line_id"] == line["id"]
    assert balance_before == Decimal("0.000")
    assert inspected.status_code == 200
    assert InspectionVarianceLine.objects.get(pk=line["id"]).status == "completed"
    assert GoodsReceiptItem.objects.get(pk=receipt.data["items"][0]["id"]).replacement_variance_line_id == line["id"]


@pytest.mark.django_db
def test_variance_closes_only_after_all_lines_complete_and_rolls_up_documents(
    api_client, user, supplier, product
):
    order, _, _, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-CLOSE"
    )
    buyer = _buyer("C6 Close Buyer")
    submitted = _create_and_submit_case(
        api_client,
        buyer,
        inspection,
        [{"action_type": "waive", "quantity": "2", "reason": "接受短交結案"}],
    )
    blocked = api_client.post(
        f"/api/v1/inspection-variances/{submitted.data['id']}/close/",
        {"version": submitted.data["version"]},
        format="json",
    )
    completed = api_client.post(
        f"/api/v1/inspection-variances/{submitted.data['id']}/complete-line/",
        {"version": submitted.data["version"], "line_id": submitted.data["lines"][0]["id"]},
        format="json",
    )
    closed = api_client.post(
        f"/api/v1/inspection-variances/{submitted.data['id']}/close/",
        {"version": completed.data["version"]},
        format="json",
    )

    order.refresh_from_db()
    request = order.award.rfq.request
    request.refresh_from_db()
    assert blocked.status_code == 409
    assert closed.status_code == 200
    assert closed.data["status"] == "closed"
    assert closed.data["closed_by"]["id"] == buyer.id
    assert order.status == PurchaseOrder.Status.CLOSED
    assert request.status == PurchaseRequest.Status.COMPLETED
