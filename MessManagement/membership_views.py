"""
Membership flow APIs.

A user is connected to a mess only through a ``MessMemberShip`` in that mess's
active season. There are three ways in:

* the mess (manager / acting manager) invites a user  -> user accepts the invite
* the user sends a join request to a mess              -> manager approves it
* the user creates a new mess                          -> becomes its manager

Leadership lives on ``Mess`` so it spans every season. Each season owns its own
memberships; starting a new season copies every member who has not left.

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
from .utils import get_active_membership

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


def ensure_not_connected(user):
    if get_active_membership(user):
        raise ValidationError({"detail": "You are already connected to an active mess. Leave it first."})


def join_active_season(user, mess):
    season = mess.active_season
    if not season:
        raise ValidationError({"detail": "This mess has no active season."})
    membership, _ = MessMemberShip.objects.update_or_create(
        user=user, mess=mess, season=season,
        defaults={'status': 'active', 'left_at': None},
    )
    return membership


def membership_summary(membership):
    return {
        "membership_id": membership.id,
        "mess_id": membership.mess_id,
        "mess_name": membership.mess.name,
        "season_id": membership.season_id,
        "season_name": membership.season.name,
        "role": membership.role,
        "status": membership.status if membership.left_at is None and membership.season.is_active else "inactive",
    }


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

    Current membership (if any), past memberships, pending join requests and
    invitations addressed to the user.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        current = get_active_membership(user)
        history = (
            MessMemberShip.objects.select_related('mess', 'season')
            .filter(user=user)
            .exclude(id=current.id if current else None)
            .order_by('-joined_at')[:20]
        )
        pending_requests = (
            MessMemberShipRequest.objects.select_related('mess')
            .filter(user=user, status='pending')
            .order_by('-requested_at')
        )
        invites = (
            MessMemberShipInvitation.objects.select_related('mess')
            .filter(user=user, status='pending')
            .order_by('-invited_at')
        )
        return Response({
            "current": membership_summary(current) if current else None,
            "history": [membership_summary(m) for m in history],
            "pending_requests": [
                {"id": r.id, "mess_id": r.mess_id, "mess_name": r.mess.name, "created_at": r.requested_at}
                for r in pending_requests
            ],
            "invites": [
                {"id": i.id, "mess_id": i.mess_id, "mess_name": i.mess.name, "invite_code": i.invite_code, "status": i.status}
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
    creator becomes the mess manager.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreateMessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user
        ensure_not_connected(user)

        with transaction.atomic():
            mess = Mess.objects.create(
                name=data['name'].strip(), address=data['address'].strip(),
                email=data['email'], phone=data['phone'].strip(), manager=user,
            )
            season = MessSeason.objects.create(
                mess=mess, name=data['season_name'].strip(), start_date=timezone.now().date(), is_active=True,
            )
            membership = MessMemberShip.objects.create(user=user, mess=mess, season=season, status='active')
            # Requests elsewhere no longer make sense once the user runs a mess.
            MessMemberShipRequest.objects.filter(user=user, status='pending').update(
                status='rejected', responded_at=timezone.now(), response_message='Cancelled: user created a mess.',
            )

        return Response(
            {"message": "Mess created successfully.", "current": membership_summary(membership)},
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
        ensure_not_connected(user)
        try:
            mess = Mess.objects.get(id=int(request.data.get('mess_id')))
        except (Mess.DoesNotExist, TypeError, ValueError):
            raise ValidationError({"mess_id": "Mess not found."})
        if not mess.active_season:
            raise ValidationError({"detail": "This mess has no active season."})
        if MessMemberShipRequest.objects.filter(user=user, mess=mess, status='pending').exists():
            raise ValidationError({"detail": "You already have a pending request to this mess."})

        join_request = MessMemberShipRequest.objects.create(user=user, mess=mess)
        return Response(
            {"message": "Join request sent.", "id": join_request.id, "mess_id": mess.id, "mess_name": mess.name},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, pk):
        updated = MessMemberShipRequest.objects.filter(id=pk, user=request.user, status='pending').update(
            status='rejected', responded_at=timezone.now(), response_message='Cancelled by user.',
        )
        if not updated:
            raise NotFound("Pending request not found.")
        return Response({"message": "Join request cancelled."})


class InviteResponseView(APIView):
    """
    POST /api/v1/user/invites/accept   {invite_code}
    POST /api/v1/user/invites/decline  {invite_code}
    """
    permission_classes = [permissions.IsAuthenticated]
    accept = True

    def post(self, request):
        code = str(request.data.get('invite_code', '')).strip().upper()
        invite = (
            MessMemberShipInvitation.objects.select_related('mess')
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

        ensure_not_connected(request.user)
        with transaction.atomic():
            membership = join_active_season(request.user, invite.mess)
            invite.status = 'accepted'
            invite.responded_at = timezone.now()
            invite.save(update_fields=['status', 'responded_at', 'updated_at'])
            MessMemberShipRequest.objects.filter(user=request.user, status='pending').update(
                status='rejected', responded_at=timezone.now(), response_message='Cancelled: user joined a mess.',
            )
        return Response({"message": f"Joined {invite.mess.name}.", "current": membership_summary(membership)})


class LeaveMessView(APIView):
    """
    POST /api/v1/user/membership/leave

    Leaves the current mess. The member will not be carried into the next
    season. The manager must hand over leadership before leaving.
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


# ---------------------------------------------------------------------------
# Admin endpoints  (/api/v1/admin/...)  — manager / acting manager only
# ---------------------------------------------------------------------------

class MemberLookupView(APIView):
    """GET /api/v1/admin/member-lookup?query=<email or phone>"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        get_managed_membership(request.user)
        user = find_user(request.query_params.get('query'))
        if not user:
            raise NotFound("No account matches that email or phone.")
        current = get_active_membership(user)
        return Response({
            **user_summary(user),
            "available": current is None,
            "current_mess": current.mess.name if current else None,
        })


class AdminInviteView(APIView):
    """
    GET    /api/v1/admin/invites               pending invites sent by this mess
    POST   /api/v1/admin/invites   {user_id}    invite a user
    DELETE /api/v1/admin/invites   {invite_id}  revoke a pending invite
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
            "created_at": invite.invited_at,
        }

    def get(self, request):
        membership = get_managed_membership(request.user)
        invites = (
            MessMemberShipInvitation.objects.select_related('user')
            .filter(mess=membership.mess, status='pending')
            .order_by('-invited_at')
        )
        return Response([self._serialize(i) for i in invites])

    def post(self, request):
        membership = get_managed_membership(request.user)
        try:
            user = User.objects.get(id=int(request.data.get('user_id')))
        except (User.DoesNotExist, TypeError, ValueError):
            raise ValidationError({"user_id": "User not found."})
        if get_active_membership(user):
            raise ValidationError({"detail": "This user is already connected to an active mess."})

        invite = MessMemberShipInvitation.objects.filter(mess=membership.mess, user=user, status='pending').first()
        if not invite:
            invite = MessMemberShipInvitation.objects.create(mess=membership.mess, user=user, invited_by=request.user)
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
    """GET /api/v1/admin/join-requests — pending requests to this mess."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        membership = get_managed_membership(request.user)
        requests_qs = (
            MessMemberShipRequest.objects.select_related('user')
            .filter(mess=membership.mess, status='pending')
            .order_by('requested_at')
        )
        return Response([
            {
                "id": r.id,
                "status": r.status,
                "user_id": str(r.user_id),
                "user_name": r.user.full_name,
                "user_email": r.user.email,
                "phone": r.user.phone,
                "created_at": r.requested_at,
            }
            for r in requests_qs
        ])


class AdminJoinRequestDecisionView(APIView):
    """POST /api/v1/admin/join-requests/decision  {request_id, decision: accepted|rejected}"""
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

        with transaction.atomic():
            if decision == 'accepted':
                if get_active_membership(join_request.user):
                    raise ValidationError({"detail": "This user has already joined another mess."})
                join_active_season(join_request.user, membership.mess)
                # Other pending requests from this user are now moot.
                MessMemberShipRequest.objects.filter(user=join_request.user, status='pending').exclude(
                    id=join_request.id,
                ).update(status='rejected', responded_at=timezone.now(), response_message='User joined another mess.')
            join_request.status = 'approved' if decision == 'accepted' else 'rejected'
            join_request.responded_at = timezone.now()
            join_request.save(update_fields=['status', 'responded_at', 'updated_at'])
        return Response({"message": f"Request {decision}."})


class AdminMemberListView(APIView):
    """GET /api/v1/admin/members — members of the current season."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        membership = get_managed_membership(request.user)
        members = (
            MessMemberShip.objects.select_related('user', 'mess')
            .filter(season=membership.season, status='active', left_at__isnull=True)
            .order_by('user__full_name')
        )
        return Response([
            {**user_summary(m.user), "membership_id": m.id, "role": m.role, "status": m.status, "joined_at": m.joined_at}
            for m in members
        ])


class AdminSeasonView(APIView):
    """
    GET  /api/v1/admin/seasons          all seasons of this mess
    POST /api/v1/admin/seasons  {name}  close the active season and start a new one

    Every member of the closing season who has not left gets a fresh
    membership in the new season, so no season's data depends on another.
    """
    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def _serialize(season):
        return {
            "id": season.id, "name": season.name, "start_date": season.start_date,
            "end_date": season.end_date, "is_active": season.is_active,
        }

    def get(self, request):
        membership = get_managed_membership(request.user)
        seasons = membership.mess.seasons.order_by('-start_date', '-id')
        return Response([self._serialize(s) for s in seasons])

    def post(self, request):
        membership = get_managed_membership(request.user)
        name = str(request.data.get('name', '')).strip()
        if not name:
            raise ValidationError({"name": "Season name is required."})
        mess = membership.mess
        today = timezone.now().date()

        with transaction.atomic():
            old_season = membership.season
            carried_users = list(
                MessMemberShip.objects.filter(season=old_season, status='active', left_at__isnull=True)
                .values_list('user_id', flat=True)
            )
            old_season.is_active = False
            old_season.end_date = today
            old_season.save(update_fields=['is_active', 'end_date', 'updated_at'])

            new_season = MessSeason.objects.create(mess=mess, name=name, start_date=today, is_active=True)
            MessMemberShip.objects.bulk_create([
                MessMemberShip(user_id=user_id, mess=mess, season=new_season, status='active')
                for user_id in carried_users
            ])

        return Response(
            {"message": "New season started.", "season": self._serialize(new_season), "members_carried": len(carried_users)},
            status=status.HTTP_201_CREATED,
        )
