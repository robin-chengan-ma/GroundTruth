from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import Permission, RolePermission, UserRole
from apps.erp.models import GoodsReceipt, Inventory, PurchaseSuggestion, QualityInspection
from apps.procurement.models import PurchaseRequest
from services.inventory_balance_service import post_accepted_inventory
from tests.test_phase4_1_receiving_inventory import create_purchase_order

pytestmark = pytest.mark.django_db


def _grant(role, *codes):
    for code in codes:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={"name": code})
        RolePermission.objects.get_or_create(role=role, permission=permission)


def _activate_role(user):
    UserRole.objects.get_or_create(user=user, role=user.role)


def test_inventory_post_creates_one_pending_suggestion_when_still_below_threshold(
    user, supplier, product,
):
    Inventory.objects.create(product=product, stock_qty=0, threshold=10)
    purchase_order, purchase_order_item = create_purchase_order(
        user, supplier, product, quantity="4.000"
    )
    receipt_item = GoodsReceipt.objects.create(
        purchase_order=purchase_order,
        receipt_no="GR-SUGGEST-1", received_by=user
    ).items.create(
        purchase_order_item=purchase_order_item, received_quantity=Decimal("3.000")
    )
    inspection = QualityInspection.objects.create(
        receipt_item=receipt_item,
        status=QualityInspection.Status.ACCEPTED,
        accepted_quantity=Decimal("3.000"),
        defective_quantity=Decimal("0.000"),
        rejected_quantity=Decimal("0.000"),
        inspected_by=user,
        inspected_at=timezone.now(),
    )

    first_movement = post_accepted_inventory(inspection, user)

    suggestion = PurchaseSuggestion.objects.get()
    assert suggestion.product == product
    assert suggestion.suggested_qty == Decimal("7.000")
    assert suggestion.source_movement == first_movement
    assert suggestion.status == PurchaseSuggestion.Status.PENDING

    second_inspection = QualityInspection.objects.create(
        receipt_item=GoodsReceipt.objects.create(
            purchase_order=purchase_order, receipt_no="GR-SUGGEST-2", received_by=user
        ).items.create(
            purchase_order_item=purchase_order_item, received_quantity=Decimal("1.000")
        ),
        accepted_quantity=Decimal("1.000"),
        status=QualityInspection.Status.ACCEPTED,
        defective_quantity=Decimal("0.000"),
        rejected_quantity=Decimal("0.000"),
        inspected_by=user,
        inspected_at=timezone.now(),
    )
    post_accepted_inventory(second_inspection, user)
    assert PurchaseSuggestion.objects.count() == 1


def test_convert_suggestion_creates_linked_draft_and_submit_marks_in_progress(
    api_client, user, supplier, product,
):
    _grant(
        user.role,
        "purchase_request.create",
        "purchase_request.read_own",
        "purchase_request.submit",
    )
    _activate_role(user)
    api_client.force_authenticate(user=user)
    suggestion = PurchaseSuggestion.objects.create(product=product, suggested_qty="8.000")

    converted = api_client.post(
        f"/api/v1/purchase-suggestions/{suggestion.id}/convert/",
        {"supplier_ids": [supplier.id], "purpose": "低庫存自動補貨"},
        format="json",
    )

    assert converted.status_code == 201
    suggestion.refresh_from_db()
    request = PurchaseRequest.objects.get(pk=converted.data["purchase_request_id"])
    assert suggestion.purchase_request == request
    assert suggestion.status == PurchaseSuggestion.Status.PENDING
    assert request.status == PurchaseRequest.Status.DRAFT
    assert request.items.get().product == product
    assert request.items.get().quantity == Decimal("8.000")

    submitted = api_client.post(
        f"/api/v1/purchase-request-drafts/{request.id}/submit/",
        {"version": request.version, "idempotency_key": "suggestion-submit-1"},
        format="json",
    )
    assert submitted.status_code == 200
    suggestion.refresh_from_db()
    assert suggestion.status == PurchaseSuggestion.Status.IN_PROGRESS


def test_admin_can_dismiss_pending_but_cannot_dismiss_converted_suggestion(
    admin_api_client, user, supplier, product,
):
    pending = PurchaseSuggestion.objects.create(product=product, suggested_qty="5.000")
    dismissed = admin_api_client.post(
        f"/api/v1/purchase-suggestions/{pending.id}/dismiss/", {}, format="json"
    )
    assert dismissed.status_code == 200
    pending.refresh_from_db()
    assert pending.status == PurchaseSuggestion.Status.DISMISSED

    linked_request = PurchaseRequest.objects.create(
        request_no="PR-SUGGEST-LINKED", requester=user, source="inventory_suggestion"
    )
    linked = PurchaseSuggestion.objects.create(
        product=product, suggested_qty="5.000", purchase_request=linked_request
    )
    conflict = admin_api_client.post(
        f"/api/v1/purchase-suggestions/{linked.id}/dismiss/", {}, format="json"
    )
    assert conflict.status_code == 409


def test_completed_request_marks_source_suggestion_processed(user, supplier, product):
    purchase_order, _ = create_purchase_order(user, supplier, product, quantity="2.000")
    request = purchase_order.award.rfq.request
    suggestion = PurchaseSuggestion.objects.create(
        product=product,
        suggested_qty="2.000",
        status=PurchaseSuggestion.Status.IN_PROGRESS,
        purchase_request=request,
    )
    purchase_order.status = purchase_order.Status.RECEIVED
    purchase_order.save(update_fields=["status"])

    from services.purchase_receiving_rollup_service import roll_up_purchase_request

    roll_up_purchase_request(purchase_order)

    suggestion.refresh_from_db()
    assert request.__class__.objects.get(pk=request.pk).status == PurchaseRequest.Status.COMPLETED
    assert suggestion.status == PurchaseSuggestion.Status.PROCESSED
