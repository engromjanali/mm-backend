from django.utils import timezone
from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from AuthManagement.models import Notification
from AuthManagement.push import notice_notification_content
from MessManagement.models import MessMemberShip, Notices
from MessManagement.utils import _season_access, get_current_access


def save_notice_notifications(notice, season):
    content = notice_notification_content(notice.title)
    recipients = MessMemberShip.objects.filter(
        season=season, status='active', left_at__isnull=True, user__is_active=True,
        user__current_season_id=season.id,
    ).values_list('user_id', flat=True)
    Notification.objects.bulk_create([
        Notification(user_id=user_id, season=season, notice_id=notice.id,
                     title=content['title'], description=content['body'])
        for user_id in recipients
    ], ignore_conflicts=True, batch_size=500)


def notification_json(item):
    return {'id': item.id, 'title': item.title, 'description': item.description,
            'season_id': item.season_id, 'season_name': item.season.name if item.season else None,
            'created_at': item.created_at, 'read': item.read_at is not None}


class NotificationListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.query_params.get('unread_only') == 'true':
            return Response({'has_unread': Notification.objects.filter(user=request.user, read_at__isnull=True).exists()})
        items = Notification.objects.filter(user=request.user).select_related('season')
        notice_id = request.query_params.get('notice_id')
        if notice_id:
            if not notice_id.isdigit():
                raise NotFound()
            items = items.filter(notice_id=notice_id)
        before = request.query_params.get('before')
        if before:
            if not before.isdigit():
                raise NotFound()
            items = items.filter(id__lt=before)
        page = list(items[:31])
        return Response({'data': [notification_json(item) for item in page[:30]],
                         'next': page[29].id if len(page) > 30 else None})


class NotificationOpenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        item = Notification.objects.filter(pk=pk, user=request.user).select_related('season').first()
        if not item:
            raise NotFound()
        if item.read_at is None:
            item.read_at = timezone.now()
            item.save(update_fields=['read_at'])
        result = notification_json(item)
        target = _season_access(request.user, item.season_id)
        current = get_current_access(request.user)
        if not target:
            result['status'] = 'unavailable'
        elif not current or current.season_id != target.season_id:
            result['status'] = 'change_season'
        elif not Notices.objects.filter(pk=item.notice_id, mess_id=target.mess_id).exists():
            result['status'] = 'unavailable'
        else:
            result.update(status='ready', route=f'/notices/{item.notice_id}')
        return Response(result)
