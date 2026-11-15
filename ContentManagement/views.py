"""
Public app content, managed in Django admin, under ``/api/v1/app/`` and public web routes.

No login needed (the app and public web visitors read these before sign-in, e.g. on
the splash and login screens, app stores, or web browsers). Text comes in the app's
language — ``?lang=`` or the ``X-localization`` header the app sends — falling back to English.
"""
import html
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View
from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from ContentManagement.models import DEFAULT_LANGUAGE, LANGUAGES, AppSetting, ContentPage, Faq, SupportChannel

SUPPORTED_LANGUAGES = {code for code, _ in LANGUAGES}


def request_language(request):
    """`?lang=`, then the app's `X-localization` / `locale` header, then English."""
    query_params = getattr(request, 'query_params', None)
    lang_val = query_params.get('lang') if query_params is not None else request.GET.get('lang')
    for value in (lang_val, request.headers.get('X-localization'), request.headers.get('locale')):
        code = (value or '').strip().lower()[:2]
        if code in SUPPORTED_LANGUAGES:
            return code
    return DEFAULT_LANGUAGE


def format_content_to_html(body: str) -> str:
    """
    Format plain-text/markdown body to safe HTML.
    - '# ' -> <h2>...</h2>
    - '## ' -> <h3>...</h3>
    - '- ' -> <ul><li>...</li></ul>
    - Blank lines separate paragraphs -> <p>...</p>
    """
    if not body:
        return ""

    escaped = html.escape(body.strip())
    blocks = [b.strip() for b in escaped.split('\n\n') if b.strip()]
    html_parts = []

    for block in blocks:
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if not lines:
            continue

        first = lines[0]
        if first.startswith('# ') or first.startswith('## '):
            level = '3' if first.startswith('## ') else '2'
            heading_title = first[3:].strip() if level == '3' else first[2:].strip()
            html_parts.append(f'<h{level}>{heading_title}</h{level}>')
            lines = lines[1:]

        if lines:
            curr_para = []
            curr_list = []
            for line in lines:
                if line.startswith('- '):
                    if curr_para:
                        html_parts.append(f'<p>{"<br>".join(curr_para)}</p>')
                        curr_para = []
                    curr_list.append(f'<li>{line[2:].strip()}</li>')
                else:
                    if curr_list:
                        html_parts.append(f'<ul>{"".join(curr_list)}</ul>')
                        curr_list = []
                    curr_para.append(line)
            if curr_para:
                html_parts.append(f'<p>{"<br>".join(curr_para)}</p>')
            if curr_list:
                html_parts.append(f'<ul>{"".join(curr_list)}</ul>')

    return "\n".join(html_parts)


def config_json(setting, request=None):
    channels = list(SupportChannel.objects.filter(Q(is_active=True) | Q(kind='email')))
    email_channels = [channel for channel in channels if channel.kind == 'email']
    support_email = next((channel.destination for channel in email_channels if channel.is_active), '') if email_channels else setting.support_email
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
        "support_email": support_email,
        "support_channels": [
            {
                'name': channel.name,
                'kind': channel.kind,
                'destination': channel.destination,
                'url': channel.contact_url,
                'logo_url': request.build_absolute_uri(channel.logo.url) if request and channel.logo else channel.logo.url if channel.logo else '',
            }
            for channel in channels if channel.is_active
        ],
        "privacy_policy_url": request.build_absolute_uri('/privacy-policy/') if request else '/privacy-policy/',
        "terms_and_conditions_url": request.build_absolute_uri('/terms-and-conditions/') if request else '/terms-and-conditions/',
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
        return Response(config_json(AppSetting.current(), request))


class ContentPageView(PublicView):
    """
    GET /api/v1/app/pages/privacy-policy
    GET /api/v1/app/pages/terms-and-conditions
    GET /api/v1/app/privacy-policy
    GET /api/v1/app/terms-and-conditions
    GET /api/v1/privacy-policy
    GET /api/v1/terms-and-conditions
    """

    def get(self, request, kind=None):
        target_kind = kind or self.kwargs.get('kind')
        pages = ContentPage.objects.filter(kind=target_kind, is_public=True)
        language = request_language(request)
        page = pages.filter(language=language).first() or pages.filter(language=DEFAULT_LANGUAGE).first()
        if page is None:
            raise NotFound("This page hasn't been published yet.")
        return Response({
            "kind": page.kind,
            "language": page.language,
            "title": page.title,
            "body": page.body,
            "updated_at": page.updated_at,
        })


class PublicContentWebOrApiView(View):
    """
    Public web and API view for Privacy Policy and Terms and Conditions.

    Renders clean, branded HTML for browser visitors, and JSON if requested
    by API clients (Accept: application/json or ?format=json).
    """
    kind = 'privacy-policy'

    def get(self, request, kind=None):
        target_kind = kind or getattr(self, 'kind', None) or self.kwargs.get('kind') or 'privacy-policy'

        accept_header = request.headers.get('Accept', '')
        wants_json = request.GET.get('format') == 'json' or (
            'application/json' in accept_header and 'text/html' not in accept_header
        )

        pages = ContentPage.objects.filter(kind=target_kind, is_public=True)
        requested_lang = request_language(request)
        page = pages.filter(language=requested_lang).first()
        is_fallback = False
        if page is None:
            page = pages.filter(language=DEFAULT_LANGUAGE).first()
            if page and requested_lang != DEFAULT_LANGUAGE:
                is_fallback = True

        if page is None:
            if wants_json:
                return JsonResponse({"detail": "This page hasn't been published yet."}, status=404)
            return render(
                request,
                'content/public_page_404.html',
                {'kind': target_kind, 'title': 'Page Not Found'},
                status=404,
            )

        if wants_json:
            return JsonResponse({
                "kind": page.kind,
                "language": page.language,
                "title": page.title,
                "body": page.body,
                "updated_at": page.updated_at.isoformat() if hasattr(page.updated_at, 'isoformat') else str(page.updated_at),
            })

        body_html = format_content_to_html(page.body)
        setting = AppSetting.current()

        available_languages = list(
            ContentPage.objects.filter(kind=target_kind, is_public=True).values_list('language', flat=True)
        )

        is_privacy = target_kind == ContentPage.PRIVACY_POLICY
        other_kind = ContentPage.TERMS if is_privacy else ContentPage.PRIVACY_POLICY
        other_title = 'Terms and Conditions' if is_privacy else 'Privacy Policy'
        other_url = '/terms-and-conditions/' if is_privacy else '/privacy-policy/'

        context = {
            'page': page,
            'title': page.title,
            'body_html': body_html,
            'kind': target_kind,
            'kind_display': dict(ContentPage.KINDS).get(target_kind, page.title),
            'current_language': page.language,
            'requested_language': requested_lang,
            'is_fallback': is_fallback,
            'available_languages': available_languages,
            'support_email': setting.support_email,
            'other_kind': other_kind,
            'other_title': other_title,
            'other_url': other_url,
        }
        return render(request, 'content/public_page.html', context)


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
