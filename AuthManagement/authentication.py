import hashlib
import hmac
from datetime import datetime, timezone

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

ACCESS_TOKEN = "access"
REFRESH_TOKEN = "refresh"


def create_token(user, token_type, lifetime):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.pk),
        "type": token_type,
        "pwd": password_fingerprint(user),
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user):
    return create_token(user, ACCESS_TOKEN, settings.JWT_ACCESS_TOKEN_LIFETIME)


def create_refresh_token(user):
    """
    Long-lived token whose only power is to mint new access tokens through
    /api/v1/auth/refresh-token.  It carries the same password fingerprint as
    an access token, so changing the password kills it too.
    """
    return create_token(user, REFRESH_TOKEN, settings.JWT_REFRESH_TOKEN_LIFETIME)


def password_fingerprint(user):
    return hmac.new(
        settings.SECRET_KEY.encode(), user.password.encode(), hashlib.sha256
    ).hexdigest()


def resolve_token_user(token, expected_type):
    """
    Decodes a token, checks it is of ``expected_type`` and still matches the
    user's current password, and returns the (user, payload) pair.
    Raises ``AuthenticationFailed`` on anything unexpected.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError as exc:
        raise exceptions.AuthenticationFailed("Token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise exceptions.AuthenticationFailed("Invalid token.") from exc

    if payload.get("type") != expected_type or not payload.get("sub"):
        raise exceptions.AuthenticationFailed("Invalid token.")

    try:
        user = get_user_model().objects.get(pk=payload["sub"], is_active=True)
    except get_user_model().DoesNotExist as exc:
        raise exceptions.AuthenticationFailed("User not found.") from exc

    if not hmac.compare_digest(payload.get("pwd", ""), password_fingerprint(user)):
        raise exceptions.AuthenticationFailed("Token is no longer valid.")
    return user, payload


class JWTAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header:
            return None
        if header[0].decode(errors="ignore").lower() != self.keyword.lower():
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("Invalid Authorization header.")

        # A refresh token is rejected here: only access tokens open the API.
        return resolve_token_user(header[1], ACCESS_TOKEN)

    def authenticate_header(self, request):
        return self.keyword
