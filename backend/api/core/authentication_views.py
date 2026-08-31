from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.crypto import constant_time_compare
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from lib.jwt_authentication import BusinessJwtAuthentication
from services.authentication_service import (
    AuthenticationError,
    authenticate_credentials,
    issue_token_pair,
    revoke_refresh_token,
    rotate_refresh_token,
)
from services.rbac_service import get_permission_codes


def _user_payload(user):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role.role,
        "permissions": sorted(get_permission_codes(user)),
    }


def _set_refresh_cookie(response, token):
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="Lax",
        path="/api/v1/auth/",
    )


def _csrf_is_valid(request):
    cookie_token = request.COOKIES.get(settings.CSRF_COOKIE_NAME, "")
    header_token = request.headers.get("X-CSRFToken", "")
    return bool(cookie_token and header_token and constant_time_compare(cookie_token, header_token))


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            user = authenticate_credentials(request.data.get("email"), request.data.get("password"))
        except AuthenticationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        access, refresh, _ = issue_token_pair(user)
        get_token(request)
        response = Response({"access": access, "user": _user_payload(user)})
        _set_refresh_cookie(response, refresh)
        return response


class RefreshView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if not _csrf_is_valid(request):
            return Response({"detail": "CSRF 驗證失敗"}, status=status.HTTP_403_FORBIDDEN)
        try:
            access, refresh = rotate_refresh_token(request.COOKIES.get(settings.REFRESH_COOKIE_NAME))
        except AuthenticationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        response = Response({"access": access})
        _set_refresh_cookie(response, refresh)
        return response


class LogoutView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if not _csrf_is_valid(request):
            return Response({"detail": "CSRF 驗證失敗"}, status=status.HTTP_403_FORBIDDEN)
        revoke_refresh_token(request.COOKIES.get(settings.REFRESH_COOKIE_NAME))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/api/v1/auth/", samesite="Lax")
        return response


class MeView(APIView):
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(_user_payload(request.user))
