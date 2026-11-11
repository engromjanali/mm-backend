"""Verification of Google OAuth ID tokens used by ``POST /api/v1/auth/google``.

The Flutter client obtains an ID token from Google Sign-In and sends it here;
this module validates the token's signature, issuer and audience before the
email is trusted. The view then signs in the matching account or creates one.
"""

from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework.exceptions import APIException, ValidationError


class GoogleAuthUnavailable(APIException):
    status_code = 503
    default_detail = 'Google sign-in is not configured.'
    default_code = 'google_auth_unavailable'


def _is_true(value):
    return value is True or (isinstance(value, str) and value.lower() == 'true') or value == 1


def verify_google_id_token(raw_token):
    """Return the verified token claims or raise a DRF exception."""
    allowed_client_ids = settings.GOOGLE_OAUTH_CLIENT_IDS
    if not allowed_client_ids:
        raise GoogleAuthUnavailable()

    if not raw_token or not isinstance(raw_token, str):
        raise ValidationError({'id_token': 'A Google ID token is required.'})

    try:
        claims = id_token.verify_oauth2_token(raw_token, google_requests.Request())
    except Exception:
        raise ValidationError({'id_token': 'Invalid or expired Google token.'}) from None

    if claims.get('aud') not in allowed_client_ids:
        raise ValidationError({'id_token': 'Google token was issued for a different application.'})

    if not _is_true(claims.get('email_verified')):
        raise ValidationError({'id_token': 'Google account email is not verified.'})

    email = (claims.get('email') or '').strip().lower()
    if not email:
        raise ValidationError({'id_token': 'Google token did not include an email address.'})

    claims['email'] = email
    return claims
