from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.crm.models import Supplier
from apps.procurement.models import (
    PurchaseRequest,
    PurchaseRequestItem,
    RequestItemRequirement,
    Rfq,
    RfqSupplier,
)


@pytest.mark.django_db
def test_purchase_request_supports_multiple_decimal_quantity_items(user, product):
    request = PurchaseRequest.objects.create(
        request_no="PR-20260828-001",
        requester=user,
        purpose="添購辦公設備",
        currency="TWD",
        idempotency_key="demo-request-001",
    )
    first = PurchaseRequestItem.objects.create(
        request=request,
        line_no=1,
        product=product,
        description_snapshot="A產品-辦公椅",
        specification_snapshot={"material": "網布"},
        quantity=Decimal("5.000"),
        unit_of_measure="EA",
    )
    second = PurchaseRequestItem.objects.create(
        request=request,
        line_no=2,
        description_snapshot="客製會議桌",
        specification_snapshot={"width_cm": 180},
        quantity=Decimal("1.500"),
        unit_of_measure="SET",
    )

    assert list(request.items.order_by("line_no")) == [first, second]


@pytest.mark.django_db
def test_purchase_request_idempotency_key_is_unique(user):
    PurchaseRequest.objects.create(
        request_no="PR-20260828-002",
        requester=user,
        purpose="第一次提交",
        idempotency_key="same-key",
    )

    with pytest.raises(IntegrityError):
        PurchaseRequest.objects.create(
            request_no="PR-20260828-003",
            requester=user,
            purpose="重複提交",
            idempotency_key="same-key",
        )


@pytest.mark.django_db
def test_purchase_request_item_requires_object_specification(user):
    request = PurchaseRequest.objects.create(
        request_no="PR-20260828-004",
        requester=user,
        purpose="規格驗證",
    )
    item = PurchaseRequestItem(
        request=request,
        line_no=1,
        description_snapshot="辦公椅",
        specification_snapshot=["網布"],
        quantity=Decimal("1.000"),
        unit_of_measure="EA",
    )

    with pytest.raises(ValidationError, match="JSON object"):
        item.full_clean()


@pytest.mark.django_db
def test_request_item_requirement_code_is_unique_per_item(user):
    request = PurchaseRequest.objects.create(
        request_no="PR-20260828-005",
        requester=user,
        purpose="必要條件",
    )
    item = PurchaseRequestItem.objects.create(
        request=request,
        line_no=1,
        description_snapshot="辦公椅",
        quantity=Decimal("1.000"),
        unit_of_measure="EA",
    )
    RequestItemRequirement.objects.create(
        request_item=item,
        code="material",
        label="材質",
        data_type="string",
        operator="equals",
        expected_value="網布",
        is_mandatory=True,
    )

    with pytest.raises(IntegrityError):
        RequestItemRequirement.objects.create(
            request_item=item,
            code="material",
            label="材質重複",
            data_type="string",
            operator="equals",
            expected_value="皮革",
        )


@pytest.mark.django_db
def test_only_one_active_rfq_revision_per_purchase_request(user):
    request = PurchaseRequest.objects.create(
        request_no="PR-20260828-006",
        requester=user,
        purpose="詢價",
    )
    Rfq.objects.create(rfq_no="RFQ-20260828-001", request=request, revision=1, status="draft")

    with pytest.raises(IntegrityError), transaction.atomic():
        Rfq.objects.create(rfq_no="RFQ-20260828-001", request=request, revision=2, status="draft")

    Rfq.objects.filter(request=request).update(status="cancelled")
    revised = Rfq.objects.create(
        rfq_no="RFQ-20260828-001",
        request=request,
        revision=2,
        status="draft",
    )

    assert revised.revision == 2


@pytest.mark.django_db
def test_rfq_can_invite_multiple_suppliers(user, supplier):
    request = PurchaseRequest.objects.create(
        request_no="PR-20260828-007",
        requester=user,
        purpose="多供應商比價",
    )
    rfq = Rfq.objects.create(rfq_no="RFQ-20260828-002", request=request, revision=1)
    another_supplier = Supplier.objects.create(name="第二供應商")
    invited_at = timezone.now()

    RfqSupplier.objects.create(rfq=rfq, supplier=supplier, invited_at=invited_at)
    RfqSupplier.objects.create(
        rfq=rfq,
        supplier=another_supplier,
        invited_at=invited_at,
        responded_at=invited_at + timedelta(hours=1),
        status="responded",
    )

    assert rfq.invited_suppliers.count() == 2
