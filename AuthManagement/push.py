import base64
import binascii
import json
import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from django.db import transaction
from django.db.models import F, Q
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from AuthManagement.models import PushDevice
from MessManagement.models import MessMemberShip, MessSeason

logger = logging.getLogger(__name__)


def firebase_messaging():
    import firebase_admin
    from firebase_admin import credentials, messaging
    try:
        firebase_admin.get_app()
    except ValueError:
        service_account_json = settings.FIREBASE_SERVICE_ACCOUNT_JSON
        if service_account_json:
            try:
                value = service_account_json.strip()
                if not value.startswith(('{', '"')):
                    value = base64.b64decode(value, validate=True).decode('utf-8')
                service_account = json.loads(value)
                if isinstance(service_account, str):
                    service_account = json.loads(service_account)
                if not isinstance(service_account, dict):
                    raise ValueError
            except (ValueError, TypeError, binascii.Error):
                raise ImproperlyConfigured('FIREBASE_SERVICE_ACCOUNT_JSON must contain valid service-account JSON, a JSON-encoded string, or base64-encoded JSON.') from None
            firebase_admin.initialize_app(credentials.Certificate(service_account))
        else:
            firebase_admin.initialize_app()
    return messaging


def season_topic(season_id):
    return f'topic_seasonId_{season_id}'


def mess_topic(mess_id):
    return f'topic_messId_{mess_id}'


def eligible_topic_sets(user_ids):
    memberships = MessMemberShip.objects.filter(
        user_id__in=user_ids, user__is_active=True, status='active', left_at__isnull=True,
        season__is_disabled=False, season_id=F('user__current_season_id'),
    ).values_list('user_id', 'season_id', 'mess_id')
    return {user_id: {season_topic(season_id), mess_topic(mess_id)} for user_id, season_id, mess_id in memberships}


def eligible_topics(user_id):
    return eligible_topic_sets([user_id]).get(user_id, set())


class PushSubscriptionUnavailable(APIException):
    status_code = 503
    default_detail = 'Push subscription is temporarily unavailable.'
    default_code = 'push_subscription_unavailable'


def check_topic_result(device, result, operation):
    if not result.failure_count:
        return True
    reasons = {error.reason for error in result.errors}
    if reasons and reasons.issubset({'UNREGISTERED', 'registration-token-not-registered', 'invalid-registration-token'}):
        device.delete()
        return False
    # Never expose arbitrary provider messages: they may contain device IDs.
    known = {'PERMISSION_DENIED', 'UNAUTHENTICATED', 'INVALID_ARGUMENT', 'NOT_FOUND', 'RESOURCE_EXHAUSTED', 'INTERNAL', 'UNAVAILABLE', 'DEADLINE_EXCEEDED'}
    reason = next(iter(sorted(reasons & known)), 'UNKNOWN_ERROR')
    logger.warning('Push topic %s failed: %s', operation, reason)
    raise PushSubscriptionUnavailable(f'Push subscription unavailable ({reason}).')


def update_topics(device, topics):
    old = set(device.topics)
    if old == topics:
        return True
    messaging = firebase_messaging()
    for topic in old - topics:
        result = messaging.unsubscribe_from_topic([device.token], topic)
        if not check_topic_result(device, result, 'unsubscribe'):
            return False
    for topic in topics - old:
        result = messaging.subscribe_to_topic([device.token], topic)
        if not check_topic_result(device, result, 'subscribe'):
            return False
    device.topics = sorted(topics)
    device.save(update_fields=['topics', 'updated_at'])
    return True


class PushDeviceSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512, trim_whitespace=True)


class PushDeviceView(APIView):
    def post(self, request):
        serializer = PushDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            device, _ = PushDevice.objects.select_for_update().get_or_create(
                token=serializer.validated_data['token'], defaults={'user': request.user},
            )
            # A shared device must lose the previous account's subscriptions first.
            if device.user_id != request.user.id:
                if not update_topics(device, set()):
                    return Response({'detail': 'Device registration expired.'}, status=400)
                device.user = request.user
                device.save(update_fields=['user'])
            if not update_topics(device, eligible_topics(request.user.id)):
                return Response({'detail': 'Device registration expired.'}, status=400)
        return Response({'topics': device.topics})

    def delete(self, request):
        serializer = PushDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            device = PushDevice.objects.select_for_update().filter(
                user=request.user, token=serializer.validated_data['token'],
            ).first()
            if device and update_topics(device, set()):
                device.delete()
        return Response(status=204)


def send_notice_notification(notice_id, season_id, notice_title):
    # Never roll back a published notice because the push provider is unavailable.
    try:
        season = MessSeason.objects.filter(pk=season_id, is_disabled=False).first()
        if not season:
            return
        topic = season_topic(season_id)
        eligible_users = set(MessMemberShip.objects.filter(
            season=season, status='active', left_at__isnull=True, user__is_active=True, user__current_season_id=season.id,
        ).values_list('user_id', flat=True))
        # Reconcile even when a member's app is closed. Fail closed: if removal
        # fails, do not send a notice to a topic containing a former member.
        with transaction.atomic():
            devices = list(PushDevice.objects.select_for_update().filter(
                Q(user_id__in=eligible_users) | Q(topics__icontains=f'"{topic}"'),
            ).order_by('pk'))
            current_topics = eligible_topic_sets({device.user_id for device in devices})
            for device in devices:
                update_topics(device, current_topics.get(device.user_id, set()))
            messaging = firebase_messaging()
            messaging.send(messaging.Message(
                topic=topic,
                notification=messaging.Notification(title='New Notice', body=(notice_title.encode('utf-8')[:3000].decode('utf-8', errors='ignore') + '…') if len(notice_title.encode('utf-8')) > 3000 else notice_title),
                data={'type': 'notice', 'notice_id': str(notice_id), 'season_id': str(season_id)},
            ))
    except Exception:
        logger.warning('Notice %s push delivery failed', notice_id)
