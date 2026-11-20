"""
Poll APIs for members and managers.

A poll is a dated question in one season. Every member with an active
membership in that season can vote once and change their choice until the
poll closes. Managers and acting managers create, edit, close and cancel
polls from the app's Add Meal screen or the Polls screen.

User endpoints live under ``/api/v1/user/`` and manager endpoints under
``/api/v1/admin/``.
"""
from django.db import transaction
from django.db.models import Count, Prefetch
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from MealManagement.utils import parse_date_value
from MessManagement.membership_views import MANAGER_ROLES, get_managed_membership
from MessManagement.models import MessMemberShip
from MessManagement.utils import get_current_access
from .models import Poll, PollOption, PollVote
from .serializers import PollCloseSerializer, PollVoteSerializer, PollWriteSerializer

PAGE_SIZE = 20


class PollClosed(APIException):
    """409 — the poll stopped accepting votes."""
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This poll is closed and no longer accepts votes."
    default_code = 'poll_closed'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _options_prefetch():
    return Prefetch('options', queryset=PollOption.objects.order_by('position', 'id'))


def _active_membership(context):
    """The caller's real, active membership in the poll's season, or None."""
    membership = context.membership if context else None
    if membership is None or membership.status != 'active' or membership.left_at is not None:
        return None
    return membership


def _paginate(polls, request):
    try:
        page = int(request.query_params.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        page = 1
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    next_page = page + 1 if len(polls) > end else None
    return polls[start:end], next_page


def _ordered(polls):
    """
    Nearest date first for open polls, then past/closed ones newest first.
    This is the app's "poll sorted by nearest date" rule.
    """
    open_polls = [poll for poll in polls if not poll.is_closed]
    closed_polls = [poll for poll in polls if poll.is_closed]
    open_polls.sort(key=lambda poll: (poll.poll_date, poll.closes_at, poll.id))
    closed_polls.sort(key=lambda poll: (poll.poll_date, poll.closes_at, poll.id), reverse=True)
    return open_polls + closed_polls


def _payloads(polls, context, can_manage):
    """Serialize a page of polls with batched vote counts (no N+1 queries)."""
    poll_ids = [poll.id for poll in polls]
    if not poll_ids:
        return []

    counts = dict(
        PollOption.objects.filter(poll_id__in=poll_ids)
        .annotate(vote_count=Count('votes'))
        .values_list('id', 'vote_count')
    )
    voter_counts = dict(
        PollVote.objects.filter(poll_id__in=poll_ids)
        .values('poll_id')
        .annotate(total=Count('membership', distinct=True))
        .values_list('poll_id', 'total')
    )
    membership = _active_membership(context)
    my_votes = {}
    if membership is not None:
        for poll_id, option_id in PollVote.objects.filter(
            poll_id__in=poll_ids, membership=membership
        ).values_list('poll_id', 'option_id'):
            my_votes.setdefault(poll_id, set()).add(option_id)

    eligible = 0
    if context is not None:
        eligible = MessMemberShip.objects.filter(
            season=context.season, status='active', left_at__isnull=True
        ).count()

    return [
        _payload(
            poll,
            counts,
            voter_counts,
            my_votes.get(poll.id, set()),
            eligible,
            membership,
            context,
            can_manage,
        )
        for poll in polls
    ]


def _payload(poll, counts, voter_counts, my_option_ids, eligible, membership, context, can_manage):
    closed = poll.is_closed
    has_voted = bool(my_option_ids)
    results_visible = (
        can_manage
        or poll.results_visibility == 'always'
        or (poll.results_visibility == 'after_vote' and has_voted)
        or (poll.results_visibility == 'after_close' and closed)
    )
    can_vote = (
        not closed
        and membership is not None
        and context is not None
        and context.season_id == poll.season_id
    )
    return {
        'id': poll.id,
        'season_id': poll.season_id,
        'created_by_id': poll.created_by_id,
        'title': poll.title,
        'description': poll.description,
        'poll_date': poll.poll_date.isoformat(),
        'closes_at': poll.closes_at,
        'status': poll.status,
        'allow_multiple': poll.allow_multiple,
        'max_choices': poll.max_choices,
        'is_anonymous': poll.is_anonymous,
        'results_visibility': poll.results_visibility,
        'options': [
            {
                'id': option.id,
                'text': option.text,
                'vote_count': counts.get(option.id, 0) if results_visible else None,
            }
            for option in poll.options.all()
        ],
        'my_option_ids': sorted(my_option_ids),
        'has_voted': has_voted,
        'total_votes': voter_counts.get(poll.id, 0),
        'eligible_member_count': eligible,
        'can_vote': can_vote,
        'results_visible': results_visible,
        'can_manage': can_manage,
        'has_votes': voter_counts.get(poll.id, 0) > 0,
        'can_edit_options': can_manage and voter_counts.get(poll.id, 0) == 0,
    }


def _poll_payload(poll, context, can_manage):
    return _payloads([poll], context, can_manage)[0]


def _visible_poll(user, pk):
    """A non-cancelled poll in the caller's current season."""
    context = get_current_access(user)
    if not context:
        raise PermissionDenied("You are not connected to an active mess.")
    poll = (
        Poll.objects.select_related('season__mess', 'created_by')
        .prefetch_related(_options_prefetch())
        .filter(pk=pk, season=context.season, cancelled_at__isnull=True)
        .first()
    )
    if poll is None:
        raise NotFound("Poll not found in your current season.")
    return context, poll


def _managed_poll(user, pk):
    """A poll (including cancelled) of the manager's current season."""
    manager = get_managed_membership(user)
    poll = (
        Poll.objects.select_related('season__mess', 'created_by')
        .prefetch_related(_options_prefetch())
        .filter(pk=pk, season=manager.season)
        .first()
    )
    if poll is None:
        raise NotFound("Poll not found in your current season.")
    return manager, poll


def _can_manage(context):
    return context is not None and context.role in MANAGER_ROLES


# ---------------------------------------------------------------------------
# User endpoints  (/api/v1/user/polls)
# ---------------------------------------------------------------------------

class PollListView(APIView):
    """
    GET /api/v1/user/polls?page=1&include_past=true

    Every poll of the caller's current season, nearest open date first. Cancelled
    polls are hidden from members.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        context = get_current_access(request.user)
        if not context:
            raise PermissionDenied("You are not connected to an active mess.")
        can_manage = _can_manage(context)
        polls = (
            Poll.objects.select_related('season__mess', 'created_by')
            .prefetch_related(_options_prefetch())
            .filter(season=context.season, cancelled_at__isnull=True)
        )
        if request.query_params.get('include_past', 'true').lower() == 'false':
            polls = polls.filter(closes_at__gt=timezone.now(), manually_closed_at__isnull=True)

        page, next_page = _paginate(_ordered(list(polls)), request)
        return Response({
            'mess_id': context.mess_id,
            'season_id': context.season_id,
            'can_manage': can_manage,
            'next_page': next_page,
            'data': _payloads(page, context, can_manage),
        })


class PollDetailView(APIView):
    """GET /api/v1/user/polls/<id>"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        context, poll = _visible_poll(request.user, pk)
        return Response(_poll_payload(poll, context, _can_manage(context)))


class PollVoteView(APIView):
    """
    POST   /api/v1/user/polls/<id>/vote  {"option_ids": [1]}
    DELETE /api/v1/user/polls/<id>/vote  (withdraw while open)
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        serializer = PollVoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            poll = (
                Poll.objects.select_for_update()
                .select_related('season__mess')
                .filter(pk=pk, cancelled_at__isnull=True)
                .first()
            )
            if poll is None:
                raise NotFound("Poll not found.")
            context = get_current_access(request.user)
            if not context or context.season_id != poll.season_id:
                raise PermissionDenied("This poll belongs to one of your other seasons. Switch to that season and try again.")
            membership = _active_membership(context)
            if membership is None:
                raise PermissionDenied("Only active members of this season can vote.")
            if poll.is_closed:
                raise PollClosed()

            option_ids = serializer.validated_data['option_ids']
            valid_ids = set(poll.options.values_list('id', flat=True))
            unknown = [option_id for option_id in option_ids if option_id not in valid_ids]
            if unknown:
                raise ValidationError({'option_ids': 'One or more options do not belong to this poll.'})
            limit = poll.max_choices if poll.allow_multiple else 1
            if len(option_ids) > limit:
                raise ValidationError({'option_ids': f"Choose at most {limit} option{'s' if limit != 1 else ''}."})

            PollVote.objects.filter(poll=poll, membership=membership).delete()
            PollVote.objects.bulk_create([
                PollVote(poll=poll, option_id=option_id, membership=membership)
                for option_id in option_ids
            ])
        return Response(_poll_payload(poll, context, _can_manage(context)))

    def delete(self, request, pk):
        with transaction.atomic():
            poll = (
                Poll.objects.select_for_update()
                .select_related('season__mess')
                .filter(pk=pk, cancelled_at__isnull=True)
                .first()
            )
            if poll is None:
                raise NotFound("Poll not found.")
            context = get_current_access(request.user)
            if not context or context.season_id != poll.season_id:
                raise PermissionDenied("This poll belongs to one of your other seasons. Switch to that season and try again.")
            membership = _active_membership(context)
            if membership is None:
                raise PermissionDenied("Only active members of this season can vote.")
            if poll.is_closed:
                raise PollClosed()
            PollVote.objects.filter(poll=poll, membership=membership).delete()
        return Response(_poll_payload(poll, context, _can_manage(context)))


# ---------------------------------------------------------------------------
# Admin endpoints  (/api/v1/admin/polls)
# ---------------------------------------------------------------------------

class AdminPollListCreateView(APIView):
    """
    GET  /api/v1/admin/polls?poll_date=YYYY-MM-DD&include_cancelled=true
    POST /api/v1/admin/polls
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        manager = get_managed_membership(request.user)
        polls = (
            Poll.objects.select_related('season__mess', 'created_by')
            .prefetch_related(_options_prefetch())
            .filter(season=manager.season)
        )
        if request.query_params.get('include_cancelled', 'false').lower() != 'true':
            polls = polls.filter(cancelled_at__isnull=True)
        poll_date = request.query_params.get('poll_date')
        if poll_date:
            polls = polls.filter(poll_date=poll_date)
        page, next_page = _paginate(_ordered(list(polls)), request)
        return Response({
            'mess_id': manager.mess_id,
            'season_id': manager.season_id,
            'can_manage': True,
            'next_page': next_page,
            'data': _payloads(page, manager, True),
        })

    def post(self, request):
        manager = get_managed_membership(request.user)
        serializer = PollWriteSerializer(data=request.data, context={'season': manager.season})
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        options = data.pop('options')
        data.pop('season', None)
        max_choices = data.pop('max_choices', 1)

        with transaction.atomic():
            poll = Poll.objects.create(
                season=manager.season,
                created_by=request.user,
                max_choices=max_choices,
                **data,
            )
            PollOption.objects.bulk_create([
                PollOption(poll=poll, text=text, position=index)
                for index, text in enumerate(options)
            ])
        poll = Poll.objects.select_related('season__mess', 'created_by').prefetch_related(_options_prefetch()).get(pk=poll.pk)
        return Response(_poll_payload(poll, manager, True), status=status.HTTP_201_CREATED)


class AdminPollDetailView(APIView):
    """PATCH /api/v1/admin/polls/<id>, DELETE /api/v1/admin/polls/<id>"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        manager, poll = _managed_poll(request.user, pk)
        if poll.is_cancelled:
            raise ValidationError({'detail': 'A cancelled poll cannot be edited.'})
        requested_date = request.data.get('poll_date')
        if requested_date:
            # The date is the poll's identity in the meal screen; moving it would
            # hide it from where members expect it.
            parsed = parse_date_value(requested_date, 'poll_date')
            if parsed != poll.poll_date:
                raise ValidationError({'poll_date': 'The poll date cannot be changed. Create a new poll instead.'})

        has_options_change = any(key in request.data for key in ('options', 'allow_multiple', 'max_choices'))
        if poll.votes.exists() and has_options_change:
            raise ValidationError({'detail': 'Options cannot be changed after members have voted.'})

        serializer = PollWriteSerializer(poll, data=request.data, partial=True, context={'season': manager.season})
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        options = data.pop('options', None)
        data.pop('season', None)
        max_choices = data.pop('max_choices', poll.max_choices)

        with transaction.atomic():
            for field, value in data.items():
                setattr(poll, field, value)
            poll.max_choices = max_choices
            poll.save()
            if options is not None:
                poll.options.all().delete()
                PollOption.objects.bulk_create([
                    PollOption(poll=poll, text=text, position=index)
                    for index, text in enumerate(options)
                ])
        poll = Poll.objects.select_related('season__mess', 'created_by').prefetch_related(_options_prefetch()).get(pk=poll.pk)
        return Response(_poll_payload(poll, manager, True))

    def delete(self, request, pk):
        manager, poll = _managed_poll(request.user, pk)
        if poll.votes.exists():
            now = timezone.now()
            poll.cancelled_at = now
            poll.manually_closed_at = poll.manually_closed_at or now
            poll.save(update_fields=['cancelled_at', 'manually_closed_at', 'updated_at'])
            return Response({'id': poll.id, 'status': 'cancelled', 'message': 'Poll cancelled. Existing votes are kept.'})
        poll.delete()
        return Response({'id': pk, 'status': 'deleted', 'message': 'Poll deleted.'})


class AdminPollCloseView(APIView):
    """POST /api/v1/admin/polls/<id>/close  {"closed": true|false}"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        manager, poll = _managed_poll(request.user, pk)
        if poll.is_cancelled:
            raise ValidationError({'detail': 'A cancelled poll cannot be opened or closed.'})
        serializer = PollCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        closed = serializer.validated_data['closed']
        poll.manually_closed_at = timezone.now() if closed else None
        poll.save(update_fields=['manually_closed_at', 'updated_at'])
        poll = Poll.objects.select_related('season__mess', 'created_by').prefetch_related(_options_prefetch()).get(pk=poll.pk)
        return Response(_poll_payload(poll, manager, True))


class AdminPollResultsView(APIView):
    """GET /api/v1/admin/polls/<id>/results — counts and participation."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        manager, poll = _managed_poll(request.user, pk)
        options = list(poll.options.annotate(vote_count=Count('votes')))
        votes = PollVote.objects.filter(poll=poll).select_related('membership__user')
        participant_ids = set(votes.values_list('membership_id', flat=True))
        voters = []
        if not poll.is_anonymous:
            seen = set()
            for vote in votes:
                if vote.membership_id in seen:
                    continue
                seen.add(vote.membership_id)
                voters.append({
                    'membership_id': vote.membership_id,
                    'name': vote.membership.user.full_name,
                    'option_ids': sorted(
                        PollVote.objects.filter(poll=poll, membership_id=vote.membership_id)
                        .values_list('option_id', flat=True)
                    ),
                })
        eligible = MessMemberShip.objects.filter(
            season=poll.season, status='active', left_at__isnull=True
        ).count()
        return Response({
            'poll_id': poll.id,
            'status': poll.status,
            'total_votes': len(participant_ids),
            'eligible_member_count': eligible,
            'is_anonymous': poll.is_anonymous,
            'options': [
                {'id': option.id, 'text': option.text, 'vote_count': option.vote_count}
                for option in options
            ],
            'voters': voters,
        })
