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
