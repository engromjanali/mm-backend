import hashlib
import hmac
from datetime import datetime, timezone

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions


def create_access_token(user):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.pk),
        "type": "access",
        "pwd": password_fingerprint(user),
        "iat": now,
        "exp": now + settings.JWT_ACCESS_TOKEN_LIFETIME,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def password_fingerprint(user):
    return hmac.new(
        settings.SECRET_KEY.encode(), user.password.encode(), hashlib.sha256
    ).hexdigest()


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

        try:
            payload = jwt.decode(
                header[1], settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )
        except jwt.ExpiredSignatureError as exc:
            raise exceptions.AuthenticationFailed("Token has expired.") from exc
        except jwt.PyJWTError as exc:
            raise exceptions.AuthenticationFailed("Invalid token.") from exc

        if payload.get("type") != "access" or not payload.get("sub"):
            raise exceptions.AuthenticationFailed("Invalid token.")

        try:
            user = get_user_model().objects.get(pk=payload["sub"], is_active=True)
        except get_user_model().DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("User not found.") from exc
        if not hmac.compare_digest(payload.get("pwd", ""), password_fingerprint(user)):
            raise exceptions.AuthenticationFailed("Token is no longer valid.")
        return user, payload

    def authenticate_header(self, request):
        return self.keyword
