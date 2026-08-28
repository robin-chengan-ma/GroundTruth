import hashlib
from datetime import UTC, datetime

from django.contrib.auth.hashers import check_password
from django.db import transaction
from django.db.models.functions import Now
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import RefreshSession, User


class AuthenticationError(Exception):
    """登入或 Refresh Session 無效。"""


def authenticate_credentials(email, password):
    try:
        user = User.objects.select_related("role").get(email__iexact=(email or "").strip())
    except User.DoesNotExist as exc:
        raise AuthenticationError("帳號或密碼錯誤") from exc
    if not check_password(password or "", user.password):
        raise AuthenticationError("帳號或密碼錯誤")
    return user


def issue_token_pair(user):
    refresh = _build_refresh(user)
    session = _create_session(user, refresh)
    return str(refresh.access_token), str(refresh), session


@transaction.atomic
def rotate_refresh_token(raw_token):
    refresh = _parse_refresh(raw_token)
    try:
        current = RefreshSession.objects.select_for_update().select_related("user__role").get(
            token_hash=_hash_token(raw_token),
            jti=str(refresh["jti"]),
            revoked_at__isnull=True,
            expires_at__gt=Now(),
        )
    except RefreshSession.DoesNotExist as exc:
        raise AuthenticationError("Refresh Token 已失效") from exc

    replacement = _build_refresh(current.user)
    replacement_session = _create_session(current.user, replacement)
    RefreshSession.objects.filter(pk=current.pk).update(revoked_at=Now(), replaced_by=replacement_session)
    return str(replacement.access_token), str(replacement)


def revoke_refresh_token(raw_token):
    if raw_token:
        RefreshSession.objects.filter(
            token_hash=_hash_token(raw_token), revoked_at__isnull=True
        ).update(revoked_at=Now())


def _build_refresh(user):
    refresh = RefreshToken()
    refresh["user_id"] = user.id
    refresh["role"] = user.role.role
    return refresh


def _create_session(user, refresh):
    return RefreshSession.objects.create(
        user=user,
        jti=str(refresh["jti"]),
        token_hash=_hash_token(str(refresh)),
        expires_at=datetime.fromtimestamp(refresh["exp"], tz=UTC),
    )


def _parse_refresh(raw_token):
    if not raw_token:
        raise AuthenticationError("缺少 Refresh Token")
    try:
        return RefreshToken(raw_token)
    except TokenError as exc:
        raise AuthenticationError("Refresh Token 已失效") from exc


def _hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
