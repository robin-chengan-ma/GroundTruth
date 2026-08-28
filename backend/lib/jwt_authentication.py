from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.core.models import User


class BusinessJwtAuthentication(BaseAuthentication):
    """驗證 JWT 簽章，再從專案 users 表取得即時角色資料。"""

    keyword = b"Bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts:
            return None
        if parts[0] != self.keyword or len(parts) != 2:
            raise exceptions.AuthenticationFailed("無效的認證資訊")
        try:
            token = AccessToken(parts[1].decode("utf-8"))
            user = User.objects.select_related("role").get(pk=token["user_id"])
        except (TokenError, KeyError, UnicodeDecodeError, User.DoesNotExist) as exc:
            raise exceptions.AuthenticationFailed("登入狀態已失效") from exc
        return user, token

    def authenticate_header(self, request):
        return "Bearer"
