"""
Notice board APIs, scoped to the caller's active season.

Like deposits and costs, notices belong to a season: a new season starts with
an empty board. Every member (the manager included) reads the notices; the
manager / acting manager publishes, edits, deletes and pins them. At most one
notice per season is pinned — pinning one unpins the others, and a database
constraint backs that up.

User endpoints live under ``/api/v1/user/`` and manager endpoints under
``/api/v1/admin/``.
"""
from django.db import IntegrityError, transaction
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .membership_views import get_managed_membership
from .models import Notices
from .utils import get_active_membership

TITLE_MAX_LENGTH = Notices._meta.get_field('title').max_length
DESCRIPTION_MAX_LENGTH = 2000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class NoticeConflict(APIException):
    """409 — another pin won a race for the season's single pinned slot."""
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Another notice was pinned at the same time. Refresh and try again."
    default_code = 'conflict'


def notice_json(notice):
    return {
        "id": notice.id,
        "title": notice.title,
        "description": notice.content,
        "pinned": notice.is_pinned,
        "created_at": notice.created_at,
        "updated_at": notice.updated_at,
    }


def _text_field(label, max_length):
    """A trimmed, required text field whose errors name the field."""
    return serializers.CharField(
        max_length=max_length,
        error_messages={
            'required': f"{label} is required.",
            'blank': f"{label} can't be empty.",
            'null': f"{label} can't be empty.",
            'max_length': f"{label} can't be longer than {max_length} characters.",
            'invalid': f"{label} must be text.",
        },
    )


class NoticeWriteSerializer(serializers.Serializer):
    title = _text_field("Title", TITLE_MAX_LENGTH)
    description = _text_field("Description", DESCRIPTION_MAX_LENGTH)
    pinned = serializers.BooleanField(required=False, error_messages={'invalid': "pinned must be true or false."})


class NoticePinSerializer(serializers.Serializer):
    pinned = serializers.BooleanField(error_messages={
        'required': "pinned is required (true to pin, false to unpin).",
        'invalid': "pinned must be true or false.",
    })


def _pin(notice, pinned):
    """
    Pins (unpinning every other notice of the season) or unpins [notice] in one
    transaction. A concurrent pin that wins the race surfaces as a readable 409.
    """
    try:
        with transaction.atomic():
            if pinned:
                Notices.objects.filter(season_id=notice.season_id, is_pinned=True).exclude(pk=notice.pk).update(is_pinned=False)
            notice.is_pinned = pinned
            notice.save(update_fields=['is_pinned', 'updated_at'])
    except IntegrityError:
        raise NoticeConflict()


def _managed_notice(request, pk):
    """The notice [pk] of the caller's active season; the caller must manage the mess."""
    manager = get_managed_membership(request.user)
    notice = Notices.objects.filter(pk=pk, season=manager.season).first()
    if not notice:
        raise NotFound("Notice not found in the current season. It may have been deleted.")
    return notice


# ---------------------------------------------------------------------------
# User endpoints  (/api/v1/user/...)
# ---------------------------------------------------------------------------

class NoticeListView(APIView):
    """
    GET /api/v1/user/notices

    Every notice of the caller's active season, pinned first, then newest.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        membership = get_active_membership(request.user)
        if not membership:
            raise ValidationError({"detail": "You are not connected to an active mess."})
        notices = Notices.objects.filter(season=membership.season)
        return Response({"data": [notice_json(n) for n in notices]})


# ---------------------------------------------------------------------------
# Admin endpoints  (/api/v1/admin/...)  — manager / acting manager only
# ---------------------------------------------------------------------------

class AdminNoticeCreateView(APIView):
    """POST /api/v1/admin/notices  {title, description, pinned?}"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        manager = get_managed_membership(request.user)
        serializer = NoticeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Publish and pin together, so a failed pin doesn't leave a half-done notice.
        with transaction.atomic():
            notice = Notices.objects.create(season=manager.season, title=data['title'], content=data['description'])
            if data.get('pinned'):
                _pin(notice, True)
        return Response(notice_json(notice), status=status.HTTP_201_CREATED)


class AdminNoticeDetailView(APIView):
    """
    PATCH  /api/v1/admin/notices/<id>  {title?, description?}  (pin with /pin)
    DELETE /api/v1/admin/notices/<id>
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        notice = _managed_notice(request, pk)
        serializer = NoticeWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if 'title' not in data and 'description' not in data:
            raise ValidationError({"detail": "Send a title or description to update."})

        if 'title' in data:
            notice.title = data['title']
        if 'description' in data:
            notice.content = data['description']
        notice.save()
        return Response(notice_json(notice))

    def delete(self, request, pk):
        notice = _managed_notice(request, pk)
        notice.delete()
        return Response({"message": "Notice deleted."})


class AdminNoticePinView(APIView):
    """
    POST /api/v1/admin/notices/<id>/pin  {pinned: true|false}

    Pinning unpins any other notice of the season.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        notice = _managed_notice(request, pk)
        serializer = NoticePinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _pin(notice, serializer.validated_data['pinned'])
        return Response(notice_json(notice))

