"""
Season management APIs — manager / acting manager, under ``/api/v1/admin/seasons``.

A mess can run several seasons at once. Each user works in the season their
current membership points to and can switch between seasons any time (members
through ``/user/membership/switch``, the manager here). A new season copies the
members of a source season who haven't left; no other season ends. Ending a
season stops records dated after its end date; disabling one keeps its data but
nobody can work in it; deleting one removes all its meals, deposits and costs.

With auto-create on, ``run_auto_create_seasons`` (the ``create_scheduled_seasons``
command, run daily) creates a ``season-xyz`` on the chosen day of each month and
switches the members to it.
"""
from django.db.models import Count, Max, Min, Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from CostManagement.models import Cost
from DepositManagement.models import Deposit
from MealManagement.models import Meals
from MealManagement.utils import DATE_OUTPUT_FORMAT, parse_date_value
from .membership_views import get_managed_membership, membership_state
from .models import MessMemberShip, MessSeason
from .utils import get_active_membership, move_current_off, set_current_membership, start_season, usable_memberships


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def season_json(season, current_season_id):
    return {
        "id": season.id,
        "name": season.name,
        "start_date": season.start_date,
        "end_date": season.end_date,
        "status": season.status,
        "is_disabled": season.is_disabled,
        "member_count": getattr(season, 'member_count', None),
        "is_current": season.id == current_season_id,
    }


def seasons_with_counts(mess):
    """[mess]'s seasons, newest first, each with ``member_count`` (members who haven't left)."""
    return mess.seasons.annotate(
        member_count=Count('memberships', filter=Q(memberships__left_at__isnull=True)),
    ).order_by('-start_date', '-id')


def auto_create_json(mess):
    return {"enabled": mess.auto_create_season, "day": mess.auto_create_season_day}


def _fmt(value):
    return value.strftime(DATE_OUTPUT_FORMAT)


def _mess_season(manager, pk):
    """A season of the manager's mess (with its member count), or a readable 404."""
    season = seasons_with_counts(manager.mess).filter(pk=pk).first()
    if not season:
        raise NotFound("Season not found in this mess.")
    return season


def _clean_name(value, mess, exclude=None):
    """A non-empty season name no other season of [mess] uses (case-insensitive)."""
    name = str(value or '').strip()
    if not name:
        raise ValidationError({"name": "Season name is required."})
    if len(name) > 100:
        raise ValidationError({"name": "Season name can be at most 100 characters."})
    others = mess.seasons.filter(name__iexact=name)
    if exclude is not None:
        others = others.exclude(pk=exclude.pk)
    if others.exists():
        raise ValidationError({"name": f"This mess already has a season named {name}."})
    return name


def _record_bounds(season):
    """Dates of [season]'s first and last meal, deposit or cost (None, None when it has none)."""
    bounds = [
        queryset.aggregate(first=Min('date'), last=Max('date'))
        for queryset in (Meals.objects.filter(mess_season=season), Deposit.objects.filter(season=season), Cost.objects.filter(season=season))
    ]
    firsts = [b['first'] for b in bounds if b['first']]
    lasts = [b['last'] for b in bounds if b['last']]
    return (min(firsts) if firsts else None, max(lasts) if lasts else None)


def _check_dates(season, start_date, end_date):
    """[start_date]–[end_date] must be in order and still cover every record of [season]."""
    if end_date is not None and end_date < start_date:
        raise ValidationError({"end_date": "The end date can't be before the start date."})
    first, last = _record_bounds(season)
    if first and start_date > first:
        raise ValidationError({"start_date": f"{season.name} has records from {_fmt(first)}, so it can't start later than that."})
    if last and end_date is not None and end_date < last:
        raise ValidationError({"end_date": f"{season.name} has records up to {_fmt(last)}, so it can't end before that."})


# ---------------------------------------------------------------------------
# Admin endpoints  (/api/v1/admin/seasons...)
# ---------------------------------------------------------------------------

class AdminSeasonListView(APIView):
    """
    GET  /api/v1/admin/seasons
         {current_season_id, auto_create: {enabled, day}, seasons: [...]}
    POST /api/v1/admin/seasons  {name, start_date?, source_season_id?}

    Creating copies the members of ``source_season_id`` (default: the season
    the manager is working in) who haven't left; disabled members stay
    disabled. No season ends and nobody switches — use ``/switch`` for that.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        manager = get_managed_membership(request.user)
        return Response({
            "current_season_id": manager.season_id,
            "auto_create": auto_create_json(manager.mess),
            "seasons": [season_json(s, manager.season_id) for s in seasons_with_counts(manager.mess)],
        })

    def post(self, request):
        manager = get_managed_membership(request.user)
        mess = manager.mess
        name = _clean_name(request.data.get('name'), mess)
        start_date = parse_date_value(request.data.get('start_date'), 'start_date') or timezone.localdate()

        source = manager.season
        source_id = request.data.get('source_season_id')
        if source_id not in (None, ''):
            source = MessSeason.objects.filter(pk=source_id, mess=mess).first() if str(source_id).isdigit() else None
            if source is None:
                raise ValidationError({"source_season_id": "That season isn't in this mess."})

        season, carried = start_season(mess, name, start_date, source)
        # The manager is a member of every season, even one copied from a season they weren't in.
        _, added = MessMemberShip.objects.get_or_create(user=request.user, mess=mess, season=season, defaults={'status': 'active'})
        season = _mess_season(manager, season.pk)
        return Response(
            {"message": f"{name} created with {carried + int(added)} members.", "season": season_json(season, manager.season_id)},
            status=status.HTTP_201_CREATED,
        )


class AdminSeasonDetailView(APIView):
    """
    PATCH  /api/v1/admin/seasons/<id>  {name?, start_date?, end_date?}
           ``end_date: null`` reopens an ended season.
    DELETE /api/v1/admin/seasons/<id>
           Deletes the season with all its meals, deposits and costs. Members
           working in it move to another season of the mess.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        manager = get_managed_membership(request.user)
        season = _mess_season(manager, pk)
        data = request.data
        name = _clean_name(data['name'], manager.mess, exclude=season) if 'name' in data else season.name
        start_date = parse_date_value(data.get('start_date'), 'start_date') or season.start_date
        end_date = parse_date_value(data.get('end_date'), 'end_date') if 'end_date' in data else season.end_date
        _check_dates(season, start_date, end_date)

        season.name, season.start_date, season.end_date = name, start_date, end_date
        season.save(update_fields=['name', 'start_date', 'end_date', 'updated_at'])
        return Response({"message": f"{name} updated.", "season": season_json(season, manager.season_id)})

    def delete(self, request, pk):
        manager = get_managed_membership(request.user)
        season = _mess_season(manager, pk)
        if season.id == manager.season_id and not usable_memberships(request.user).filter(mess=manager.mess).exclude(season=season).exists():
            raise ValidationError({"detail": f"{season.name} is the only season you can work in. Create or enable another season before deleting it."})

        name = season.name
        move_current_off(season)
        season.delete()
        current = get_active_membership(request.user)
        return Response({
            "message": f"{name} and all its meals, deposits and costs were deleted.",
            "current_season_id": current.season_id if current else None,
        })


class AdminSeasonEndView(APIView):
    """
    POST /api/v1/admin/seasons/<id>/end

    Ends a running season today: nothing can be recorded after today, but it
    stays usable for viewing and fixing older records.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        manager = get_managed_membership(request.user)
        season = _mess_season(manager, pk)
        today = timezone.localdate()
        if season.end_date is not None:
            raise ValidationError({"detail": f"{season.name} already ended on {_fmt(season.end_date)}."})
        if season.start_date > today:
            raise ValidationError({"detail": f"{season.name} starts on {_fmt(season.start_date)}, so it can't end today."})
        _, last = _record_bounds(season)
        if last and last > today:
            raise ValidationError({"detail": f"{season.name} has records up to {_fmt(last)}, so it can't end today."})

        season.end_date = today
        season.save(update_fields=['end_date', 'updated_at'])
        return Response({
            "message": f"{season.name} ended. Nothing can be added after {_fmt(today)}.",
            "season": season_json(season, manager.season_id),
        })


class AdminSeasonStatusView(APIView):
    """
    POST /api/v1/admin/seasons/<id>/disable
    POST /api/v1/admin/seasons/<id>/enable

    A disabled season keeps its data, but nobody can work in it: members
    working in it move to another season of the mess. The season the manager
    is working in can't be disabled.
    """
    permission_classes = [permissions.IsAuthenticated]
    disable = True

    def post(self, request, pk):
        manager = get_managed_membership(request.user)
        season = _mess_season(manager, pk)
        if self.disable:
            if season.is_disabled:
                raise ValidationError({"detail": f"{season.name} is already disabled."})
            if season.id == manager.season_id:
                raise ValidationError({"detail": f"You're working in {season.name}. Switch to another season before disabling it."})
            season.is_disabled = True
            season.save(update_fields=['is_disabled', 'updated_at'])
            move_current_off(season)
            message = f"{season.name} is disabled. Members working in it moved to another season."
        else:
            if not season.is_disabled:
                raise ValidationError({"detail": f"{season.name} is already enabled."})
            season.is_disabled = False
            season.save(update_fields=['is_disabled', 'updated_at'])
            message = f"{season.name} is enabled."
        return Response({"message": message, "season": season_json(season, manager.season_id)})


class AdminSeasonSwitchView(APIView):
    """
    POST /api/v1/admin/seasons/<id>/switch

    Makes [id] the season the manager works in (their current membership);
    the app then reloads every screen for it. Ended seasons can be used too.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        manager = get_managed_membership(request.user)
        season = _mess_season(manager, pk)
        if season.is_disabled:
            raise ValidationError({"detail": f"{season.name} is disabled. Enable it before switching to it."})
        if season.id == manager.season_id:
            raise ValidationError({"detail": f"You're already working in {season.name}."})

        # The manager is a member of every season; add them if this one predates them.
        membership, _ = MessMemberShip.objects.select_related('mess', 'season').get_or_create(
            user=request.user, mess=manager.mess, season=season, defaults={'status': 'active'},
        )
        state = membership_state(membership)
        if state != 'active':
            raise ValidationError({"detail": f"Your membership in {season.name} is {state}, so you can't work in it."})
        set_current_membership(request.user, membership)
        return Response({"message": f"Now working in {season.name}.", "current_season_id": season.id})


class AdminSeasonAutoCreateView(APIView):
    """
    GET /api/v1/admin/seasons/auto-create  -> {enabled, day}
    PUT /api/v1/admin/seasons/auto-create  {enabled?, day?}

    ``day`` is 1–28 (every month has it) or 0 for the month's last day. On
    that day a new ``season-xyz`` is created from the active season and the
    members working in it switch to the new one.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        manager = get_managed_membership(request.user)
        return Response(auto_create_json(manager.mess))

    def put(self, request):
        manager = get_managed_membership(request.user)
        mess = manager.mess
        fields = []
        if 'enabled' in request.data:
            enabled = request.data['enabled']
            if not isinstance(enabled, bool):
                raise ValidationError({"enabled": "enabled must be true or false."})
            mess.auto_create_season = enabled
            fields.append('auto_create_season')
        if 'day' in request.data:
            day = request.data['day']
            if isinstance(day, bool) or not isinstance(day, int) or not 0 <= day <= 28:
                raise ValidationError({"day": "Choose a day from 1 to 28, or 0 for the last day of the month."})
            mess.auto_create_season_day = day
            fields.append('auto_create_season_day')
        if not fields:
            raise ValidationError({"detail": "Send enabled and/or day to change."})
        mess.save(update_fields=[*fields, 'updated_at'])

        if not mess.auto_create_season:
            message = "Auto-create is off."
        else:
            when = "on the last day of every month" if mess.auto_create_season_day == 0 else f"on day {mess.auto_create_season_day} of every month"
            message = f"Auto-create is on: a new season starts {when}."
        return Response({"message": message, "auto_create": auto_create_json(mess)})
