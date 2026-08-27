"""n8n ↔ Django 內部服務認證（FR-1a）。

用固定 API Key 驗證自訂 header（`X-Internal-Api-Key`），不套用使用者登入流程。
金鑰只從環境變數讀取，不寫死在程式碼裡；比對用 `secrets.compare_digest` 避免時序攻擊。
錯誤訊息不得洩漏金鑰內容或內部細節（見 AGENTS.md 敏感資料處理規則）。
"""
import hmac

from django.conf import settings
from rest_framework import authentication, exceptions

API_KEY_HEADER = "X-Internal-Api-Key"


class InternalServiceUser:
    """代表呼叫端是內部服務（n8n），不是真人使用者；不對應 apps.core.models.User。"""

    is_authenticated = True

    def __str__(self):
        return "internal-service(n8n)"


class InternalApiKeyAuthentication(authentication.BaseAuthentication):
    """給 n8n 呼叫 Django 內部端點使用。前端使用者請求不應套用此驗證方式。"""

    def authenticate(self, request):
        provided_key = request.META.get(f"HTTP_{API_KEY_HEADER.upper().replace('-', '_')}")
        if not provided_key:
            return None  # 沒帶這個 header，交給其他 authentication class 或 permission 處理

        configured_key = getattr(settings, "INTERNAL_API_KEY", "")
        if not configured_key or not hmac.compare_digest(provided_key, configured_key):
            raise exceptions.AuthenticationFailed("Invalid internal API key.")

        return (InternalServiceUser(), None)

    def authenticate_header(self, request):
        # 有這個方法，DRF 才會把驗證失敗回成 401（帶 WWW-Authenticate）而不是 403。
        return API_KEY_HEADER
