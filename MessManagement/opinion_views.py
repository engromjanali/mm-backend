from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from MessManagement.models import AnonymousOpinion, Mess, MessMemberShip, OpinionPeriod
from MessManagement.utils import get_current_access


class OpinionPagination(PageNumberPagination):
    page_size = 10


class OpinionMessagePagination(PageNumberPagination):
    page_size = 20


class OpinionPeriodSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120)
    details = serializers.CharField(max_length=1000)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    accepting_messages = serializers.BooleanField(required=False)
    allow_named_opinions = serializers.BooleanField(required=False)
    visibility = serializers.ChoiceField(choices=['realtime', 'after_publish'], required=False)


class OpinionMessageSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000)
    anonymous = serializers.BooleanField(required=False, default=True)


def _read_mess(request):
    mess_id = request.query_params.get('mess_id')
    memberships = MessMemberShip.objects.filter(user=request.user).select_related('mess')
    if mess_id is not None:
        try:
            membership = memberships.filter(mess_id=int(mess_id)).first()
        except (TypeError, ValueError):
            raise ValidationError({'mess_id': 'mess_id must be a number.'})
    else:
        context = get_current_access(request.user)
        membership = context.membership if context else memberships.order_by('-season__start_date', '-id').first()
        mess = context.mess if context else membership.mess if membership else None
    if mess_id is not None:
        mess = membership.mess if membership else Mess.objects.filter(pk=mess_id, manager=request.user).first() or Mess.objects.filter(pk=mess_id, acting_manager=request.user).first()
    if not mess:
        raise PermissionDenied('You must belong to a season of this mess to view opinions.')
    return mess


def _can_manage(user, mess):
    return mess.role_of(user.id) in ('manager', 'acting_manager')


def _managed_mess(user, mess_id=None):
    if mess_id is None:
        context = get_current_access(user)
        mess = context.mess if context else None
    else:
        mess = Mess.objects.filter(pk=mess_id).first()
    if mess is None or not _can_manage(user, mess):
        raise PermissionDenied('Only the manager or acting manager of this mess can do this.')
    return mess


def _messages(period, can_manage):
    messages = AnonymousOpinion.objects.filter(period=period)
    if not can_manage and period.visibility != 'realtime':
        messages = messages.none()
    return messages


def _message_json(opinion):
    return {'id': opinion.id, 'period_id': opinion.period_id, 'message': opinion.message, 'author_name': opinion.author_name or None, 'is_anonymous': not bool(opinion.author_name), 'created_at': opinion.created_at, 'is_published': opinion.is_published}


def _period_json(period, writable_season_id):
    today = timezone.localdate()
    can_write = period.season_id == writable_season_id and period.accepting_messages and period.start_date <= today <= period.end_date
    return {
        'id': period.id, 'mess_id': period.season.mess_id, 'season_id': period.season_id, 'season_name': period.season.name,
        'title': period.title, 'details': period.details, 'start_date': period.start_date, 'end_date': period.end_date,
        'accepting_messages': period.accepting_messages, 'allow_named_opinions': period.allow_named_opinions, 'visibility': period.visibility, 'can_write': can_write,
        'opinions': [_message_json(opinion) for opinion in period.visible_opinions],
        'opinion_count': period.visible_count, 'has_more_opinions': period.visible_count > len(period.visible_opinions),
    }


class OpinionPeriodListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        mess = _read_mess(request)
        can_manage = _can_manage(request.user, mess)
        context = get_current_access(request.user)
        current_season = context.season if context and context.mess_id == mess.id else None
        writable_season_id = context.season_id if context and context.mess_id == mess.id and context.membership and context.membership.status == 'active' and context.membership.left_at is None else None
        visible = Q() if can_manage else Q(visibility='realtime')
        messages = AnonymousOpinion.objects.all()
        if not can_manage:
            messages = messages.filter(period__visibility='realtime')
        periods = OpinionPeriod.objects.filter(season__mess=mess).select_related('season').annotate(visible_count=Count('opinions', filter=visible)).prefetch_related(
            Prefetch('opinions', queryset=messages.order_by('-created_at', '-id')[:OpinionMessagePagination.page_size], to_attr='visible_opinions'),
        ).order_by('-created_at', '-id')
        pagination = OpinionPagination()
        page = pagination.paginate_queryset(periods, request)
        return Response({
            'mess_id': mess.id, 'can_manage': can_manage, 'can_create': can_manage and current_season is not None,
            'current_season_id': current_season.id if current_season else None,
            'next_page': pagination.page.next_page_number() if pagination.page.has_next() else None,
            'data': [_period_json(period, writable_season_id) for period in page],
        })


class OpinionMessagesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        mess = _read_mess(request)
        period = OpinionPeriod.objects.filter(pk=pk, season__mess=mess).first()
        if period is None:
            raise NotFound('Opinion period not found in this mess.')
        pagination = OpinionMessagePagination()
        page = pagination.paginate_queryset(_messages(period, _can_manage(request.user, mess)), request)
        return Response({'data': [_message_json(opinion) for opinion in page], 'next_page': pagination.page.next_page_number() if pagination.page.has_next() else None})

    def post(self, request, pk):
        serializer = OpinionMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            # Serialize submissions and publishing against the same period.
            period = OpinionPeriod.objects.select_for_update().select_related('season__mess').filter(pk=pk).first()
            if period is None:
                raise NotFound('Opinion period not found.')
            user = type(request.user).objects.select_for_update().get(pk=request.user.pk)
            context = get_current_access(user)
            membership = MessMemberShip.objects.select_for_update().filter(pk=context.membership_id, user=user, season_id=period.season_id, status='active', left_at__isnull=True, season__is_disabled=False).first() if context and context.season_id == period.season_id and context.membership_id else None
            if membership is None:
                raise PermissionDenied('Only active members of their current season can submit opinions.')
            today = timezone.localdate()
            if not period.accepting_messages or not period.start_date <= today <= period.end_date:
                raise ValidationError({'detail': 'This opinion period is not accepting messages.'})
            anonymous = serializer.validated_data['anonymous']
            if not anonymous and not period.allow_named_opinions:
                raise ValidationError({'anonymous': 'Named opinions are not enabled for this period.'})
            AnonymousOpinion.objects.create(period=period, message=serializer.validated_data['message'], author_name='' if anonymous else membership.user.full_name)
        return Response({'message': 'Opinion submitted.'}, status=status.HTTP_201_CREATED)


class AdminOpinionPeriodCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        mess = _managed_mess(request.user)
        serializer = OpinionPeriodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data['end_date'] < data['start_date']:
            raise ValidationError({'end_date': 'End date cannot be before start date.'})
        context = get_current_access(request.user)
        if context is None or context.mess_id != mess.id:
            raise ValidationError({'detail': 'Select a season of this mess before opening an opinion period.'})
        season = context.season
        period = OpinionPeriod.objects.create(season=season, **data)
        return Response({'id': period.id}, status=status.HTTP_201_CREATED)


class AdminOpinionPeriodDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        with transaction.atomic():
            period = OpinionPeriod.objects.select_for_update().select_related('season').filter(pk=pk).first()
            if period is None:
                raise NotFound('Opinion period not found.')
            _managed_mess(request.user, period.season.mess_id)
            if 'season' in request.data or 'season_id' in request.data:
                raise ValidationError({'season_id': 'The season of an opinion period cannot be changed.'})
            serializer = OpinionPeriodSerializer(data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            if data.get('end_date', period.end_date) < data.get('start_date', period.start_date):
                raise ValidationError({'end_date': 'End date cannot be before start date.'})
            for field, value in data.items():
                setattr(period, field, value)
            period.save()
        return Response({'id': period.id})


class AdminOpinionPublishView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        with transaction.atomic():
            period = OpinionPeriod.objects.select_for_update().select_related('season').filter(pk=pk).first()
            if period is None:
                raise NotFound('Opinion period not found.')
            _managed_mess(request.user, period.season.mess_id)
            count = period.opinions.filter(is_published=False).update(is_published=True)
            period.visibility = 'realtime'
            period.save(update_fields=['visibility', 'updated_at'])
        return Response({'published_count': count})
