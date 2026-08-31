"""自然語言詢價與新版採購需求候選解析服務。"""
import re
import unicodedata
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

from apps.crm.models import Supplier
from apps.erp.models import Product
from repositories.inquiry import request_candidate_parse
from services.masking_service import mask_candidate_text, unmask_payload

INQUIRY_TIMEOUT_SECONDS = 30


class InquiryTriggerError(Exception):
    """呼叫 n8n Webhook 失敗（連線問題、逾時、n8n 回傳非 2xx）時拋出。"""


class InquiryValidationError(InquiryTriggerError):
    """使用者輸入缺少可驗證的必要欄位。"""


FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
QUANTITY_UNITS = "個|件|台|組|箱|張|支|份|套|包|瓶|顆|本|盒"
ARABIC_QUANTITY_PATTERNS = (
    re.compile(rf"([1-9]\d*)\s*(?:{QUANTITY_UNITS})"),
    re.compile(r"數量\s*[:：]?\s*([1-9]\d*)"),
)
CHINESE_QUANTITY_PATTERNS = (
    re.compile(rf"([零〇一二兩三四五六七八九十百千萬]+)\s*(?:{QUANTITY_UNITS})"),
    re.compile(r"數量\s*[:：]?\s*([零〇一二兩三四五六七八九十百千萬]+)"),
)
CHINESE_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5,
                  "六": 6, "七": 7, "八": 8, "九": 9}
CHINESE_UNITS = {"十": 10, "百": 100, "千": 1000, "萬": 10000}


def _parse_chinese_integer(value):
    total = section = number = 0
    for character in value:
        if character in CHINESE_DIGITS:
            number = CHINESE_DIGITS[character]
            continue
        unit = CHINESE_UNITS[character]
        if unit == 10000:
            total += (section + number) * unit
            section = number = 0
        else:
            section += (number or 1) * unit
            number = 0
    return total + section + number


def _explicit_quantities(raw_text):
    normalized_text = raw_text.translate(FULLWIDTH_DIGITS)
    quantities = {
        int(match.group(1))
        for pattern in ARABIC_QUANTITY_PATTERNS
        for match in pattern.finditer(normalized_text)
    }
    quantities.update(
        _parse_chinese_integer(match.group(1))
        for pattern in CHINESE_QUANTITY_PATTERNS
        for match in pattern.finditer(normalized_text)
    )
    return {quantity for quantity in quantities if quantity > 0}


def trigger_inquiry(raw_text: str, user_id=None) -> dict:
    if not raw_text or not raw_text.strip():
        raise InquiryValidationError("詢價內容不可為空")

    if not _explicit_quantities(raw_text):
        raise InquiryValidationError("詢價內容格式無法解析，請提供明確的正整數數量")

    try:
        response = requests.post(
            settings.N8N_INQUIRY_WEBHOOK_URL,
            json={"raw_text": raw_text, "user_id": user_id},
            headers={"X-Internal-Api-Key": settings.INTERNAL_API_KEY},
            timeout=INQUIRY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, requests.JSONDecodeError) as exc:
        # 錯誤訊息不得洩漏內部服務位址/金鑰等細節，只回傳一般化訊息。
        raise InquiryTriggerError("詢價流程觸發失敗，請稍後再試") from exc


def _candidate_list(payload, field):
    value = payload.get(field, [])
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise InquiryTriggerError("AI 候選資料格式錯誤，請重新解析")
    return value


def _normalize_candidate_quantity(value):
    if value in (None, ""):
        return None
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not quantity.is_finite() or quantity <= 0 or quantity.as_tuple().exponent < -3:
        return None
    return format(quantity, "f")


def _resolve_supplier(name):
    matches = Supplier.objects.filter(
        name__iexact=str(name or "").strip(), is_active=True, status="active",
    )[:2]
    return matches[0] if len(matches) == 1 else None


def _resolve_product(name):
    matches = Product.objects.filter(name__iexact=str(name or "").strip(), is_active=True)[:2]
    return matches[0] if len(matches) == 1 else None


def _normalize_product_text(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    normalized = re.sub(r"[‐‑‒–—−]", "-", normalized)
    return re.sub(r"\s+", "", normalized)


def _explicit_product_candidates(raw_text):
    normalized_raw_text = _normalize_product_text(raw_text)
    return [
        product
        for product in Product.objects.filter(is_active=True).only("id", "name", "unit_of_measure")
        if _normalize_product_text(product.name) in normalized_raw_text
    ]


def _resolve_product_from_explicit_raw_name(name, explicit_products):
    normalized_name = _normalize_product_text(name)
    if len(normalized_name) < 2:
        return None
    matches = [
        product
        for product in explicit_products
        if normalized_name in _normalize_product_text(product.name)
    ]
    return matches[0] if len(matches) == 1 else None


def parse_purchase_request_candidate(raw_text: str, *, user_id: int) -> dict:
    """FR-3／NFR-1：遮罩後解析並對應主檔，只回傳候選資料，不建立單據。"""
    if not raw_text or not raw_text.strip():
        raise InquiryValidationError("採購需求不可為空")

    masking_result = mask_candidate_text(raw_text.strip(), requester_id=user_id)
    if masking_result["outcome"] == "supplier_fuzzy_match":
        raise InquiryValidationError("供應商名稱需要人工複核，請至人工複核佇列處理")
    if masking_result["outcome"] == "supplier_not_found":
        raise InquiryValidationError("找不到可確認的供應商，請檢查名稱後再試")

    try:
        parsed = request_candidate_parse(masking_result["masked_text"], user_id=user_id)
    except (requests.RequestException, requests.JSONDecodeError) as exc:
        raise InquiryTriggerError("AI 需求解析失敗，請稍後再試") from exc
    if not isinstance(parsed, dict):
        raise InquiryTriggerError("AI 候選資料格式錯誤，請重新解析")
    parsed = unmask_payload(parsed, masking_result["mapping"])

    supplier_rows = _candidate_list(parsed, "suppliers")
    item_rows = _candidate_list(parsed, "items")
    explicit_products = _explicit_product_candidates(raw_text)
    missing_fields = []
    suppliers = []
    for index, row in enumerate(supplier_rows):
        supplier_name = str(row.get("name") or row.get("supplier_name") or "").strip()
        supplier = _resolve_supplier(supplier_name)
        if supplier is None:
            missing_fields.append(f"supplier_candidates.{index}.supplier_id")
        suppliers.append({
            "supplier_id": supplier.id if supplier else None,
            "supplier_name": supplier.name if supplier else supplier_name,
        })
    if not suppliers:
        missing_fields.append("supplier_candidates")

    items = []
    for index, row in enumerate(item_rows):
        product_name = str(row.get("product_name") or row.get("name") or "").strip()
        product = _resolve_product(product_name) or _resolve_product_from_explicit_raw_name(
            product_name, explicit_products,
        )
        quantity = _normalize_candidate_quantity(row.get("quantity"))
        specifications = row.get("specifications") or {}
        if not isinstance(specifications, dict):
            specifications = {"description": str(specifications)}
        if product is None:
            missing_fields.append(f"items.{index}.product_id")
        if quantity is None:
            missing_fields.append(f"items.{index}.quantity")
        items.append({
            "product_id": product.id if product else None,
            "product_name": product.name if product else product_name,
            "quantity": quantity,
            "unit_of_measure": str(row.get("unit_of_measure") or (product.unit_of_measure if product else "EA")),
            "specifications": specifications,
        })
    if not items:
        missing_fields.append("items")

    return {
        "purpose": str(parsed.get("purpose") or raw_text).strip(),
        "needed_by": parsed.get("needed_by") or None,
        "currency": str(parsed.get("currency") or "TWD").upper(),
        "assistant_message": str(parsed.get("assistant_message") or "請確認 AI 整理的需求內容。"),
        "supplier_candidates": suppliers,
        "items": items,
        "missing_fields": missing_fields,
        "ready_for_draft": not missing_fields,
    }
