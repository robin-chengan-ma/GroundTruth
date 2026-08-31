"""收貨、驗收與差異結案後的採購單／申請單狀態彙總。"""

from decimal import Decimal

from django.utils import timezone

from apps.procurement.models import PurchaseOrder, PurchaseRequest
from repositories.erp import InspectionVarianceRepository
from repositories.procurement import PurchaseOrderRepository


def roll_up_purchase_order(purchase_order):
    all_accepted = True
    all_accounted = True
    any_final_receipt = False
    for order_item in purchase_order.items.all():
        accepted = Decimal(
            InspectionVarianceRepository.accepted_quantity_for_order_item(
                order_item.id
            )
        )
        commercially_resolved = Decimal(
            InspectionVarianceRepository.commercially_resolved_quantity_for_order_item(
                order_item.id
            )
        )
        all_accepted = all_accepted and accepted == order_item.ordered_quantity
        all_accounted = all_accounted and (
            accepted + commercially_resolved == order_item.ordered_quantity
        )
        if InspectionVarianceRepository.has_inspection_for_order_item(order_item.id):
            any_final_receipt = True

    if all_accepted:
        new_status = PurchaseOrder.Status.RECEIVED
    elif all_accounted:
        new_status = PurchaseOrder.Status.CLOSED
    elif any_final_receipt:
        new_status = PurchaseOrder.Status.PARTIALLY_RECEIVED
    else:
        new_status = PurchaseOrder.Status.ISSUED

    if purchase_order.status != new_status:
        purchase_order.status = new_status
        purchase_order.closed_at = (
            timezone.now() if new_status == PurchaseOrder.Status.CLOSED else None
        )
        purchase_order.version += 1
        purchase_order.save(
            update_fields=["status", "closed_at", "version", "updated_at"]
        )


def roll_up_purchase_request(purchase_order):
    request = purchase_order.award.rfq.request
    statuses = PurchaseOrderRepository.statuses_for_request_for_update(request.id)
    terminal = {PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.CLOSED}
    new_status = (
        PurchaseRequest.Status.COMPLETED
        if statuses and all(status in terminal for status in statuses)
        else PurchaseRequest.Status.PARTIALLY_RECEIVED
    )
    if request.status != new_status:
        request.status = new_status
        request.version += 1
        request.save(update_fields=["status", "version", "updated_at"])
        if new_status == PurchaseRequest.Status.COMPLETED:
            from services.purchase_suggestion_service import mark_request_processed

            mark_request_processed(request.id)


def roll_up_purchase_documents(purchase_order):
    roll_up_purchase_order(purchase_order)
    roll_up_purchase_request(purchase_order)
