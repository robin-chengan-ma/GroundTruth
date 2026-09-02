"""採購稽核與流程健康總覽統計聚合。

資料來源與已知限制（2026-09-02 與 Robin 確認，見 docs/ADR/discuss/audit-dashboard.md）：
- FR-1 AI 候選採用／修正：來源 candidate_confirmed 稽核事件，只保存修正欄位類別。
- FR-2 主檔媒合健康度：來源 candidate_parsed 聚合事件，只保存命中／未命中數量。
- FR-3 複核佇列處理狀況：來源 manual_review_queue，涵蓋全部 review_type。
- FR-4 價格異常案件比例與清單：來源正式（非 draft）SupplierQuoteItem，比對
  PurchaseRequestRepository.historical_average_price，門檻沿用 FR-4a 既有 20%。
"""
import json
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Q, Sum

from apps.audit.models import AuditLog, ManualReviewQueue
from apps.erp.models import QualityInspection
from apps.procurement.models import SupplierQuote, SupplierQuoteItem
from repositories.procurement import PurchaseRequestRepository

PRICE_ANOMALY_THRESHOLD_PCT = Decimal("20.00")  # 沿用 FR-4a 既有門檻

_FORMAL_QUOTE_STATUSES = [
    SupplierQuote.Status.SUBMITTED,
    SupplierQuote.Status.ACCEPTED_FOR_EVALUATION,
    SupplierQuote.Status.REVISED,
]


def _parse_date(value):
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _period_filter(date_from, date_to, field="created_at"):
    filters = Q()
    if date_from:
        filters &= Q(**{f"{field}__date__gte": date_from})
    if date_to:
        filters &= Q(**{f"{field}__date__lte": date_to})
    return filters


def _candidate_quality_stats(date_from, date_to):
    logs = AuditLog.objects.filter(
        action_type="candidate_confirmed",
        verification_result__in=["pass", "fail"],
    ).filter(_period_filter(date_from, date_to))
    counts = logs.values("verification_result").annotate(total=Count("id"))
    by_result = {row["verification_result"]: row["total"] for row in counts}
    direct = by_result.get("pass", 0)
    corrected = by_result.get("fail", 0)
    total = direct + corrected
    by_field = {}
    for raw in logs.filter(verification_result="fail").values_list("masked_payload", flat=True):
        try:
            fields = json.loads(raw or "{}").get("changed_fields", [])
        except (json.JSONDecodeError, AttributeError):
            fields = []
        for field in fields:
            by_field[field] = by_field.get(field, 0) + 1
    return {
        "direct_adoption_count": direct,
        "corrected_count": corrected,
        "direct_adoption_rate_pct": f"{(Decimal(direct) / Decimal(total) * 100):.2f}" if total else None,
        "corrections_by_field": by_field,
    }


def _supplier_match_stats(date_from, date_to):
    parse_logs = AuditLog.objects.filter(action_type="candidate_parsed").filter(
        _period_filter(date_from, date_to)
    )
    aggregate = {
        "supplier_matched_count": 0, "supplier_unmatched_count": 0,
        "product_matched_count": 0, "product_unmatched_count": 0,
    }
    for raw in parse_logs.values_list("masked_payload", flat=True):
        try:
            values = json.loads(raw or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        for key in aggregate:
            aggregate[key] += int(values.get(key, 0) or 0)
    entries = ManualReviewQueue.objects.filter(
        review_type=ManualReviewQueue.ReviewType.SUPPLIER_FUZZY_MATCH,
    ).filter(_period_filter(date_from, date_to))
    total = entries.count()
    approved = entries.filter(decision=ManualReviewQueue.Decision.APPROVED).count()
    rejected = entries.filter(decision=ManualReviewQueue.Decision.REJECTED).count()
    pending = total - approved - rejected
    return {
        **aggregate,
        "fuzzy_match_total": total,
        "fuzzy_match_approved": approved,
        "fuzzy_match_rejected": rejected,
        "fuzzy_match_pending": pending,
    }


def _manual_review_queue_stats(date_from, date_to):
    entries = ManualReviewQueue.objects.filter(_period_filter(date_from, date_to))
    pending_count = entries.exclude(status=ManualReviewQueue.Status.RESOLVED).count()
    processed = entries.filter(status=ManualReviewQueue.Status.RESOLVED)
    processed_count = processed.count()
    approved = processed.filter(decision=ManualReviewQueue.Decision.APPROVED).count()
    rejected = processed.filter(decision=ManualReviewQueue.Decision.REJECTED).count()
    return {
        "pending_count": pending_count,
        "processed_count": processed_count,
        "by_decision": {"approved": approved, "rejected": rejected},
    }


def _quality_stats(date_from, date_to):
    inspections = QualityInspection.objects.filter(
        _period_filter(date_from, date_to, field="inspected_at")
    )
    totals = inspections.aggregate(
        accepted=Sum("accepted_quantity"),
        defective=Sum("defective_quantity"),
        rejected=Sum("rejected_quantity"),
    )
    accepted = totals["accepted"] or 0
    exception = (totals["defective"] or 0) + (totals["rejected"] or 0)
    total = accepted + exception
    return {
        "inspection_count": inspections.count(),
        "accepted_quantity": f"{accepted:.3f}",
        "exception_quantity": f"{exception:.3f}",
        "acceptance_rate_pct": f"{(accepted / total * 100):.2f}" if total else None,
    }


def _price_anomaly_stats(date_from, date_to):
    items = (
        SupplierQuoteItem.objects.filter(supplier_quote__status__in=_FORMAL_QUOTE_STATUSES)
        .filter(_period_filter(date_from, date_to, field="created_at"))
        .select_related(
            "supplier_quote__rfq_supplier__supplier",
            "supplier_quote__rfq_supplier__rfq",
            "request_item__product",
        )
    )
    checked_count = 0
    anomalies = []
    for item in items:
        product = item.request_item.product
        if product is None:
            continue
        supplier = item.supplier_quote.rfq_supplier.supplier
        currency = item.supplier_quote.currency
        historical_average = PurchaseRequestRepository.historical_average_price(
            supplier_id=supplier.id, product_id=product.id, currency=currency,
        )
        if historical_average in (None, 0):
            continue
        checked_count += 1
        try:
            deviation = (item.unit_price - historical_average) / historical_average * 100
        except InvalidOperation:
            continue
        if abs(deviation) <= PRICE_ANOMALY_THRESHOLD_PCT:
            continue
        anomalies.append({
            "supplier_quote_item_id": item.id,
            "rfq_no": item.supplier_quote.rfq_supplier.rfq.rfq_no,
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "product_id": product.id,
            "product_name": product.name,
            "unit_price": f"{item.unit_price:.2f}",
            "historical_average": f"{historical_average:.2f}",
            "deviation_pct": f"{deviation:.2f}",
            "currency": currency,
        })
    anomaly_count = len(anomalies)
    anomaly_rate_pct = (
        f"{(Decimal(anomaly_count) / Decimal(checked_count) * 100):.2f}" if checked_count else None
    )
    return {
        "threshold_pct": f"{PRICE_ANOMALY_THRESHOLD_PCT:.2f}",
        "checked_count": checked_count,
        "anomaly_count": anomaly_count,
        "anomaly_rate_pct": anomaly_rate_pct,
        "items": anomalies,
    }


def compute_dashboard_stats(*, date_from=None, date_to=None):
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)
    return {
        "period": {"from": date_from or None, "to": date_to or None},
        "candidate_quality": _candidate_quality_stats(parsed_from, parsed_to),
        "supplier_match": _supplier_match_stats(parsed_from, parsed_to),
        "manual_review_queue": _manual_review_queue_stats(parsed_from, parsed_to),
        "price_anomaly": _price_anomaly_stats(parsed_from, parsed_to),
        "quality": _quality_stats(parsed_from, parsed_to),
    }
