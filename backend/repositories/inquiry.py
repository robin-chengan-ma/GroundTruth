"""n8n 自然語言候選解析的外部連線。"""

import requests
from django.conf import settings


def request_candidate_parse(raw_text: str, *, user_id: int) -> dict:
    response = requests.post(
        settings.N8N_INQUIRY_PARSE_WEBHOOK_URL,
        json={"raw_text": raw_text, "user_id": user_id},
        headers={"X-Internal-Api-Key": settings.INTERNAL_API_KEY},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
