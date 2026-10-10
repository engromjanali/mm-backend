"""
Public app content, managed in Django admin, under ``/api/v1/app/``.

No login needed (the app reads these before sign-in, e.g. on the splash and
login screens). Text comes in the app's language — ``?lang=`` or the
``X-localization`` header the app sends — falling back to English.
"""
from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DEFAULT_LANGUAGE, LANGUAGES, AppSetting, ContentPage, Faq

SUPPORTED_LANGUAGES = {code for code, _ in LANGUAGES}


def request_language(request):
    """`?lang=`, then the app's `X-localization` / `locale` header, then English."""
    for value in (request.query_params.get('lang'), request.headers.get('X-localization'), request.headers.get('locale')):
        code = (value or '').strip().lower()[:2]
        if code in SUPPORTED_LANGUAGES:
            return code
    return DEFAULT_LANGUAGE


def config_json(setting):
    return {
        "message": "API configuration",
        # Kept for older app builds that read only `version`.
        "version": setting.latest_version,
        "latest_version": setting.latest_version,
        "minimum_version": setting.minimum_version,
        "update_message": setting.update_message,
        "android_store_url": setting.android_store_url,
        "ios_store_url": setting.ios_store_url,
        "maintenance": {
            "enabled": setting.maintenance_mode,
            "message": setting.maintenance_message,
            "until": setting.maintenance_until,
        },
        "support_email": setting.support_email,
    }


class PublicView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]


class AppConfigView(PublicView):
    """
    GET /api/v1/app/config   (also /api/v1/auth/config for older builds)

    Versions (``latest_version`` → optional update, ``minimum_version`` →
    forced update), maintenance mode and store / support links.
    """

    def get(self, request):
        return Response(config_json(AppSetting.current()))


class ContentPageView(PublicView):
    """
    GET /api/v1/app/pages/privacy-policy
    GET /api/v1/app/pages/terms-and-conditions
    """

    def get(self, request, kind):
        pages = ContentPage.objects.filter(kind=kind)
        language = request_language(request)
        page = pages.filter(language=language).first() or pages.filter(language=DEFAULT_LANGUAGE).first()
        if page is None:
            raise NotFound("This page hasn't been published yet.")
        return Response({"kind": page.kind, "language": page.language, "title": page.title, "body": page.body, "updated_at": page.updated_at})


class FaqListView(PublicView):
    """GET /api/v1/app/faqs — active questions in the app's language (English if it has none)."""

    def get(self, request):
        faqs = Faq.objects.filter(is_active=True)
        language = request_language(request)
        if not faqs.filter(language=language).exists():
            language = DEFAULT_LANGUAGE
        return Response([
            {"id": faq.id, "question": faq.question, "answer": faq.answer}
            for faq in faqs.filter(language=language)
        ])
