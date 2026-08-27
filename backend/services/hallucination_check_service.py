"""FR-5a／NFR-2：幻覺驗證機制。

驗證邏輯是固定程式碼（regex ＋ 字串比對），不交給 AI 判斷是否正確（NFR-2 可信度要求）。
嚴謹標準（已與使用者確認，2026-08-27）：
1. 金額／數量：零容忍，summary 文字裡必須「剛好」出現 quantity／unit_price／total_amount
   這三個真實數字（去除千分位逗號後精確比對），且不能出現任何無法對應到這三者的多餘數字
   ——只要有一個沒對到，或多一個對不到，就判定失敗。
2. 供應商／產品名稱：去除常見中文公司後綴取「核心字串」，核心字串必須完整出現在 summary 文字中
   （避免公司全名格式差異 [例如「股份有限公司」vs 「公司」] 被誤判為幻覺）。

任一項失敗 → 寫入 manual_review_queue（review_type=hallucination_mismatch，此時 Quote 已存在，
quote_id 照填），交由人工複核。
"""
import re
from decimal import Decimal, InvalidOperation

from apps.audit.models import ManualReviewQueue

# 常見中文公司後綴，由長到短嘗試剝除（避免複合後綴剝一半殘留）。
_COMPANY_SUFFIXES = [
    "股份有限公司",
    "有限合夥事業",
    "有限公司",
    "企業社",
    "工作室",
    "商行",
    "行號",
    "有限合夥",
]

_NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?")


class HallucinationCheckError(Exception):
    """驗證輸入有誤時拋出（例如缺少必要欄位）。"""


def check_summary(
    *,
    summary_text: str,
    quote,
    quantity,
    unit_price,
    total_amount,
    supplier_name: str,
    product_name: str,
) -> dict:
    """驗證 LLM 生成的 summary_text 是否忠實反映真實數字與名稱。

    quote: 對應的 Quote 物件（此階段必已存在，驗證失敗時寫入 manual_review_queue 用）。

    回傳：
        {"passed": True} 或
        {"passed": False, "reasons": [str, ...], "review_id": int}
    """
    if not summary_text or not summary_text.strip():
        raise HallucinationCheckError("summary_text 不可為空")

    reasons = []

    number_reasons = _check_numbers(summary_text, quantity, unit_price, total_amount)
    reasons.extend(number_reasons)

    supplier_core = _strip_company_suffix(supplier_name)
    if supplier_core and supplier_core not in summary_text:
        reasons.append(f"供應商名稱核心字串「{supplier_core}」未出現在摘要文字中")

    product_core = _strip_company_suffix(product_name)
    if product_core and product_core not in summary_text:
        reasons.append(f"產品名稱核心字串「{product_core}」未出現在摘要文字中")

    if not reasons:
        return {"passed": True}

    review = ManualReviewQueue.objects.create(
        quote=quote,
        review_type=ManualReviewQueue.ReviewType.HALLUCINATION_MISMATCH,
        ai_generated_text=summary_text,
        expected_value=_format_expected_value(quantity, unit_price, total_amount, supplier_name, product_name),
    )
    # FR-6：不一致時流程中止，Quote 停在待複核狀態，直到人工決議（見 manual_review_service）。
    quote.status = quote.__class__.Status.PENDING_REVIEW
    quote.save(update_fields=["status"])
    return {"passed": False, "reasons": reasons, "review_id": review.id}


def _check_numbers(summary_text: str, quantity, unit_price, total_amount) -> list:
    expected = {}
    for label, value in (("quantity", quantity), ("unit_price", unit_price), ("total_amount", total_amount)):
        try:
            expected[label] = Decimal(str(value))
        except (InvalidOperation, TypeError):
            raise HallucinationCheckError(f"{label} 不是合法數字：{value!r}") from None

    found_decimals = []
    for match in _NUMBER_PATTERN.finditer(summary_text):
        raw = match.group(0).replace(",", "")
        try:
            found_decimals.append(Decimal(raw))
        except InvalidOperation:  # pragma: no cover - _NUMBER_PATTERN 保證只會抓到合法數字格式
            continue

    reasons = []
    missing_labels = [label for label, value in expected.items() if value not in found_decimals]
    if missing_labels:
        reasons.append(f"摘要文字缺少真實數字：{', '.join(missing_labels)}")

    expected_values = set(expected.values())
    extra_numbers = [d for d in found_decimals if d not in expected_values]
    if extra_numbers:
        formatted = ", ".join(str(n) for n in extra_numbers)
        reasons.append(f"摘要文字出現無法對應到真實數字的多餘數字：{formatted}")

    return reasons


def _strip_company_suffix(name: str) -> str:
    if not name:
        return ""
    result = name.strip()
    changed = True
    while changed:
        changed = False
        for suffix in sorted(_COMPANY_SUFFIXES, key=len, reverse=True):
            if result.endswith(suffix) and len(result) > len(suffix):
                result = result[: -len(suffix)]
                changed = True
                break
    return result


def _format_expected_value(quantity, unit_price, total_amount, supplier_name, product_name) -> str:
    import json

    return json.dumps(
        {
            "quantity": str(quantity),
            "unit_price": str(unit_price),
            "total_amount": str(total_amount),
            "supplier_name": supplier_name,
            "product_name": product_name,
        },
        ensure_ascii=False,
    )
