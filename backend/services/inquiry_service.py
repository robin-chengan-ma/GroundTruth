"""FR-1：接收自然語言詢價文字，觸發 n8n Webhook 啟動主流程。

Phase 2 範圍：同步呼叫 n8n Webhook 並把 n8n 最終回應原樣傳回；
n8n 內部的遮罩/幻覺驗證/簽核路由等後續步驟屬於 Phase 3 以後範圍。
"""
import requests
from django.conf import settings

INQUIRY_TIMEOUT_SECONDS = 30


class InquiryTriggerError(Exception):
    """呼叫 n8n Webhook 失敗（連線問題、逾時、n8n 回傳非 2xx）時拋出。"""


def trigger_inquiry(raw_text: str) -> dict:
    if not raw_text or not raw_text.strip():
        raise InquiryTriggerError("詢價內容不可為空")

    try:
        response = requests.post(
            settings.N8N_INQUIRY_WEBHOOK_URL,
            json={"raw_text": raw_text},
            headers={"X-Internal-Api-Key": settings.INTERNAL_API_KEY},
            timeout=INQUIRY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        # 錯誤訊息不得洩漏內部服務位址/金鑰等細節，只回傳一般化訊息。
        raise InquiryTriggerError("詢價流程觸發失敗，請稍後再試") from exc

    return response.json()
