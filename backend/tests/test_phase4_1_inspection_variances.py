from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.erp.models import (
    GoodsReceipt,
    GoodsReceiptItem,
    InspectionVarianceCase,
    InspectionVarianceLine,
    QualityInspection,
)
from tests.test_phase4_1_quality_inspections import _inspect, _inspector, _submitted_receipt


def _partial_inspection(api_client, user, supplier, product, suffix):
    order, item, receiver, receipt = _submitted_receipt(
        api_client, user, supplier, product, suffix=suffix
    )
    response = _inspect(
        api_client,
        _inspector(f"Variance Inspector {suffix}"),
        receipt,
        accepted_quantity="3",
        defective_quantity="1",
        rejected_quantity="1",
        defect_details="外觀瑕疵與規格不符",
    )
    return order, item, receiver, QualityInspection.objects.get(
        receipt_item_id=response.data["items"][0]["id"]
    )


@pytest.mark.django_db(transaction=True)
def test_open_variance_requires_full_quantity_allocation(api_client, user, supplier, product):
    _, _, _, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-ALLOC"
    )
    variance = InspectionVarianceCase.objects.create(
        quality_inspection=inspection,
        created_by=user,
        submitted_by=user,
        submitted_at=timezone.now(),
    )
    InspectionVarianceLine.objects.create(
        variance_case=variance,
        action_type=InspectionVarianceLine.ActionType.REPLACEMENT,
        quantity=Decimal("1.000"),
        reason="要求補交",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            variance.status = InspectionVarianceCase.Status.OPEN
            variance.save(update_fields=["status"])
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS inspection_variance_case_check IMMEDIATE")


@pytest.mark.django_db(transaction=True)
def test_authorized_replacement_can_exceed_original_receipt_cap_but_not_authorization(
    api_client, user, supplier, product
):
    order, item, receiver, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-REPLACE"
    )
    variance = InspectionVarianceCase.objects.create(
        quality_inspection=inspection,
        created_by=user,
        submitted_by=user,
        submitted_at=timezone.now(),
    )
    line = InspectionVarianceLine.objects.create(
        variance_case=variance,
        action_type=InspectionVarianceLine.ActionType.REPLACEMENT,
        quantity=Decimal("2.000"),
        reason="要求補足兩件",
    )
    variance.status = InspectionVarianceCase.Status.OPEN
    variance.save(update_fields=["status"])
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS inspection_variance_case_check IMMEDIATE")

    replacement = GoodsReceipt.objects.create(
        receipt_no="GR-C6-REPLACEMENT-001",
        purchase_order=order,
        received_by=receiver,
    )
    GoodsReceiptItem.objects.create(
        receipt=replacement,
        purchase_order_item=item,
        received_quantity=Decimal("2.000"),
        replacement_variance_line=line,
    )

    overflow = GoodsReceipt.objects.create(
        receipt_no="GR-C6-REPLACEMENT-002",
        purchase_order=order,
        received_by=receiver,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GoodsReceiptItem.objects.create(
                receipt=overflow,
                purchase_order_item=item,
                received_quantity=Decimal("0.001"),
                replacement_variance_line=line,
            )


@pytest.mark.django_db(transaction=True)
def test_open_variance_line_allows_only_controlled_completion(
    api_client, user, supplier, product
):
    _, _, _, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-COMPLETE"
    )
    variance = InspectionVarianceCase.objects.create(
        quality_inspection=inspection,
        created_by=user,
        submitted_by=user,
        submitted_at=timezone.now(),
    )
    line = InspectionVarianceLine.objects.create(
        variance_case=variance,
        action_type=InspectionVarianceLine.ActionType.CREDIT,
        quantity=Decimal("2.000"),
        reason="供應商同意折讓",
    )
    variance.status = InspectionVarianceCase.Status.OPEN
    variance.save(update_fields=["status"])
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS inspection_variance_case_check IMMEDIATE")

    completed_at = timezone.now()
    line.status = InspectionVarianceLine.Status.COMPLETED
    line.completed_by = user
    line.completed_at = completed_at
    line.save(update_fields=["status", "completed_by", "completed_at"])

    line.refresh_from_db()
    assert line.status == InspectionVarianceLine.Status.COMPLETED
    assert line.completed_by_id == user.id
    assert line.completed_at == completed_at

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            line.reason = "不得改寫正式理由"
            line.save(update_fields=["reason"])


@pytest.mark.django_db(transaction=True)
def test_closed_variance_rejects_new_replacement_receipt(
    api_client, user, supplier, product
):
    order, item, receiver, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-CLOSED"
    )
    variance = InspectionVarianceCase.objects.create(
        quality_inspection=inspection,
        created_by=user,
        submitted_by=user,
        submitted_at=timezone.now(),
    )
    line = InspectionVarianceLine.objects.create(
        variance_case=variance,
        action_type=InspectionVarianceLine.ActionType.REPLACEMENT,
        quantity=Decimal("2.000"),
        reason="要求補足兩件",
    )
    variance.status = InspectionVarianceCase.Status.OPEN
    variance.save(update_fields=["status"])
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS inspection_variance_case_check IMMEDIATE")
    line.status = InspectionVarianceLine.Status.COMPLETED
    line.completed_by = user
    line.completed_at = timezone.now()
    line.save(update_fields=["status", "completed_by", "completed_at"])
    variance.status = InspectionVarianceCase.Status.CLOSED
    variance.closed_by = user
    variance.closed_at = timezone.now()
    variance.save(update_fields=["status", "closed_by", "closed_at"])
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS inspection_variance_case_check IMMEDIATE")

    replacement = GoodsReceipt.objects.create(
        receipt_no="GR-C6-CLOSED-REPLACEMENT",
        purchase_order=order,
        received_by=receiver,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GoodsReceiptItem.objects.create(
                receipt=replacement,
                purchase_order_item=item,
                received_quantity=Decimal("1.000"),
                replacement_variance_line=line,
            )


@pytest.mark.django_db(transaction=True)
def test_variance_case_cannot_close_with_pending_lines(
    api_client, user, supplier, product
):
    _, _, _, inspection = _partial_inspection(
        api_client, user, supplier, product, "C6-VARIANCE-PENDING-CLOSE"
    )
    variance = InspectionVarianceCase.objects.create(
        quality_inspection=inspection,
        created_by=user,
        submitted_by=user,
        submitted_at=timezone.now(),
    )
    InspectionVarianceLine.objects.create(
        variance_case=variance,
        action_type=InspectionVarianceLine.ActionType.CREDIT,
        quantity=Decimal("2.000"),
        reason="供應商折讓尚未完成",
    )
    variance.status = InspectionVarianceCase.Status.OPEN
    variance.save(update_fields=["status"])
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS inspection_variance_case_check IMMEDIATE")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            variance.status = InspectionVarianceCase.Status.CLOSED
            variance.closed_by = user
            variance.closed_at = timezone.now()
            variance.save(update_fields=["status", "closed_by", "closed_at"])
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS inspection_variance_case_check IMMEDIATE")
