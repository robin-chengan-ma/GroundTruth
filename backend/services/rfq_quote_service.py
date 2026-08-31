"""Phase 4.1.5 C3：正式 RFQ、版本化報價與必要條件判定。"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import uuid4

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.procurement.models import (
    PurchaseRequest,
    QuoteRequirementResult,
    Rfq,
    RfqScoringCriterion,
    RfqSupplier,
    SupplierQuote,
    SupplierQuoteItem,
)
from repositories.procurement import RfqRepository, SupplierQuoteRepository
from services.rbac_service import user_has_permission

DEFAULT_CRITERIA = (
    ("landed_cost", "實際總成本", "30.00", "inverse_min"),
    ("spec_quality", "規格與品質", "30.00", "requirement_and_quality_history"),
    ("delivery", "交期", "15.00", "inverse_min"),
    ("payment_terms", "付款條件", "10.00", "structured_terms"),
    ("supplier_performance", "供應商表現", "10.00", "historical_performance"),
    ("sustainability_risk", "永續與風險", "5.00", "assessment_snapshot"),
)


class RfqQuoteError(Exception):
    code = "invalid_request"


class RfqQuotePermissionDenied(RfqQuoteError):
    code = "permission_denied"


class RfqQuoteNotFound(RfqQuoteError):
    code = "not_found"


class RfqQuoteConflict(RfqQuoteError):
    code = "conflict"


class QuoteExpired(RfqQuoteConflict):
    code = "quote_expired"


def _require_permission(user, code):
    if not user_has_permission(user, code):
        raise RfqQuotePermissionDenied("沒有執行此操作的權限")


def _datetime(value, field_name, *, required=False):
    if value in (None, ""):
        if required:
            raise RfqQuoteError(f"{field_name} 為必填")
        return None
    parsed = value if hasattr(value, "tzinfo") else parse_datetime(str(value))
    if parsed is None:
        raise RfqQuoteError(f"{field_name} 必須是 ISO 8601 日期時間")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _decimal(value, field_name, *, places, positive=False, default=None):
    if value in (None, ""):
        if default is not None:
            return Decimal(default)
        raise RfqQuoteError(f"{field_name} 為必填")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RfqQuoteError(f"{field_name} 必須是有效數字") from exc
    if not result.is_finite() or (result <= 0 if positive else result < 0):
        qualifier = "大於 0" if positive else "大於或等於 0"
        raise RfqQuoteError(f"{field_name} 必須{qualifier}")
    if result.as_tuple().exponent < -places:
        raise RfqQuoteError(f"{field_name} 最多只能有 {places} 位小數")
    return result


@transaction.atomic
def issue_rfq(user, rfq_id, payload):
    _require_permission(user, "rfq.manage")
    try:
        rfq = RfqRepository.get_for_update(rfq_id)
    except ObjectDoesNotExist as exc:
        raise RfqQuoteNotFound("找不到指定的 RFQ") from exc
    if rfq.status != Rfq.Status.DRAFT or rfq.request.status != PurchaseRequest.Status.SUBMITTED:
        raise RfqQuoteConflict("只有已提交需求所屬的 RFQ 草稿可以正式發出")
    if payload.get("version") != rfq.version:
        raise RfqQuoteConflict("RFQ 已被更新，請重新載入最新版本")
    due_at = _datetime(payload.get("response_due_at"), "response_due_at", required=True)
    if due_at <= timezone.now():
        raise RfqQuoteError("response_due_at 必須晚於目前時間")
    if not rfq.invited_suppliers.exists() or not rfq.request.items.exists():
        raise RfqQuoteError("RFQ 必須包含需求明細與至少一間受邀供應商")
    if not rfq.scoring_criteria.exists():
        RfqScoringCriterion.objects.bulk_create([
            RfqScoringCriterion(
                rfq=rfq,
                code=code,
                label=label,
                weight=Decimal(weight),
                calculation_method=method,
                sequence=sequence,
            )
            for sequence, (code, label, weight, method) in enumerate(DEFAULT_CRITERIA, start=1)
        ])
    rfq.rule_snapshot = {
        "version": 1,
        "criteria": [
            {"code": code, "label": label, "weight": weight, "calculation_method": method}
            for code, label, weight, method in DEFAULT_CRITERIA
        ],
    }
    rfq.response_due_at = due_at
    rfq.status = Rfq.Status.ISSUED
    rfq.version += 1
    rfq.save(update_fields=["rule_snapshot", "response_due_at", "status", "version"])
    rfq.request.status = PurchaseRequest.Status.SOURCING
    rfq.request.version += 1
    rfq.request.save(update_fields=["status", "version"])
    rfq._prefetched_objects_cache = {}
    return rfq


def _normalize_items(payload_items, request):
    if not isinstance(payload_items, list) or not payload_items:
        raise RfqQuoteError("items 必須是非空陣列")
    request_items = request.items.in_bulk()
    normalized = []
    seen = set()
    for index, row in enumerate(payload_items):
        if not isinstance(row, dict):
            raise RfqQuoteError(f"items.{index} 必須是 object")
        item_id = row.get("request_item_id")
        if not isinstance(item_id, int) or isinstance(item_id, bool):
            raise RfqQuoteError(f"items.{index}.request_item_id 必須是整數")
        if item_id not in request_items or item_id in seen:
            raise RfqQuoteError("報價明細必須對應此 RFQ 的需求品項且不可重複")
        seen.add(item_id)
        quantity = _decimal(row.get("quantity"), f"items.{index}.quantity", places=3, positive=True)
        if quantity > request_items[item_id].quantity:
            raise RfqQuoteError("報價數量不可超過需求數量")
        unit_price = _decimal(row.get("unit_price"), f"items.{index}.unit_price", places=2)
        specifications = row.get("specifications", {})
        if not isinstance(specifications, dict):
            raise RfqQuoteError(f"items.{index}.specifications 必須是 JSON object")
        lead_time_days = row.get("lead_time_days")
        warranty_months = row.get("warranty_months")
        for field_name, value in (("lead_time_days", lead_time_days), ("warranty_months", warranty_months)):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise RfqQuoteError(f"items.{index}.{field_name} 必須是大於或等於 0 的整數")
        normalized.append({
            "request_item": request_items[item_id],
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "lead_time_days": lead_time_days,
            "warranty_months": warranty_months,
            "specification_snapshot": specifications,
        })
    return normalized


def _quote_values(payload, *, defaults=None):
    defaults = defaults or {}
    currency = str(payload.get("currency", defaults.get("currency", "TWD"))).upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise RfqQuoteError("currency 必須是 ISO 4217 三碼大寫幣別")
    return {
        "currency": currency,
        "exchange_rate_to_twd": _decimal(
            payload.get("exchange_rate_to_twd", defaults.get("exchange_rate_to_twd")),
            "exchange_rate_to_twd", places=6, positive=True,
        ),
        "tax_amount": _decimal(
            payload.get("tax_amount", defaults.get("tax_amount")), "tax_amount", places=2, default="0"
        ),
        "shipping_amount": _decimal(
            payload.get("shipping_amount", defaults.get("shipping_amount")),
            "shipping_amount",
            places=2,
            default="0",
        ),
        "discount_amount": _decimal(
            payload.get("discount_amount", defaults.get("discount_amount")),
            "discount_amount",
            places=2,
            default="0",
        ),
        "payment_terms_snapshot": str(payload.get("payment_terms", defaults.get("payment_terms_snapshot", ""))).strip(),
        "valid_until": _datetime(payload.get("valid_until", defaults.get("valid_until")), "valid_until"),
    }


def _ensure_open(invitation):
    now = timezone.now()
    if invitation.rfq.status not in (Rfq.Status.ISSUED, Rfq.Status.COLLECTING):
        raise RfqQuoteConflict("RFQ 尚未發出或已停止收件")
    if invitation.status in (RfqSupplier.Status.DECLINED, RfqSupplier.Status.EXPIRED, RfqSupplier.Status.CANCELLED):
        raise RfqQuoteConflict("此供應商邀請已無法回覆")
    if invitation.rfq.response_due_at and invitation.rfq.response_due_at <= now:
        raise QuoteExpired("RFQ 回覆期限已過")


def _create_quote_rows(invitation, payload, *, quote_no, revision, defaults=None):
    values = _quote_values(payload, defaults=defaults)
    items = _normalize_items(payload.get("items"), invitation.rfq.request)
    subtotal = sum((row["subtotal"] for row in items), Decimal("0.00"))
    original_total = subtotal + values["tax_amount"] + values["shipping_amount"] - values["discount_amount"]
    if original_total < 0:
        raise RfqQuoteError("折扣不可高於品項、稅額與運費合計")
    quote = SupplierQuote.objects.create(
        quote_no=quote_no,
        rfq_supplier=invitation,
        revision=revision,
        status=SupplierQuote.Status.DRAFT,
        items_subtotal=subtotal,
        landed_total_twd=(original_total * values["exchange_rate_to_twd"]).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        ),
        **values,
    )
    SupplierQuoteItem.objects.bulk_create([
        SupplierQuoteItem(supplier_quote=quote, **row) for row in items
    ])
    return quote


@transaction.atomic
def create_quote(user, payload):
    _require_permission(user, "supplier_quote.manage")
    try:
        invitation = SupplierQuoteRepository.invitation_for_update(payload.get("rfq_supplier_id"))
    except (ObjectDoesNotExist, TypeError, ValueError) as exc:
        raise RfqQuoteNotFound("找不到指定的 RFQ 供應商邀請") from exc
    _ensure_open(invitation)
    if invitation.quotes.filter(status__in=["draft", "submitted", "accepted_for_evaluation"]).exists():
        raise RfqQuoteConflict("此邀請已有進行中的報價")
    return _create_quote_rows(
        invitation, payload, quote_no=f"SQ-{uuid4().hex.upper()}", revision=1,
    )


def _typed_value(data_type, value):
    if data_type in ("string", "enum"):
        if not isinstance(value, str):
            raise ValueError
        return value
    if data_type == "number":
        if isinstance(value, bool):
            raise ValueError
        parsed = Decimal(str(value))
        if not parsed.is_finite():
            raise ValueError
        return parsed
    if data_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError
        return value
    raise ValueError


def _matches(requirement, actual):
    try:
        actual = _typed_value(requirement.data_type, actual)
        if requirement.operator == "in":
            if not isinstance(requirement.expected_value, list):
                return False
            expected = [_typed_value(requirement.data_type, value) for value in requirement.expected_value]
        else:
            expected = _typed_value(requirement.data_type, requirement.expected_value)
    except (InvalidOperation, TypeError, ValueError):
        return False
    if requirement.operator == "equals":
        return actual == expected
    if requirement.operator == "not_equals":
        return actual != expected
    if requirement.operator == "gte":
        return actual >= expected
    if requirement.operator == "lte":
        return actual <= expected
    if requirement.operator == "in":
        return actual in expected if isinstance(expected, list) else False
    if requirement.operator == "contains":
        return expected in actual if isinstance(actual, (str, list)) else False
    return False


def _record_requirement_results(quote):
    results = []
    for item in quote.items.select_related("request_item").prefetch_related("request_item__requirements"):
        for requirement in item.request_item.requirements.all():
            actual = item.specification_snapshot.get(requirement.code)
            if actual is None:
                result = QuoteRequirementResult.Result.NOT_PROVIDED
                evidence = "供應商未提供此規格"
            else:
                passed = _matches(requirement, actual)
                result = QuoteRequirementResult.Result.PASS if passed else QuoteRequirementResult.Result.FAIL
                evidence = f"供應商回覆值：{actual}"
            results.append(QuoteRequirementResult(
                quote_item=item,
                requirement=requirement,
                result=result,
                evidence=evidence,
            ))
    QuoteRequirementResult.objects.bulk_create(results)


def submit_quote(user, quote_id):
    _require_permission(user, "supplier_quote.manage")
    expired = False
    with transaction.atomic():
        try:
            quote = SupplierQuoteRepository.get_for_update(quote_id)
        except ObjectDoesNotExist as exc:
            raise RfqQuoteNotFound("找不到指定的供應商報價") from exc
        if quote.status != SupplierQuote.Status.DRAFT:
            raise RfqQuoteConflict("只有報價草稿可以提交")
        now = timezone.now()
        rfq = quote.rfq_supplier.rfq
        if (rfq.response_due_at and rfq.response_due_at <= now) or (quote.valid_until and quote.valid_until <= now):
            quote.status = SupplierQuote.Status.EXPIRED
            quote.save(update_fields=["status"])
            expired = True
        else:
            _ensure_open(quote.rfq_supplier)
            _record_requirement_results(quote)
            quote.status = SupplierQuote.Status.SUBMITTED
            quote.submitted_at = now
            quote.save(update_fields=["status", "submitted_at"])
            invitation = quote.rfq_supplier
            invitation.status = RfqSupplier.Status.RESPONDED
            invitation.responded_at = now
            invitation.save(update_fields=["status", "responded_at"])
            if rfq.status == Rfq.Status.ISSUED:
                rfq.status = Rfq.Status.COLLECTING
                rfq.save(update_fields=["status"])
    if expired:
        raise QuoteExpired("報價或 RFQ 回覆期限已過")
    return quote


@transaction.atomic
def revise_quote(user, quote_id, payload):
    _require_permission(user, "supplier_quote.manage")
    try:
        prior = SupplierQuoteRepository.get_for_update(quote_id)
        invitation = SupplierQuoteRepository.invitation_for_update(prior.rfq_supplier_id)
    except ObjectDoesNotExist as exc:
        raise RfqQuoteNotFound("找不到指定的供應商報價") from exc
    if prior.status not in (
        SupplierQuote.Status.SUBMITTED,
        SupplierQuote.Status.ACCEPTED_FOR_EVALUATION,
    ):
        raise RfqQuoteConflict("只有已提交或已納入評選的報價可以改版")
    _ensure_open(invitation)
    defaults = {
        "currency": prior.currency,
        "exchange_rate_to_twd": prior.exchange_rate_to_twd,
        "tax_amount": prior.tax_amount,
        "shipping_amount": prior.shipping_amount,
        "discount_amount": prior.discount_amount,
        "payment_terms_snapshot": prior.payment_terms_snapshot,
        "valid_until": prior.valid_until,
    }
    prior.status = SupplierQuote.Status.REVISED
    prior.save(update_fields=["status"])
    return _create_quote_rows(
        invitation,
        payload,
        quote_no=prior.quote_no,
        revision=prior.revision + 1,
        defaults=defaults,
    )


@transaction.atomic
def waive_requirement(user, result_id, reason):
    _require_permission(user, "requirement.waive")
    reason = str(reason or "").strip()
    if not reason:
        raise RfqQuoteError("reason 為必填")
    try:
        result = SupplierQuoteRepository.requirement_result_for_update(result_id)
    except ObjectDoesNotExist as exc:
        raise RfqQuoteNotFound("找不到指定的必要條件結果") from exc
    if result.result not in (
        QuoteRequirementResult.Result.FAIL,
        QuoteRequirementResult.Result.NOT_PROVIDED,
    ):
        raise RfqQuoteConflict("只有未符合或未提供的條件可以例外核准")
    result.result = QuoteRequirementResult.Result.WAIVED
    result.waiver_reason = reason
    result.waived_by = user
    result.waived_at = timezone.now()
    result.save(update_fields=["result", "waiver_reason", "waived_by", "waived_at"])
    return result
