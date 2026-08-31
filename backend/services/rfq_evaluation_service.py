"""Phase 4.1.5 C4：逐項比較、整體彙總的固定公式評分。"""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from apps.procurement.models import (
    PurchaseRequest,
    QuoteRequirementResult,
    Rfq,
    SupplierQuote,
    SupplierQuoteScore,
)
from repositories.procurement import RfqRepository
from services.rbac_service import user_has_permission
from services.rfq_quote_service import (
    RfqQuoteConflict,
    RfqQuoteError,
    RfqQuoteNotFound,
    RfqQuotePermissionDenied,
)

SCORE_QUANTUM = Decimal("0.01")
HUNDRED = Decimal("100.00")


def _score(value):
    return value.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


def _display(value):
    return f"{_score(value):.2f}"


def _inverse_minimum(value, minimum):
    if value == 0:
        return HUNDRED if minimum == 0 else Decimal("0.00")
    return _score(minimum / value * HUNDRED)


def allocated_item_unit_cost_twd(quote, item):
    adjustment = quote.tax_amount + quote.shipping_amount - quote.discount_amount
    if quote.items_subtotal:
        allocated = adjustment * item.subtotal / quote.items_subtotal
    else:
        item_count = quote.items.count()
        allocated = adjustment / item_count if item_count else Decimal("0.00")
    total_twd = (item.subtotal + allocated) * quote.exchange_rate_to_twd
    return _score(total_twd / item.quantity)


def _requirement_state(item, requirements):
    results = {result.requirement_id: result for result in item.requirement_results.all()}
    mandatory_failure = False
    passed = 0
    total = len(requirements)
    details = []
    for requirement in requirements:
        result = results.get(requirement.id)
        state = result.result if result else QuoteRequirementResult.Result.NOT_PROVIDED
        if requirement.is_mandatory and state in (
            QuoteRequirementResult.Result.FAIL,
            QuoteRequirementResult.Result.NOT_PROVIDED,
        ):
            mandatory_failure = True
        if state == QuoteRequirementResult.Result.PASS:
            passed += 1
        details.append({"code": requirement.code, "label": requirement.label, "result": state})
    quality_score = _score(Decimal(passed) / Decimal(total) * HUNDRED) if total else None
    return mandatory_failure, quality_score, details


def _unavailable_scores(criteria):
    return {
        criterion.code: {
            "label": criterion.label,
            "weight": _display(criterion.weight),
            "status": "unavailable",
            "message": "尚無可驗證的正式資料",
        }
        for criterion in criteria
    }


def _available_score(criterion, normalized, raw_value):
    weighted = _score(normalized * criterion.weight / HUNDRED)
    return {
        "label": criterion.label,
        "weight": _display(criterion.weight),
        "status": "available",
        "normalized_score": _display(normalized),
        "weighted_score": _display(weighted),
        "raw_value": raw_value,
    }


def _aggregate_available(item_rows, criteria):
    scores = _unavailable_scores(criteria)
    for criterion in criteria:
        available = [
            row["scores"][criterion.code]
            for row in item_rows
            if row["scores"][criterion.code]["status"] == "available"
        ]
        if not available:
            continue
        normalized = _score(
            sum((Decimal(row["normalized_score"]) for row in available), Decimal(0))
            / Decimal(len(available))
        )
        scores[criterion.code] = _available_score(
            criterion,
            normalized,
            {"item_scores": [row["normalized_score"] for row in available]},
        )
    return scores


def _totals(scores):
    available = [row for row in scores.values() if row["status"] == "available"]
    available_weight = sum((Decimal(row["weight"]) for row in available), Decimal(0))
    weighted_sum = sum((Decimal(row["weighted_score"]) for row in available), Decimal(0))
    normalized_total = weighted_sum / available_weight * HUNDRED if available_weight else Decimal(0)
    return _score(normalized_total), _score(available_weight)


def _persist_scores(quote, criteria_by_code, scores):
    quote.scores.all().delete()
    SupplierQuoteScore.objects.bulk_create([
        SupplierQuoteScore(
            supplier_quote=quote,
            criterion=criteria_by_code[code],
            raw_value=row["raw_value"],
            normalized_score=Decimal(row["normalized_score"]),
            weighted_score=Decimal(row["weighted_score"]),
        )
        for code, row in scores.items()
        if row["status"] == "available"
    ])


@transaction.atomic
def evaluate_rfq(user, rfq_id, *, enforce_permission=True):
    if enforce_permission and not user_has_permission(user, "rfq.manage"):
        raise RfqQuotePermissionDenied("沒有執行此操作的權限")
    try:
        rfq = RfqRepository.evaluation_context_for_update(rfq_id)
    except ObjectDoesNotExist as exc:
        raise RfqQuoteNotFound("找不到指定的 RFQ") from exc
    if rfq.status not in (Rfq.Status.ISSUED, Rfq.Status.COLLECTING, Rfq.Status.EVALUATING):
        raise RfqQuoteConflict("只有已發出或收件中的 RFQ 可以進行評選")

    criteria = list(rfq.scoring_criteria.all().order_by("sequence"))
    if not criteria or sum((row.weight for row in criteria), Decimal(0)) != HUNDRED:
        raise RfqQuoteError("RFQ 評分權重快照不完整")
    criteria_by_code = {row.code: row for row in criteria}
    required_codes = {"landed_cost", "spec_quality", "delivery"}
    if not required_codes.issubset(criteria_by_code):
        raise RfqQuoteError("RFQ 缺少必要的評分準則")

    now = timezone.now()
    quotes = []
    for invitation in rfq.invited_suppliers.all():
        for quote in invitation.quotes.all():
            if quote.status not in (
                SupplierQuote.Status.SUBMITTED,
                SupplierQuote.Status.ACCEPTED_FOR_EVALUATION,
            ):
                continue
            if quote.valid_until and quote.valid_until <= now:
                quote.status = SupplierQuote.Status.EXPIRED
                quote.save(update_fields=["status"])
                quote.scores.all().delete()
                continue
            quotes.append(quote)
    if not quotes:
        raise RfqQuoteConflict("沒有可納入評選的有效報價")

    request_items = list(rfq.request.items.all().order_by("line_no"))
    requirements_by_item = {item.id: list(item.requirements.all()) for item in request_items}
    quote_items_by_request = defaultdict(list)
    for quote in quotes:
        for item in quote.items.all():
            quote_items_by_request[item.request_item_id].append((quote, item))

    item_sections = []
    quote_item_rows = defaultdict(list)
    recommendations = []
    for request_item in request_items:
        candidates = quote_items_by_request[request_item.id]
        costs = {item.id: allocated_item_unit_cost_twd(quote, item) for quote, item in candidates}
        leads = {item.id: Decimal(item.lead_time_days) for _, item in candidates if item.lead_time_days is not None}
        minimum_cost = min(costs.values()) if costs else None
        minimum_lead = min(leads.values()) if leads else None
        rows = []
        for quote, item in candidates:
            scores = _unavailable_scores(criteria)
            cost_normalized = _inverse_minimum(costs[item.id], minimum_cost)
            scores["landed_cost"] = _available_score(
                criteria_by_code["landed_cost"],
                cost_normalized,
                {"allocated_unit_cost_twd": _display(costs[item.id]), "lowest_unit_cost_twd": _display(minimum_cost)},
            )
            if item.id in leads:
                delivery_normalized = _inverse_minimum(leads[item.id], minimum_lead)
                scores["delivery"] = _available_score(
                    criteria_by_code["delivery"],
                    delivery_normalized,
                    {"lead_time_days": int(leads[item.id]), "fastest_days": int(minimum_lead)},
                )
            mandatory_failure, quality_normalized, requirement_details = _requirement_state(
                item, requirements_by_item[request_item.id]
            )
            if quality_normalized is not None:
                scores["spec_quality"] = _available_score(
                    criteria_by_code["spec_quality"], quality_normalized, {"requirements": requirement_details}
                )
            total_score, completeness = _totals(scores)
            row = {
                "quote_id": quote.id,
                "quote_item_id": item.id,
                "supplier_id": quote.rfq_supplier.supplier_id,
                "supplier_name": quote.rfq_supplier.supplier.name,
                "quoted_quantity": f"{item.quantity:.3f}",
                "unit_price": f"{item.unit_price:.2f}",
                "currency": quote.currency,
                "allocated_unit_cost_twd": _display(costs[item.id]),
                "eligible": not mandatory_failure,
                "eligibility_reason": "必要條件未通過" if mandatory_failure else "符合推薦資格",
                "scores": scores,
                "total_score": _display(total_score),
                "data_completeness_pct": _display(completeness),
            }
            rows.append(row)
            quote_item_rows[quote.id].append(row)
        eligible_rows = [row for row in rows if row["eligible"]]
        best = max((Decimal(row["total_score"]) for row in eligible_rows), default=None)
        recommended_names = [
            row["supplier_name"] for row in eligible_rows if Decimal(row["total_score"]) == best
        ] if best is not None else []
        item_sections.append({
            "request_item_id": request_item.id,
            "line_no": request_item.line_no,
            "description": request_item.description_snapshot,
            "requested_quantity": f"{request_item.quantity:.3f}",
            "unit_of_measure": request_item.unit_of_measure,
            "quotes": rows,
            "recommended_supplier_names": recommended_names,
            "recommended_quote_ids": [
                row["quote_id"] for row in eligible_rows if Decimal(row["total_score"]) == best
            ] if best is not None else [],
        })
        recommendations.append({
            "request_item_id": request_item.id,
            "description": request_item.description_snapshot,
            "supplier_names": recommended_names,
            "tie": len(recommended_names) > 1,
        })

    quote_summaries = []
    for quote in quotes:
        rows = quote_item_rows[quote.id]
        scores = _aggregate_available(rows, criteria)
        total_score, completeness = _totals(scores)
        covers_all = len(rows) == len(request_items)
        eligible = covers_all and all(row["eligible"] for row in rows)
        _persist_scores(quote, criteria_by_code, scores)
        if quote.status != SupplierQuote.Status.ACCEPTED_FOR_EVALUATION:
            quote.status = SupplierQuote.Status.ACCEPTED_FOR_EVALUATION
            quote.save(update_fields=["status"])
        quote_summaries.append({
            "quote_id": quote.id,
            "supplier_id": quote.rfq_supplier.supplier_id,
            "supplier_name": quote.rfq_supplier.supplier.name,
            "covers_all_items": covers_all,
            "eligible_for_whole_request": eligible,
            "whole_request_recommended": False,
            "scores": scores,
            "total_score": _display(total_score),
            "data_completeness_pct": _display(completeness),
        })

    eligible_summaries = [row for row in quote_summaries if row["eligible_for_whole_request"]]
    best_total = max((Decimal(row["total_score"]) for row in eligible_summaries), default=None)
    for row in eligible_summaries:
        row["whole_request_recommended"] = Decimal(row["total_score"]) == best_total

    rfq.status = Rfq.Status.EVALUATING
    rfq.save(update_fields=["status"])
    if rfq.request.status == PurchaseRequest.Status.SOURCING:
        rfq.request.status = PurchaseRequest.Status.AWARDING
        rfq.request.version += 1
        rfq.request.save(update_fields=["status", "version"])

    return {
        "rfq_id": rfq.id,
        "rfq_no": rfq.rfq_no,
        "status": rfq.status,
        "comparison_basis": "同一需求品項逐項比較，再彙總整張報價",
        "items": item_sections,
        "quote_summaries": quote_summaries,
        "recommendations": recommendations,
    }
