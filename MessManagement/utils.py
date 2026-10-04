import secrets
import string
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, Subquery, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from AuthManagement.models import User
from .models import INVITE_AND_REQUEST_LIFETIME, Mess, MessMemberShip, MessMemberShipInvitation, MessMemberShipRequest, MessSeason


def get_verified_membership_and_season(request, require_write=False):
    """
    Extracts Membership ID and Session ID from request headers,
    verifies active membership for request.user and valid season for the mess,
    and enforces role permissions for write operations (Manager or Acting Manager).
    """
    # 1. Extract Membership ID & Session ID headers (supporting multiple casing conventions)
    membership_id = (
        request.headers.get('Membership-ID') or
        request.headers.get('membership_id') or
        request.headers.get('membership-id') or
        request.headers.get('X-Membership-ID') or
        request.META.get('HTTP_MEMBERSHIP_ID')
    )
    session_id = (
        request.headers.get('Session-ID') or
        request.headers.get('session_id') or
        request.headers.get('session-id') or
        request.headers.get('X-Session-ID') or
        request.META.get('HTTP_SESSION_ID')
    )

    if not membership_id or not session_id:
        raise PermissionDenied("Membership-ID and Session-ID headers are required.")

    try:
        membership_id = int(membership_id)
        session_id = int(session_id)
    except (ValueError, TypeError):
        raise PermissionDenied("Membership-ID and Session-ID headers must be valid integers.")

    # 2. Verify Membership for request.user
    try:
        membership = MessMemberShip.objects.get(id=membership_id, user=request.user, status='active')
    except MessMemberShip.DoesNotExist:
        raise PermissionDenied("Invalid or inactive membership for this user.")

    # 3. Verify Season and associate with mess
    try:
        season = MessSeason.objects.get(id=session_id, mess=membership.mess)
    except MessSeason.DoesNotExist:
        raise PermissionDenied("Invalid session ID or session does not belong to your mess.")

    # 4. Enforce Manager / Acting Manager role check for write operations
    if require_write and membership.role not in ['manager', 'acting_manager']:
        raise PermissionDenied("Only Manager or Acting Manager can perform this write operation.")

    return membership, season


def usable_memberships(user):
    """Memberships the user can work in: not left, not disabled by a manager, in a season that isn't disabled."""
    return MessMemberShip.objects.select_related('mess', 'season').filter(user=user, status='active', left_at__isnull=True, season__is_disabled=False)


def get_active_membership(user):
    """
    The user's current membership, or ``None``.

    A user may belong to several messes (one membership per season). The
    current one is the membership they chose (``User.current_membership``)
    while it's still usable; otherwise their newest usable membership, which
    is then saved as current so the choice stays stable.
    """
    memberships = usable_memberships(user)
    # Read the saved choice from the database, not the (possibly stale) user object.
    saved = type(user).objects.filter(pk=user.pk).values('current_membership')[:1]
    current = memberships.filter(pk=Subquery(saved)).first()
    if current:
        user.current_membership_id = current.id
        return current
    fallback = memberships.order_by('-season__start_date', '-season_id', '-joined_at').first()
    set_current_membership(user, fallback)
    return fallback


def set_current_membership(user, membership):
    """Saves [membership] (or None) as the user's current membership."""
    membership_id = membership.id if membership else None
    type(user).objects.filter(pk=user.pk).update(current_membership=membership_id)
    user.current_membership_id = membership_id


def expire_stale_invites_and_requests():
    """
    Saves ``expired`` on every pending invitation and join request older than
    ``INVITE_AND_REQUEST_LIFETIME``. Runs nightly (the
    ``expire_invites_and_requests`` command / cron endpoint), never per request:
    between runs, endpoints check the one row they touch (``current_status``).
    Returns how many invitations and requests expired.
    """
    cutoff = timezone.now() - INVITE_AND_REQUEST_LIFETIME
    invites = MessMemberShipInvitation.objects.filter(status='pending', invited_at__lt=cutoff).update(status='expired', updated_at=timezone.now())
    requests = MessMemberShipRequest.objects.filter(status='pending', requested_at__lt=cutoff).update(
        status='expired', updated_at=timezone.now(), response_message='Expired: not answered within 7 days.',
    )
    return invites, requests


def expire_now(item):
    """Saves ``expired`` on one invitation / join request found past its 7 days."""
    if item.status == 'pending' and item.current_status == 'expired':
        item.status = 'expired'
        item.save(update_fields=['status', 'updated_at'])


def random_season_name(mess):
    """`season-` + 3 random lowercase letters, unused in [mess]."""
    taken = {name.lower() for name in mess.seasons.values_list('name', flat=True)}
    while True:
        name = 'season-' + ''.join(secrets.choice(string.ascii_lowercase) for _ in range(3))
        if name not in taken:
            return name


def start_season(mess, name, start_date, source, move_current=False):
    """
    Creates a season of [mess] whose members are [source]'s members who
    haven't left (a disabled member stays disabled). No other season ends.
    With [move_current], users working in [source] switch to the new season.
    Returns the new season and how many members were carried.
    """
    with transaction.atomic():
        season = MessSeason.objects.create(mess=mess, name=name, start_date=start_date)
        carried = list(MessMemberShip.objects.filter(season=source, left_at__isnull=True)) if source else []
        created = MessMemberShip.objects.bulk_create([
            MessMemberShip(user_id=m.user_id, mess=mess, season=season, status=m.status) for m in carried
        ])
        if move_current:
            for membership in created:
                User.objects.filter(pk=membership.user_id, current_membership__season=source).update(current_membership=membership)
    return season, len(created)


def move_current_off(season):
    """
    Users working in [season] (about to be disabled or deleted) move to their
    newest usable membership in another season of the same mess, or to none
    (then `get_active_membership` picks one on their next request).
    """
    for membership in MessMemberShip.objects.select_related('user').filter(season=season):
        user = membership.user
        if user.current_membership_id != membership.id:
            continue
        fallback = (
            usable_memberships(user).filter(mess_id=season.mess_id).exclude(season=season)
            .order_by('-season__start_date', '-season_id').first()
        )
        set_current_membership(user, fallback)


def mess_today():
    """Today's date in the messes' time zone (``MESS_TIME_ZONE``), e.g. Bangladesh, not UTC."""
    return timezone.localtime(timezone.now(), ZoneInfo(settings.MESS_TIME_ZONE)).date()


def auto_create_due(mess, today):
    """Whether [mess]'s auto-create day is [today] and it hasn't run today."""
    if not mess.auto_create_season or mess.last_auto_season_on == today:
        return False
    if mess.auto_create_season_day == 0:
        return (today + timedelta(days=1)).month != today.month
    return today.day == mess.auto_create_season_day


def run_auto_create_seasons(today):
    """
    For every mess due today: creates a `season-xyz` from its active season
    (its newest enabled one if none is running) and switches the members
    working in that season to the new one. Returns the created seasons.
    """
    created = []
    for mess in Mess.objects.filter(auto_create_season=True):
        if not auto_create_due(mess, today):
            continue
        source = mess.active_season or mess.seasons.filter(is_disabled=False).order_by('-start_date', '-id').first()
        with transaction.atomic():
            season, _ = start_season(mess, random_season_name(mess), today, source, move_current=True)
            mess.last_auto_season_on = today
            mess.save(update_fields=['last_auto_season_on', 'updated_at'])
        created.append(season)
    return created


def signed_amount_summary(queryset):
    """
    Credit / debit / net / entries over a queryset with a signed ``amount``
    (positive = credit, negative = debit), in one query. Used by deposits and funds.
    """
    totals = queryset.aggregate(
        credit=Sum('amount', filter=Q(amount__gt=0)),
        debit=Sum('amount', filter=Q(amount__lt=0)),
        entries=Count('id'),
    )
    credit = totals['credit'] or Decimal('0')
    debit = -(totals['debit'] or Decimal('0'))
    return {"credit": float(credit), "debit": float(debit), "net": float(credit - debit), "entries": totals['entries']}
