"""
Membership flow APIs.

A user is connected to a mess through a ``MessMemberShip`` in one of its
seasons — at most one per season, in any number of messes. The membership the
user chose as current (``User.current_membership``) decides which mess and
season every screen shows; they can switch it at any time. There are three
ways into a mess:

* the mess (manager / acting manager) invites a user  -> user accepts the invite
* the user sends a join request to a mess              -> manager approves it
* the user creates a new mess                          -> becomes its manager

Leadership lives on ``Mess`` so it spans every season. Each season owns its own
memberships; a new season copies every member of its source season who has not
left (see ``season_views``).

User endpoints live under ``/api/v1/user/`` and manager endpoints under
``/api/v1/admin/``.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from AuthManagement.models import User
from .models import (
    Mess,
    MessMemberShip,
    MessMemberShipInvitation,
    MessMemberShipRequest,
    MessSeason,
)
from .utils import get_active_membership, set_current_membership, usable_memberships

MANAGER_ROLES = ('manager', 'acting_manager')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_managed_membership(user):
    """Active membership of a user who manages (or acts for) that mess."""
    membership = get_active_membership(user)
    if not membership:
        raise PermissionDenied("You are not connected to an active mess.")
    if membership.role not in MANAGER_ROLES:
        raise PermissionDenied("Only the manager or acting manager can do this.")
    return membership


def is_member_of(user, season):
    """Whether [user] already has a usable membership in [season]."""
    return season is not None and usable_memberships(user).filter(season=season).exists()


def join_season(user, season):
    membership, _ = MessMemberShip.objects.update_or_create(
        user=user, mess_id=season.mess_id, season=season,
        defaults={'status': 'active', 'left_at': None},
    )
    return membership


def running_seasons(mess):
    """[mess]'s seasons new members can be added to: not ended, not disabled."""
    return mess.seasons.filter(end_date__isnull=True, is_disabled=False)


def season_closed_reason(season):
    """Why nobody can be added to [season], or ``None`` while it runs."""
    if season.is_disabled:
        return f"{season.name} is disabled."
    if season.end_date is not None:
        return f"{season.name} has ended."
    return None


def target_season(manager, season_id):
    """
    The running season of the manager's mess that a new member joins:
    [season_id], or the season the manager is working in when it's empty.
    """
    if season_id in (None, ''):
        season = manager.season
    else:
        try:
            season = manager.mess.seasons.filter(pk=int(season_id)).first()
        except (TypeError, ValueError):
            raise ValidationError({"season_id": "season_id must be a number."})
        if not season:
            raise ValidationError({"season_id": "Season not found in this mess."})
    reason = season_closed_reason(season)
    if reason:
        raise ValidationError({"season_id": f"{reason} Choose a running season."})
    return season


def membership_state(membership):
    """`active`, `disabled` (turned off by a manager) or `left`."""
    if membership.left_at is not None:
        return 'left'
    return 'active' if membership.status == 'active' else 'disabled'


def membership_summary(membership, current_id=None):
    state = membership_state(membership)
    return {
        "membership_id": membership.id,
        "mess_id": membership.mess_id,
        "mess_name": membership.mess.name,
        "season_id": membership.season_id,
        "season_name": membership.season.name,
        "season_start_date": membership.season.start_date,
        "season_end_date": membership.season.end_date,
        "role": membership.role,
        "status": state,
        "joined_at": membership.joined_at,
        "left_at": membership.left_at,
        "is_current": current_id is not None and membership.id == current_id,
        "can_switch": state == 'active' and not membership.season.is_disabled,
    }


def admin_member_json(membership):
    """
    A season member as the manager sees them; ``disabled`` = turned off by a
    manager, ``state`` = ``active`` / ``disabled`` / ``left``.
    """
    return {
        **user_summary(membership.user),
        "membership_id": membership.id,
        "role": membership.role,
        "status": membership.status,
        "state": membership_state(membership),
        "disabled": membership.status != 'active' and membership.left_at is None,
        "joined_at": membership.joined_at,
        "left_at": membership.left_at,
    }


def _primary_manager(user):
    """The caller's membership; only the primary manager (not the acting one) passes."""
    membership = get_managed_membership(user)
    if membership.role != 'manager':
        raise PermissionDenied("Only the primary manager can change the mess leadership.")
    return membership


def _season_member(manager, membership_id):
    """A membership of the manager's current season, or a readable 404."""
    member = MessMemberShip.objects.select_related('user', 'mess').filter(pk=membership_id, season=manager.season).first()
    if not member:
        raise NotFound("Member not found in the current season.")
    return member


def _active_season_member(manager, membership_id):
    """Like `_season_member`, but the member must be active (not disabled or left)."""
    member = _season_member(manager, membership_id)
    if member.status != 'active' or member.left_at is not None:
        raise ValidationError({"detail": f"{member.user.full_name} isn't an active member. Enable them first."})
    return member


def request_summary(join_request):
    """A join request as its sender sees it; the season is set once it's approved."""
    return {
        "id": join_request.id, "mess_id": join_request.mess_id, "mess_name": join_request.mess.name, "status": join_request.status,
        **season_ref(join_request.season),
        "created_at": join_request.requested_at, "responded_at": join_request.responded_at,
    }


def season_ref(season):
    return {"season_id": season.id if season else None, "season_name": season.name if season else None}


def user_summary(user):
    return {"id": str(user.id), "name": user.full_name, "email": user.email, "phone": user.phone}


def find_user(query):
    query = (query or '').strip()
    if not query:
        return None
    return User.objects.filter(Q(email__iexact=query) | Q(phone=query)).first()


def int_param(request, name, default):
    try:
        value = int(request.query_params.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def bool_param(request, name):
    return request.query_params.get(name, '').lower() in ('1', 'true', 'yes')


# ---------------------------------------------------------------------------
# User endpoints  (/api/v1/user/...)
# ---------------------------------------------------------------------------

class PublicMessListView(APIView):
    """
    GET /api/v1/user/messes?search=&page=1&per_page=10

    Public directory of messes. No authentication required.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        queryset = Mess.objects.order_by('name', 'id')
        search = request.query_params.get('search', '').strip()
        if search:
            filters = Q(name__icontains=search)
            if search.isdigit():
                filters |= Q(id=int(search))
            queryset = queryset.filter(filters)

        per_page = min(int_param(request, 'per_page', 10), 50)
        page = int_param(request, 'page', 1)
        total = queryset.count()
        last_page = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        messes = queryset.values('id', 'name', 'address')[start:start + per_page]

        return Response({
            "data": list(messes),
            "meta": {"total": total, "current_page": page, "last_page": last_page, "per_page": per_page},
        })


class MembershipStatusView(APIView):
    """
    GET /api/v1/user/membership/status

    The current membership (if any), every membership of the user across all
    messes and seasons (``memberships``, with ``is_current`` / ``can_switch``;
    ``history`` is the same list without the current one), every join request
    the user sent (``join_requests``; ``pending_requests`` = the pending ones)
    and every invitation addressed to the user — any status, newest first.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        current = get_active_membership(user)
        current_id = current.id if current else None
        memberships = (
            MessMemberShip.objects.select_related('mess', 'season')
            .filter(user=user)
            .order_by('-season__start_date', '-season_id', '-joined_at')
        )
        join_requests = MessMemberShipRequest.objects.select_related('mess', 'season').filter(user=user).order_by('-requested_at')
        invites = MessMemberShipInvitation.objects.select_related('mess', 'season', 'invited_by').filter(user=user).order_by('-invited_at')
        return Response({
            "current": membership_summary(current, current_id) if current else None,
            "memberships": [membership_summary(m, current_id) for m in memberships],
            "history": [membership_summary(m, current_id) for m in memberships if m.id != current_id],
            "pending_requests": [request_summary(r) for r in join_requests if r.status == 'pending'],
            "join_requests": [request_summary(r) for r in join_requests],
            "invites": [
                {
                    "id": i.id, "mess_id": i.mess_id, "mess_name": i.mess.name, "invite_code": i.invite_code, "status": i.status,
                    **season_ref(i.season),
                    "invited_by": i.invited_by.full_name if i.invited_by else None,
                    "created_at": i.invited_at, "responded_at": i.responded_at,
                }
                for i in invites
            ],
        })


class CreateMessSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    season_name = serializers.CharField(max_length=100)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')


class CreateMessView(APIView):
    """
    POST /api/v1/user/messes/create  {name, season_name, address?, email?, phone?}

    Creates the mess, its first season and the creator's membership. The
    creator becomes the mess manager and the new membership becomes current;
    their other messes are unaffected.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreateMessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user

        with transaction.atomic():
            mess = Mess.objects.create(
                name=data['name'].strip(), address=data['address'].strip(),
                email=data['email'], phone=data['phone'].strip(), manager=user,
            )
            season = MessSeason.objects.create(
                mess=mess, name=data['season_name'].strip(), start_date=timezone.now().date(),
            )
            membership = MessMemberShip.objects.create(user=user, mess=mess, season=season, status='active')
            set_current_membership(user, membership)

        return Response(
            {"message": "Mess created successfully.", "current": membership_summary(membership, membership.id)},
            status=status.HTTP_201_CREATED,
        )


class JoinRequestView(APIView):
    """
    POST   /api/v1/user/join-requests        {mess_id}   send a join request
    DELETE /api/v1/user/join-requests/<id>               cancel a pending request
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        try:
            mess = Mess.objects.get(id=int(request.data.get('mess_id')))
        except (Mess.DoesNotExist, TypeError, ValueError):
            raise ValidationError({"mess_id": "Mess not found."})
        if not mess.active_season:
            raise ValidationError({"detail": "This mess has no running season."})
        if is_member_of(user, mess.active_season):
            raise ValidationError({"detail": f"You're already a member of {mess.name}."})
        if MessMemberShipRequest.objects.filter(user=user, mess=mess, status='pending').exists():
            raise ValidationError({"detail": "You already have a pending request to this mess."})

        join_request = MessMemberShipRequest.objects.create(user=user, mess=mess)
        return Response(
            {"message": "Join request sent.", "id": join_request.id, "mess_id": mess.id, "mess_name": mess.name},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, pk):
        updated = MessMemberShipRequest.objects.filter(id=pk, user=request.user, status='pending').update(
            status='cancelled', responded_at=timezone.now(), response_message='Cancelled by user.',
        )
        if not updated:
            raise NotFound("Pending request not found.")
        return Response({"message": "Join request cancelled."})


class InviteResponseView(APIView):
    """
    POST /api/v1/user/invites/accept   {invite_code}
    POST /api/v1/user/invites/decline  {invite_code}

    Accepting joins the season the manager chose when inviting.
    """
    permission_classes = [permissions.IsAuthenticated]
    accept = True

    def post(self, request):
        code = str(request.data.get('invite_code', '')).strip().upper()
        invite = (
            MessMemberShipInvitation.objects.select_related('mess', 'season')
            .filter(invite_code=code, user=request.user, status='pending')
            .first()
        )
        if not invite:
            raise ValidationError({"invite_code": "Invite is invalid, expired, or not addressed to you."})

        if not self.accept:
            invite.status = 'declined'
            invite.responded_at = timezone.now()
            invite.save(update_fields=['status', 'responded_at', 'updated_at'])
            return Response({"message": "Invite declined."})

        season = invite.season
        if season is None:
            raise ValidationError({"detail": "The season of this invite was deleted. Ask the manager for a new invite."})
        reason = season_closed_reason(season)
        if reason:
            raise ValidationError({"detail": f"{reason} Ask the manager for a new invite."})
        if is_member_of(request.user, season):
            raise ValidationError({"detail": f"You're already a member of {invite.mess.name} ({season.name})."})
        with transaction.atomic():
            membership = join_season(request.user, season)
            invite.status = 'accepted'
            invite.responded_at = timezone.now()
            invite.save(update_fields=['status', 'responded_at', 'updated_at'])
            # A pending request to the same mess is now moot; other messes are unaffected.
            MessMemberShipRequest.objects.filter(user=request.user, mess=invite.mess, status='pending').update(
                status='cancelled', responded_at=timezone.now(), response_message='Cancelled: user joined via invite.',
            )
            set_current_membership(request.user, membership)
        return Response({"message": f"Joined {invite.mess.name} ({season.name}).", "current": membership_summary(membership, membership.id)})


class LeaveMessView(APIView):
    """
    POST /api/v1/user/membership/leave

    Leaves the current membership's mess. The member will not be carried into
    the next season, and their newest other membership (if any) becomes
    current. The manager must hand over leadership before leaving.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        membership = get_active_membership(request.user)
        if not membership:
            raise ValidationError({"detail": "You are not connected to an active mess."})
        if membership.role == 'manager':
            raise ValidationError({"detail": "Transfer the manager role before leaving the mess."})

        with transaction.atomic():
            membership.status = 'inactive'
            membership.left_at = timezone.now()
            membership.save(update_fields=['status', 'left_at', 'updated_at'])
            mess = membership.mess
            if mess.acting_manager_id == request.user.id:
                mess.acting_manager = None
                mess.save(update_fields=['acting_manager', 'updated_at'])
        return Response({"message": "You left the mess."})


class SwitchMembershipView(APIView):
    """
    POST /api/v1/user/membership/switch  {membership_id}

    Makes one of the user's memberships current (saved on their profile);
    every screen then shows that mess and season. Any membership they haven't
    left and that isn't disabled can be chosen, including older seasons.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            membership_id = int(request.data.get('membership_id'))
        except (TypeError, ValueError):
            raise ValidationError({"membership_id": "membership_id must be a number."})
        membership = MessMemberShip.objects.select_related('mess', 'season').filter(pk=membership_id, user=request.user).first()
        if not membership:
            raise NotFound("Membership not found.")

        label = f"{membership.mess.name} ({membership.season.name})"
        state = membership_state(membership)
        if state == 'left':
            raise ValidationError({"detail": f"You left {label}, so it can't be your current membership."})
        if state == 'disabled':
            raise ValidationError({"detail": f"Your membership in {label} was disabled by its manager."})
        if membership.season.is_disabled:
            raise ValidationError({"detail": f"{label} is disabled by its manager, so it can't be your current season."})

        set_current_membership(request.user, membership)
        return Response({"message": f"Switched to {label}.", "current": membership_summary(membership, membership.id)})


# ---------------------------------------------------------------------------
# Admin endpoints  (/api/v1/admin/...)  — manager / acting manager only
# ---------------------------------------------------------------------------

class MemberLookupView(APIView):
    """
    GET /api/v1/admin/member-lookup?query=<email or phone>

    ``joined_season_ids`` = the running seasons of this mess the user already
    belongs to; ``available`` = there's a running season they can be invited to.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        manager = get_managed_membership(request.user)
        user = find_user(request.query_params.get('query'))
        if not user:
            raise NotFound("No account matches that email or phone.")
        running = running_seasons(manager.mess)
        joined = list(usable_memberships(user).filter(season__in=running).values_list('season_id', flat=True))
        return Response({
            **user_summary(user),
            "available": running.exclude(pk__in=joined).exists(),
            "joined_season_ids": joined,
        })


class AdminInviteView(APIView):
    """
    GET    /api/v1/admin/invites                           every invite sent by this mess (any status)
    POST   /api/v1/admin/invites   {user_id, season_id?}    invite a user to a running season
                                                           (default: the season the manager works in)
    DELETE /api/v1/admin/invites   {invite_id}              revoke a pending invite
    """
    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def _serialize(invite):
        return {
            "id": invite.id,
            "invite_code": invite.invite_code,
            "status": invite.status,
            "user_id": str(invite.user_id),
            "user_name": invite.user.full_name,
            "user_email": invite.user.email,
            **season_ref(invite.season),
            "created_at": invite.invited_at,
            "responded_at": invite.responded_at,
        }

    def get(self, request):
        membership = get_managed_membership(request.user)
        invites = MessMemberShipInvitation.objects.select_related('user', 'season').filter(mess=membership.mess).order_by('-invited_at')
        return Response([self._serialize(i) for i in invites])

    def post(self, request):
        membership = get_managed_membership(request.user)
        try:
            user = User.objects.get(id=int(request.data.get('user_id')))
        except (User.DoesNotExist, TypeError, ValueError):
            raise ValidationError({"user_id": "User not found."})
        season = target_season(membership, request.data.get('season_id'))
        if is_member_of(user, season):
            raise ValidationError({"detail": f"{user.full_name} is already a member of {season.name}."})

        invite = MessMemberShipInvitation.objects.filter(mess=membership.mess, user=user, season=season, status='pending').first()
        if not invite:
            invite = MessMemberShipInvitation.objects.create(mess=membership.mess, user=user, season=season, invited_by=request.user)
        return Response(self._serialize(invite), status=status.HTTP_201_CREATED)

    def delete(self, request):
        membership = get_managed_membership(request.user)
        updated = MessMemberShipInvitation.objects.filter(
            id=request.data.get('invite_id'), mess=membership.mess, status='pending',
        ).update(status='revoked', responded_at=timezone.now())
        if not updated:
            raise NotFound("Pending invite not found.")
        return Response({"message": "Invite revoked."})


class AdminJoinRequestListView(APIView):
    """GET /api/v1/admin/join-requests — every request to this mess (any status), newest first."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        membership = get_managed_membership(request.user)
        requests_qs = (
            MessMemberShipRequest.objects.select_related('user', 'season')
            .filter(mess=membership.mess)
            .order_by('-requested_at')
        )
        return Response([
            {
                "id": r.id,
                "status": r.status,
                "user_id": str(r.user_id),
                "user_name": r.user.full_name,
                "user_email": r.user.email,
                "phone": r.user.phone,
                # The season the user was added to; null until approved.
                **season_ref(r.season),
                "created_at": r.requested_at,
                "responded_at": r.responded_at,
            }
            for r in requests_qs
        ])


class AdminJoinRequestDecisionView(APIView):
    """
    POST /api/v1/admin/join-requests/decision  {request_id, decision: accepted|rejected, season_id?}

    Accepting adds the user to the running season ``season_id`` (default: the
    season the manager works in) and records it on the request.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        membership = get_managed_membership(request.user)
        decision = request.data.get('decision')
        if decision not in ('accepted', 'rejected'):
            raise ValidationError({"decision": "Must be 'accepted' or 'rejected'."})
        join_request = (
            MessMemberShipRequest.objects.select_related('user')
            .filter(id=request.data.get('request_id'), mess=membership.mess, status='pending')
            .first()
        )
        if not join_request:
            raise NotFound("Pending request not found.")
        name = join_request.user.full_name

        if decision == 'rejected':
            join_request.status = 'rejected'
            join_request.responded_at = timezone.now()
            join_request.save(update_fields=['status', 'responded_at', 'updated_at'])
            return Response({"message": f"{name}'s request was rejected."})

        season = target_season(membership, request.data.get('season_id'))
        if is_member_of(join_request.user, season):
            raise ValidationError({"detail": f"{name} is already a member of {season.name}."})
        with transaction.atomic():
            join_season(join_request.user, season)
            join_request.status = 'approved'
            join_request.season = season
            join_request.responded_at = timezone.now()
            join_request.save(update_fields=['status', 'season', 'responded_at', 'updated_at'])
        return Response({"message": f"{name} joined {season.name}."})


class AdminMemberListView(APIView):
    """
    GET /api/v1/admin/members?include_disabled=true&include_left=true

    Active members of the current season; with ``include_disabled`` also the
    members a manager disabled, with ``include_left`` also the members who left.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        membership = get_managed_membership(request.user)
        members = MessMemberShip.objects.select_related('user', 'mess').filter(season=membership.season)
        if not bool_param(request, 'include_left'):
            members = members.filter(left_at__isnull=True)
        if not bool_param(request, 'include_disabled'):
            members = members.filter(Q(status='active') | Q(left_at__isnull=False))
        return Response([admin_member_json(m) for m in members.order_by('user__full_name')])


class AdminMemberStatusView(APIView):
    """
    POST /api/v1/admin/members/<membership_id>/disable
    POST /api/v1/admin/members/<membership_id>/enable

    Manager / acting manager. A disabled member can't open the mess (their
    records stay) until enabled again. The primary manager can't be disabled,
    and disabling the acting manager also removes that role.
    """
    permission_classes = [permissions.IsAuthenticated]
    disable = True

    def post(self, request, pk):
        manager = get_managed_membership(request.user)
        member = _season_member(manager, pk)
        name = member.user.full_name
        if member.left_at is not None:
            raise ValidationError({"detail": f"{name} left the mess. Invite them again instead."})

        if self.disable:
            if member.user_id == request.user.id:
                raise ValidationError({"detail": "You can't disable yourself."})
            if member.role == 'manager':
                raise ValidationError({"detail": "The primary manager can't be disabled."})
            if member.status != 'active':
                raise ValidationError({"detail": f"{name} is already disabled."})
            with transaction.atomic():
                member.status = 'inactive'
                member.save(update_fields=['status', 'updated_at'])
                mess = Mess.objects.select_for_update().get(pk=member.mess_id)
                if mess.acting_manager_id == member.user_id:
                    mess.acting_manager = None
                    mess.save(update_fields=['acting_manager', 'updated_at'])
            return Response({"message": f"{name} is disabled and can't open this mess until enabled again."})

        if member.status == 'active':
            raise ValidationError({"detail": f"{name} is already active."})
        member.status = 'active'
        member.save(update_fields=['status', 'updated_at'])
        return Response({"message": f"{name} is active again."})


class AdminActingManagerView(APIView):
    """
    POST   /api/v1/admin/members/<membership_id>/acting-manager  make acting manager
    DELETE /api/v1/admin/members/<membership_id>/acting-manager  remove the role

    Primary manager only. A mess has one acting manager, so assigning a new
    one makes the previous one a regular member.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        manager = _primary_manager(request.user)
        member = _active_season_member(manager, pk)
        name = member.user.full_name
        if member.user_id == request.user.id:
            raise ValidationError({"detail": "You're the primary manager already."})
        with transaction.atomic():
            mess = Mess.objects.select_for_update().get(pk=manager.mess_id)
            if mess.acting_manager_id == member.user_id:
                raise ValidationError({"detail": f"{name} is already the acting manager."})
            previous = mess.acting_manager
            mess.acting_manager = member.user
            mess.save(update_fields=['acting_manager', 'updated_at'])
        message = f"{name} is now the acting manager."
        if previous is not None:
            message += f" {previous.full_name} is a regular member again."
        return Response({"message": message})

    def delete(self, request, pk):
        manager = _primary_manager(request.user)
        member = _season_member(manager, pk)
        name = member.user.full_name
        with transaction.atomic():
            mess = Mess.objects.select_for_update().get(pk=manager.mess_id)
            if mess.acting_manager_id != member.user_id:
                raise ValidationError({"detail": f"{name} isn't the acting manager."})
            mess.acting_manager = None
            mess.save(update_fields=['acting_manager', 'updated_at'])
        return Response({"message": f"{name} is no longer the acting manager."})


class AdminTransferOwnershipView(APIView):
    """
    POST /api/v1/admin/members/<membership_id>/transfer-ownership

    Primary manager only: makes an active member the primary manager. The
    previous manager becomes a regular member (and the new manager stops
    being acting manager if they were).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        manager = _primary_manager(request.user)
        member = _active_season_member(manager, pk)
        name = member.user.full_name
        if member.user_id == request.user.id:
            raise ValidationError({"detail": "You're already the primary manager."})
        with transaction.atomic():
            mess = Mess.objects.select_for_update().get(pk=manager.mess_id)
            if mess.manager_id != request.user.id:
                raise PermissionDenied("You're no longer the primary manager of this mess.")
            mess.manager = member.user
            if mess.acting_manager_id == member.user_id:
                mess.acting_manager = None
            mess.save(update_fields=['manager', 'acting_manager', 'updated_at'])
        return Response({"message": f"{name} is now the primary manager. You're a regular member now."})
