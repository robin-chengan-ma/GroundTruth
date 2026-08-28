"""FR-1：接收自然語言詢價文字，觸發 n8n Webhook 啟動主流程。

同步呼叫 n8n Webhook 並把 n8n 最終回應原樣傳回；n8n 內部的遮罩/幻覺驗證/簽核路由等步驟
屬於各自 Phase 範圍。

user_id：詢價發起人，Phase 3 起一路傳給 n8n → quotes/calculate/ 用來建立 Quote 資料列
（Vue＋JWT 使用者驗證留待 Phase 4，這裡先由呼叫端明確帶入，見 docs/ADR/discuss/main-flow.md）。
"""
import re

import requests
from django.conf import settings

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
