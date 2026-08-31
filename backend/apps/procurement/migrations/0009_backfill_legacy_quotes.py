from decimal import Decimal

from django.db import migrations
from django.db.models import Q

REQUEST_STATUS = {
    "pending_verification": "sourcing",
    "pending_review": "sourcing",
    "pending_approval": "approval",
    "approved": "completed",
    "rejected": "cancelled",
    "cancelled": "cancelled",
}
RFQ_STATUS = {
    "pending_verification": "collecting",
    "pending_review": "evaluating",
    "pending_approval": "evaluating",
    "approved": "closed",
    "rejected": "closed",
    "cancelled": "cancelled",
}
AWARD_STATUS = {
    "pending_verification": "draft",
    "pending_review": "draft",
    "pending_approval": "submitted",
    "approved": "approved",
    "rejected": "rejected",
    "cancelled": "cancelled",
}
CASE_STATUS = {
    "pending_approval": "pending",
    "approved": "approved",
    "rejected": "rejected",
}


def _migration_error(quote_id, code):
    raise RuntimeError(f"legacy_quote_id={quote_id};code={code}")


def _policy_for_quote(ApprovalPolicy, quote):
    policies = ApprovalPolicy.objects.filter(
        currency=quote.currency,
        is_active=True,
        min_amount__lte=quote.total_amount,
    ).filter(Q(max_amount__isnull=True) | Q(max_amount__gt=quote.total_amount))
    policy = policies.order_by("-active_from", "id").first()
    if policy is None:
        _migration_error(quote.id, "approval_policy_missing")
    return policy


def _preflight(Quote, ApprovalPolicy):
    quotes = list(
        Quote.objects.select_for_update(of=("self",))
        .select_related("user", "supplier", "product")
        .prefetch_related("approvals")
    )
    for quote in quotes:
        if quote.status not in REQUEST_STATUS:
            _migration_error(quote.id, "unknown_status")
        if quote.quantity <= 0:
            _migration_error(quote.id, "quantity_nonpositive")
        if quote.currency != quote.currency.upper() or len(quote.currency) != 3:
            _migration_error(quote.id, "currency_invalid")
        if quote.total_amount != (quote.price * Decimal(quote.quantity)).quantize(Decimal("0.01")):
            _migration_error(quote.id, "amount_mismatch")
        approvals = list(quote.approvals.all())
        if len(approvals) > 1:
            _migration_error(quote.id, "approval_duplicate")
        approval = approvals[0] if approvals else None
        if quote.status == "pending_approval" and (approval is None or approval.status != "pending"):
            _migration_error(quote.id, "pending_approval_inconsistent")
        if quote.status == "approved" and approval is not None and approval.status != "approved":
            _migration_error(quote.id, "approved_approval_inconsistent")
        if quote.status == "rejected" and (approval is None or approval.status != "rejected"):
            _migration_error(quote.id, "rejected_approval_inconsistent")
        if approval is not None and approval.status in {"approved", "rejected"} and approval.approver_id is None:
            _migration_error(quote.id, "approval_actor_missing")
        if quote.status in CASE_STATUS:
            _policy_for_quote(ApprovalPolicy, quote)
    return quotes


def forwards(apps, schema_editor):
    Quote = apps.get_model("procurement", "Quote")
    PurchaseRequest = apps.get_model("procurement", "PurchaseRequest")
    PurchaseRequestItem = apps.get_model("procurement", "PurchaseRequestItem")
    Rfq = apps.get_model("procurement", "Rfq")
    RfqSupplier = apps.get_model("procurement", "RfqSupplier")
    SupplierQuote = apps.get_model("procurement", "SupplierQuote")
    SupplierQuoteItem = apps.get_model("procurement", "SupplierQuoteItem")
    RfqScoringCriterion = apps.get_model("procurement", "RfqScoringCriterion")
    SupplierQuoteScore = apps.get_model("procurement", "SupplierQuoteScore")
    AwardDecision = apps.get_model("procurement", "AwardDecision")
    AwardLine = apps.get_model("procurement", "AwardLine")
    ApprovalPolicy = apps.get_model("procurement", "ApprovalPolicy")
    ApprovalCase = apps.get_model("procurement", "ApprovalCase")
    ApprovalStep = apps.get_model("procurement", "ApprovalStep")
    PurchaseOrder = apps.get_model("procurement", "PurchaseOrder")
    PurchaseOrderItem = apps.get_model("procurement", "PurchaseOrderItem")
    GoodsReceipt = apps.get_model("erp", "GoodsReceipt")
    GoodsReceiptItem = apps.get_model("erp", "GoodsReceiptItem")
    QualityInspection = apps.get_model("erp", "QualityInspection")
    InventoryMovement = apps.get_model("erp", "InventoryMovement")

    for quote in _preflight(Quote, ApprovalPolicy):
        if PurchaseRequest.objects.filter(legacy_quote_id=quote.id).exists():
            continue

        approval = quote.approvals.first()
        request = PurchaseRequest.objects.create(
            request_no=f"LEGACY-QUOTE-{quote.id}",
            requester_id=quote.user_id,
            status=REQUEST_STATUS[quote.status],
            purpose="Legacy Quote migration",
            currency=quote.currency,
            source="legacy",
            legacy_quote_id=quote.id,
            idempotency_key=f"legacy-quote-{quote.id}",
            created_at=quote.created_at,
            updated_at=quote.created_at,
        )
        request_item = PurchaseRequestItem.objects.create(
            request=request,
            line_no=1,
            product_id=quote.product_id,
            description_snapshot=quote.product.name,
            specification_snapshot=quote.product.specifications or {},
            quantity=Decimal(quote.quantity),
            unit_of_measure=quote.product.unit_of_measure,
            created_at=quote.created_at,
        )
        target_rfq_status = RFQ_STATUS[quote.status]
        rfq = Rfq.objects.create(
            rfq_no=f"LEGACY-RFQ-{quote.id}",
            request=request,
            revision=1,
            status="draft",
            rule_snapshot={
                "migration_source": "legacy_quote",
                "legacy_price_deviation_pct": (
                    str(quote.price_deviation_pct) if quote.price_deviation_pct is not None else None
                ),
                "legacy_ai_summary_text": quote.ai_summary_text,
            },
            created_at=quote.created_at,
            updated_at=quote.created_at,
        )
        criterion = RfqScoringCriterion.objects.create(
            rfq=rfq,
            code="legacy_price_snapshot",
            label="Legacy price snapshot",
            weight=Decimal("100.00"),
            calculation_method="legacy_snapshot",
            sequence=1,
            created_at=quote.created_at,
        )
        if target_rfq_status != "draft":
            rfq.status = target_rfq_status
            rfq.save(update_fields=["status"])
        invitation = RfqSupplier.objects.create(
            rfq=rfq,
            supplier_id=quote.supplier_id,
            status="responded",
            invited_at=quote.created_at,
            responded_at=quote.created_at,
            created_at=quote.created_at,
            updated_at=quote.created_at,
        )
        supplier_quote = SupplierQuote.objects.create(
            quote_no=f"LEGACY-SQ-{quote.id}",
            rfq_supplier=invitation,
            revision=1,
            status="submitted",
            currency=quote.currency,
            exchange_rate_to_twd=Decimal("1.000000"),
            items_subtotal=quote.total_amount,
            tax_amount=Decimal("0.00"),
            shipping_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            landed_total_twd=quote.total_amount,
            submitted_at=quote.created_at,
            created_at=quote.created_at,
        )
        supplier_quote_item = SupplierQuoteItem.objects.create(
            supplier_quote=supplier_quote,
            request_item=request_item,
            quantity=Decimal(quote.quantity),
            unit_price=quote.price,
            subtotal=quote.total_amount,
            specification_snapshot=quote.product.specifications or {},
            created_at=quote.created_at,
        )
        SupplierQuoteScore.objects.create(
            supplier_quote=supplier_quote,
            criterion=criterion,
            raw_value={
                "migration_source": "legacy_quote",
                "unit_price": str(quote.price),
                "price_deviation_pct": (
                    str(quote.price_deviation_pct) if quote.price_deviation_pct is not None else None
                ),
            },
            normalized_score=Decimal("100.00"),
            weighted_score=Decimal("100.00"),
            created_at=quote.created_at,
        )
        award_status = AWARD_STATUS[quote.status]
        award = AwardDecision.objects.create(
            rfq=rfq,
            revision=1,
            status="draft",
            recommended_quote=supplier_quote,
            selected_by_id=quote.user_id,
            selection_reason="Legacy Quote migration",
            submitted_at=None,
            created_at=quote.created_at,
        )
        award_line = AwardLine.objects.create(
            award=award,
            request_item=request_item,
            supplier_quote_item=supplier_quote_item,
            awarded_quantity=Decimal(quote.quantity),
            unit_price_snapshot=quote.price,
            amount_snapshot=quote.total_amount,
            reason="Legacy single-line award",
            created_at=quote.created_at,
        )
        if award_status != "draft":
            award.status = award_status
            award.submitted_at = quote.created_at
            award.save(update_fields=["status", "submitted_at"])

        if quote.status in CASE_STATUS:
            policy = _policy_for_quote(ApprovalPolicy, quote)
            missing_approval = approval is None
            decided_at = approval.updated_at if approval and approval.status in {"approved", "rejected"} else None
            case = ApprovalCase.objects.create(
                award=award,
                policy=policy,
                requester_id=quote.user_id,
                policy_snapshot={
                    "migration_source": "legacy_quote",
                    "legacy_approval_record_missing": missing_approval,
                    "legacy_quote_status": quote.status,
                    "policy_id": policy.id,
                },
                total_amount=quote.total_amount,
                currency=quote.currency,
                status=CASE_STATUS[quote.status],
                submitted_at=approval.created_at if approval else quote.created_at,
                decided_at=decided_at,
                created_at=quote.created_at,
                updated_at=decided_at or quote.created_at,
            )
            if approval is not None:
                if approval.status == "pending" and approval.approver_id is None:
                    step_status = "pending"
                    actor_fields = {}
                elif approval.status == "pending":
                    step_status = "claimed"
                    actor_fields = {
                        "claimed_by_id": approval.approver_id,
                        "claimed_at": approval.updated_at,
                    }
                else:
                    step_status = approval.status
                    actor_fields = {
                        "claimed_by_id": approval.approver_id,
                        "claimed_at": approval.created_at,
                        "decided_by_id": approval.approver_id,
                        "decided_at": approval.updated_at,
                        "decision_reason": "Legacy approval migration",
                    }
                    if approval.approver_id is None:
                        _migration_error(quote.id, "approval_actor_missing")
                ApprovalStep.objects.create(
                    approval_case=case,
                    sequence=1,
                    role_id=approval.role_id,
                    role_snapshot={
                        "migration_source": "legacy_approval",
                        "legacy_approval_level": approval.approval_level,
                    },
                    status=step_status,
                    created_at=approval.created_at,
                    updated_at=approval.updated_at,
                    **actor_fields,
                )

        if quote.status == "approved":
            purchase_order = PurchaseOrder.objects.create(
                po_no=f"LEGACY-PO-{quote.id}",
                award=award,
                supplier_id=quote.supplier_id,
                status="closed",
                currency=quote.currency,
                total_amount=quote.total_amount,
                issued_at=quote.created_at,
                closed_at=quote.created_at,
                created_at=quote.created_at,
                updated_at=quote.created_at,
            )
            purchase_order_item = PurchaseOrderItem.objects.create(
                purchase_order=purchase_order,
                award_line=award_line,
                line_no=1,
                product_id=quote.product_id,
                product_name_snapshot=quote.product.name,
                specification_snapshot=quote.product.specifications or {},
                ordered_quantity=Decimal(quote.quantity),
                unit_price=quote.price,
                amount=quote.total_amount,
                created_at=quote.created_at,
            )
            receipt = GoodsReceipt.objects.create(
                receipt_no=f"LEGACY-GR-{quote.id}",
                purchase_order=purchase_order,
                status="posted",
                received_by_id=None,
                received_at=quote.created_at,
                legacy_quote_id=quote.id,
                created_at=quote.created_at,
                updated_at=quote.created_at,
            )
            receipt_item = GoodsReceiptItem.objects.create(
                receipt=receipt,
                purchase_order_item=purchase_order_item,
                received_quantity=Decimal(quote.quantity),
                lot_no="",
                created_at=quote.created_at,
            )
            inspection = QualityInspection.objects.create(
                receipt_item=receipt_item,
                status="accepted",
                accepted_quantity=Decimal(quote.quantity),
                defective_quantity=Decimal("0.000"),
                rejected_quantity=Decimal("0.000"),
                defect_details="",
                inspected_by_id=None,
                inspected_at=quote.created_at,
                notes="Legacy migration assumed receipt; original actors unavailable",
                created_at=quote.created_at,
            )
            InventoryMovement.objects.create(
                product_id=quote.product_id,
                movement_type="migration_assumed_receipt",
                quantity_delta=Decimal(quote.quantity),
                reference_type="quality_inspection",
                reference_id=inspection.id,
                affects_balance=False,
                reason="Legacy approved Quote migration; inventory already reflected",
                posted_by_id=None,
                posted_at=quote.created_at,
                created_at=quote.created_at,
            )


REVERSE_SQL = """
ALTER TABLE inventory_movements DISABLE TRIGGER inventory_movements_immutable;
ALTER TABLE quality_inspections DISABLE TRIGGER quality_inspections_immutable;

DELETE FROM inventory_movements im
USING quality_inspections qi, goods_receipt_items gri, goods_receipts gr
WHERE im.reference_type = 'quality_inspection'
  AND im.reference_id = qi.id
  AND im.movement_type = 'migration_assumed_receipt'
  AND qi.receipt_item_id = gri.id
  AND gri.receipt_id = gr.id
  AND gr.legacy_quote_id IS NOT NULL;
DELETE FROM quality_inspections qi
USING goods_receipt_items gri, goods_receipts gr
WHERE qi.receipt_item_id = gri.id
  AND gri.receipt_id = gr.id
  AND gr.legacy_quote_id IS NOT NULL;

ALTER TABLE quality_inspections ENABLE TRIGGER quality_inspections_immutable;
ALTER TABLE inventory_movements ENABLE TRIGGER inventory_movements_immutable;

DELETE FROM goods_receipt_items gri USING goods_receipts gr
WHERE gri.receipt_id = gr.id AND gr.legacy_quote_id IS NOT NULL;
DELETE FROM goods_receipts WHERE legacy_quote_id IS NOT NULL;

DELETE FROM purchase_order_items poi USING purchase_orders po, award_decisions a, rfqs r, purchase_requests pr
WHERE poi.purchase_order_id = po.id AND po.award_id = a.id AND a.rfq_id = r.id
  AND r.request_id = pr.id AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM purchase_orders po USING award_decisions a, rfqs r, purchase_requests pr
WHERE po.award_id = a.id AND a.rfq_id = r.id AND r.request_id = pr.id
  AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM approval_steps ast USING approval_cases ac, award_decisions a, rfqs r, purchase_requests pr
WHERE ast.approval_case_id = ac.id AND ac.award_id = a.id AND a.rfq_id = r.id
  AND r.request_id = pr.id AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM approval_cases ac USING award_decisions a, rfqs r, purchase_requests pr
WHERE ac.award_id = a.id AND a.rfq_id = r.id AND r.request_id = pr.id
  AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM award_lines al USING award_decisions a, rfqs r, purchase_requests pr
WHERE al.award_id = a.id AND a.rfq_id = r.id AND r.request_id = pr.id
  AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM award_decisions a USING rfqs r, purchase_requests pr
WHERE a.rfq_id = r.id AND r.request_id = pr.id AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM supplier_quote_items sqi USING supplier_quotes sq, rfq_suppliers rs, rfqs r, purchase_requests pr
WHERE sqi.supplier_quote_id = sq.id AND sq.rfq_supplier_id = rs.id AND rs.rfq_id = r.id
  AND r.request_id = pr.id AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM supplier_quote_scores sqs USING supplier_quotes sq, rfq_suppliers rs, rfqs r, purchase_requests pr
WHERE sqs.supplier_quote_id = sq.id AND sq.rfq_supplier_id = rs.id AND rs.rfq_id = r.id
  AND r.request_id = pr.id AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM supplier_quotes sq USING rfq_suppliers rs, rfqs r, purchase_requests pr
WHERE sq.rfq_supplier_id = rs.id AND rs.rfq_id = r.id AND r.request_id = pr.id
  AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM rfq_suppliers rs USING rfqs r, purchase_requests pr
WHERE rs.rfq_id = r.id AND r.request_id = pr.id AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM rfq_scoring_criteria rsc USING rfqs r, purchase_requests pr
WHERE rsc.rfq_id = r.id AND r.request_id = pr.id AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM rfqs r USING purchase_requests pr
WHERE r.request_id = pr.id AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM purchase_request_items pri USING purchase_requests pr
WHERE pri.request_id = pr.id AND pr.legacy_quote_id IS NOT NULL;
DELETE FROM purchase_requests WHERE legacy_quote_id IS NOT NULL;
"""


def backwards(apps, schema_editor):
    schema_editor.execute(REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("erp", "0004_legacy_receipt_actor_exception"),
        ("procurement", "0008_concurrent_indexes"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
