"""Phase 6：稽核與正確率總覽統計聚合 API（SPEC「稽核與正確率總覽」FR-1～5）。

僅 admin（audit.read）可存取。資料來源如 FR-5：
- 幻覺驗證／供應商比對／複核佇列統計來源為 audit_logs／manual_review_queue。
  - 新版 inquiries/parse 已改為 Django 固定邏輯直接驗證，不再產生需比對的 AI 生成敘述文字，
    故幻覺驗證卡片僅反映 Phase 5 切換前的歷史 audit_logs 資料（2026-09-02 與 Robin 確認，
    見 docs/ADR/discuss/audit-dashboard.md）。
  - masking_service 只在模糊比對案件寫入 manual_review_queue；精確比對／查無供應商未持久化，
    供應商比對卡片只能呈現模糊比對數量與處理結果。
- 價格異常統計來源為正式（非 draft）SupplierQuoteItem，比對 PurchaseRequestRepository
  .historical_average_price，門檻沿用 FR-4a 既有 20%。
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog, ManualReviewQueue
from apps.erp.models import QualityInspection
from apps.procurement.models import (
    AwardLine,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    Rfq,
    RfqScoringCriterion,
    RfqSupplier,
    SupplierQuote,
    SupplierQuoteItem,
)
from services.rfq_quote_service import DEFAULT_CRITERIA
from tests.test_phase4_1_award_approval_po import create_award_context


@pytest.mark.django_db
def test_dashboard_requires_audit_read(api_client, user, role_employee):
    api_client.force_authenticate(user=user)
    resp = api_client.get("/api/v1/audit-dashboard/stats/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_dashboard_candidate_adoption_rate_from_current_flow_events(admin_api_client):
    AuditLog.objects.create(action_type="candidate_confirmed", verification_result="pass")
    AuditLog.objects.create(action_type="candidate_confirmed", verification_result="pass")
    AuditLog.objects.create(action_type="candidate_confirmed", verification_result="fail")

    resp = admin_api_client.get("/api/v1/audit-dashboard/stats/")

    assert resp.status_code == 200
    candidate = resp.data["candidate_quality"]
    assert candidate["direct_adoption_count"] == 2
    assert candidate["corrected_count"] == 1
    assert candidate["direct_adoption_rate_pct"] == "66.67"
    assert "hallucination_check" not in resp.data


@pytest.mark.django_db
def test_dashboard_candidate_adoption_rate_null_without_data(admin_api_client):
    resp = admin_api_client.get("/api/v1/audit-dashboard/stats/")
    assert resp.data["candidate_quality"]["direct_adoption_rate_pct"] is None


@pytest.mark.django_db
def test_dashboard_supplier_fuzzy_match_breakdown(admin_api_client, admin_user):
    ManualReviewQueue.objects.create(
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        status=ManualReviewQueue.Status.RESOLVED,
        decision=ManualReviewQueue.Decision.APPROVED,
        user=admin_user,
    )
    ManualReviewQueue.objects.create(
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        status=ManualReviewQueue.Status.RESOLVED,
        decision=ManualReviewQueue.Decision.REJECTED,
        user=admin_user,
    )
    ManualReviewQueue.objects.create(
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
        status=ManualReviewQueue.Status.UNCLAIMED,
    )

    resp = admin_api_client.get("/api/v1/audit-dashboard/stats/")

    supplier_match = resp.data["supplier_match"]
    assert supplier_match["fuzzy_match_total"] == 3
    assert supplier_match["fuzzy_match_approved"] == 1
    assert supplier_match["fuzzy_match_rejected"] == 1
    assert supplier_match["fuzzy_match_pending"] == 1


@pytest.mark.django_db
def test_dashboard_manual_review_queue_status(admin_api_client, admin_user):
    ManualReviewQueue.objects.create(
        review_type=ManualReviewQueue.ReviewType.HALLUCINATION_MISMATCH,
        status=ManualReviewQueue.Status.CLAIMED,
        user=admin_user,
    )
    ManualReviewQueue.objects.create(
        review_type=ManualReviewQueue.ReviewType.HALLUCINATION_MISMATCH,
        status=ManualReviewQueue.Status.RESOLVED,
        decision=ManualReviewQueue.Decision.APPROVED,
        user=admin_user,
    )

    resp = admin_api_client.get("/api/v1/audit-dashboard/stats/")

    queue = resp.data["manual_review_queue"]
    assert queue["pending_count"] == 1
    assert queue["processed_count"] == 1
    assert queue["by_decision"]["approved"] == 1
    assert queue["by_decision"]["rejected"] == 0


@pytest.mark.django_db
def test_dashboard_quality_acceptance_uses_final_inspection_quantities(
    admin_api_client, user, supplier, product,
):
    _request, request_item, quote_item, award = create_award_context(user, supplier, product)
    award_line = AwardLine.objects.create(
        award=award, request_item=request_item, supplier_quote_item=quote_item,
        awarded_quantity=Decimal("10.000"), unit_price_snapshot=Decimal("100.00"),
        amount_snapshot=Decimal("1000.00"),
    )
    po = PurchaseOrder.objects.create(
        po_no="PO-DASH-QA", award=award, supplier=supplier,
        status=PurchaseOrder.Status.RECEIVED, currency="TWD", total_amount=Decimal("1000.00"),
    )
    po_item = PurchaseOrderItem.objects.create(
        purchase_order=po, award_line=award_line, line_no=1, product=product,
        product_name_snapshot=product.name, ordered_quantity=Decimal("10.000"),
        unit_price=Decimal("100.00"), amount=Decimal("1000.00"),
    )
    from apps.erp.models import GoodsReceipt, GoodsReceiptItem

    receipt = GoodsReceipt.objects.create(
        receipt_no="GR-DASH-QA", purchase_order=po, status="posted", received_by=user,
        received_at=timezone.now(),
    )
    receipt_item = GoodsReceiptItem.objects.create(
        receipt=receipt, purchase_order_item=po_item, received_quantity=Decimal("10.000"),
    )
    QualityInspection.objects.create(
        receipt_item=receipt_item, status="partially_accepted", inspected_by=user,
        inspected_at=timezone.now(), accepted_quantity=Decimal("8.000"),
        defective_quantity=Decimal("1.000"), rejected_quantity=Decimal("1.000"),
        defect_details="測試瑕疵",
    )

    resp = admin_api_client.get("/api/v1/audit-dashboard/stats/")

    assert resp.data["quality"]["accepted_quantity"] == "8.000"
    assert resp.data["quality"]["exception_quantity"] == "2.000"
    assert resp.data["quality"]["acceptance_rate_pct"] == "80.00"


@pytest.mark.django_db
def test_dashboard_price_anomaly_from_formal_supplier_quote_items(admin_api_client, user, supplier, product):
    _request, request_item, quote_item, award = create_award_context(user, supplier, product)

    # 建立一筆已核准歷史採購單，形成歷史均價基準（100.00）。
    award_line = AwardLine.objects.create(
        award=award, request_item=request_item, supplier_quote_item=quote_item,
        awarded_quantity=Decimal("5.000"), unit_price_snapshot=Decimal("100.00"),
        amount_snapshot=Decimal("500.00"),
    )
    po = PurchaseOrder.objects.create(
        po_no="PO-DASH-001", award=award, supplier=supplier,
        status=PurchaseOrder.Status.RECEIVED, currency="TWD", total_amount=Decimal("500.00"),
    )
    PurchaseOrderItem.objects.create(
        purchase_order=po, award_line=award_line, line_no=1, product=product,
        product_name_snapshot=product.name, ordered_quantity=Decimal("5.000"),
        unit_price=Decimal("100.00"), amount=Decimal("500.00"),
    )

    # 另一張正式（submitted）報價，單價偏離歷史均價超過 20% 門檻；用獨立需求避免撞上
    # create_award_context 已建立、狀態仍是 active 的第一張 RFQ（同需求只能有一張 active RFQ）。
    request2 = PurchaseRequest.objects.create(request_no="PR-DASH-001", requester=user, purpose="B3 價格異常測試")
    request_item2 = PurchaseRequestItem.objects.create(
        request=request2, line_no=1, product=product, description_snapshot=product.name,
        quantity=Decimal("1.000"), unit_of_measure="EA",
    )
    # 先以 draft 建立 RFQ、補齊評選權重快照，再更新為 issued，避免與正式 issue_rfq 流程
    # 相同的「權重總和須為 100」trigger 在 rfqs INSERT 當下（尚無 criteria）就擋下來。
    rfq2 = Rfq.objects.create(
        request=request2, rfq_no="RFQ-DASH-001",
        response_due_at=timezone.now() + timezone.timedelta(days=30),
    )
    RfqScoringCriterion.objects.bulk_create([
        RfqScoringCriterion(
            rfq=rfq2, code=code, label=label, weight=Decimal(weight),
            calculation_method=method, sequence=sequence,
        )
        for sequence, (code, label, weight, method) in enumerate(DEFAULT_CRITERIA, start=1)
    ])
    rfq2.status = Rfq.Status.ISSUED
    rfq2.save(update_fields=["status"])
    rfq_supplier2 = RfqSupplier.objects.create(
        rfq=rfq2, supplier=supplier, status=RfqSupplier.Status.RESPONDED, invited_at=timezone.now(),
    )
    quote2 = SupplierQuote.objects.create(
        quote_no="SQ-DASH-001", rfq_supplier=rfq_supplier2, status=SupplierQuote.Status.SUBMITTED,
        currency="TWD", exchange_rate_to_twd=Decimal("1.000000"),
        items_subtotal=Decimal("150.00"), landed_total_twd=Decimal("150.00"), submitted_at=timezone.now(),
    )
    SupplierQuoteItem.objects.create(
        supplier_quote=quote2, request_item=request_item2, quantity=Decimal("1.000"),
        unit_price=Decimal("150.00"), subtotal=Decimal("150.00"),
    )

    resp = admin_api_client.get("/api/v1/audit-dashboard/stats/")

    anomaly = resp.data["price_anomaly"]
    assert anomaly["checked_count"] >= 1
    assert anomaly["anomaly_count"] >= 1
    quote2_item_id = SupplierQuoteItem.objects.get(supplier_quote=quote2).id
    matching = [row for row in anomaly["items"] if row["supplier_quote_item_id"] == quote2_item_id]
    assert len(matching) == 1
    assert matching[0]["deviation_pct"] == "50.00"


@pytest.mark.django_db
def test_dashboard_period_filter_applies_to_current_candidate_events(admin_api_client):
    old = AuditLog.objects.create(action_type="candidate_confirmed", verification_result="pass")
    AuditLog.objects.filter(pk=old.pk).update(created_at="2020-01-01T00:00:00+08:00")
    AuditLog.objects.create(action_type="candidate_confirmed", verification_result="fail")

    resp = admin_api_client.get("/api/v1/audit-dashboard/stats/", {"date_from": "2026-01-01"})

    assert resp.data["candidate_quality"]["direct_adoption_count"] == 0
    assert resp.data["candidate_quality"]["corrected_count"] == 1
