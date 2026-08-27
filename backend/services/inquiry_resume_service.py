"""FR-6a：供應商模糊比對案件核准後，Django 主動通知 n8n 交還流程，
重新走一次遮罩→LLM 解析（此案件在 Mask 節點階段中止，品項/數量/幣別都還沒解析出來，
不能跳過解析直接查詢報價）。

呼叫時機：`services/manual_review_service.decide_review()` 核准 supplier_fuzzy_match
案件、DB 交易成功提交「之後」才呼叫（避免把外部 HTTP 呼叫包在 DB transaction 裡）。
"""
import requests
from django.conf import settings

RESUME_TIMEOUT_SECONDS = 30


class InquiryResumeError(Exception):
    """呼叫 n8n 續傳 webhook 失敗時拋出（連線問題、逾時、n8n 回傳非 2xx）。"""


def trigger_resume(*, review_id, raw_input_text, requester_id, supplier_id) -> None:
    """通知 n8n：這個模糊比對案件的供應商已由人工確認，可以重新開始處理。

    不回傳、不阻塞決議 API 的回應——n8n 這段是非同步接續處理，呼叫失敗只記錄錯誤，
    不影響 `decide_review()` 本身已經成功的決議結果（決議結果已經落地 DB，是真的）。
    """
    try:
        response = requests.post(
            settings.N8N_RESUME_WEBHOOK_URL,
            json={
                "review_id": review_id,
                "raw_input_text": raw_input_text,
                "user_id": requester_id,
                "supplier_id": supplier_id,
            },
            headers={"X-Internal-Api-Key": settings.INTERNAL_API_KEY},
            timeout=RESUME_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise InquiryResumeError("通知 n8n 續傳流程失敗，請稍後手動確認") from exc
