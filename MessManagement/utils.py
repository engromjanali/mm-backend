from decimal import Decimal

from django.db.models import Count, Q, Subquery, Sum
from rest_framework.exceptions import PermissionDenied
from .models import MessMemberShip, MessSeason


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
    """Memberships the user can work in: not left and not disabled by a manager."""
    return MessMemberShip.objects.select_related('mess', 'season').filter(user=user, status='active', left_at__isnull=True)


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
