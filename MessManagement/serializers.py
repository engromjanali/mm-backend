from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from AuthManagement.models import User
from .models import (
    Mess,
    MessMemberShip,
    MessMemberShipInvitation,
    MessMemberShipRequest,
    MessSeason,
    Notices,
)


# ---------------------------------------------------------------------------
# Read / Write serializers for individual models
# ---------------------------------------------------------------------------

class MessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mess
        fields = [
            'id', 'name', 'email', 'phone', 'address',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MessSeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessSeason
        fields = [
            'id', 'mess', 'name', 'start_date', 'end_date',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MessMemberShipSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = MessMemberShip
        fields = [
            'id', 'user', 'user_name', 'mess', 'season',
            'role', 'status', 'joined_at', 'left_at', 'updated_at',
        ]
        read_only_fields = ['id', 'joined_at', 'left_at', 'updated_at']


class MessMemberShipRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessMemberShipRequest
        fields = [
            'id', 'user', 'mess', 'status',
            'requested_at', 'responded_at', 'response_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'user', 'status', 'requested_at', 'responded_at', 'created_at', 'updated_at']

    def validate(self, attrs):
        request = self.context.get('request')
        if not request or not request.user:
            raise serializers.ValidationError("Authentication credentials were not provided.")
        
        user = request.user
        mess = attrs['mess']
        
        # Check if there is an existing pending request for the same user and mess
        existing_pending = MessMemberShipRequest.objects.filter(
            user=user,
            mess=mess,
            status='pending'
        ).exists()
        
        if existing_pending:
            raise serializers.ValidationError(
                {"mess": "You already have a pending request to join this mess."}
            )
            
        return attrs


class MessMemberShipInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessMemberShipInvitation
        fields = [
            'id', 'user', 'mess', 'status',
            'invited_at', 'responded_at', 'Invitation_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'invited_at', 'responded_at', 'created_at', 'updated_at']


class NoticesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notices
        fields = ['id', 'mess', 'title', 'content', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


# ---------------------------------------------------------------------------
# Composite serializer — orchestrates Mess + Season + Membership creation
# ---------------------------------------------------------------------------

class MessCreationSerializer(serializers.Serializer):
    """
    Accepts minimal mess info from the user.  Inside ``create()`` it
    atomically creates a Mess, its first Season, and the creator's
    Membership.
    """
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    address = serializers.CharField(max_length=255)

    def validate(self, attrs):
        # Users can create multiple messes, so no restriction here.
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user

        with transaction.atomic():
            # 1. Create the Mess
            mess = Mess.objects.create(
                name=validated_data['name'],
                email=validated_data['email'],
                phone=validated_data['phone'],
                address=validated_data['address'],
            )

            # 2. Create the first Season (with end_date left empty until the season is closed)
            today = timezone.now().date()
            season = MessSeason.objects.create(
                mess=mess,
                name='Season 1',
                start_date=today,
                end_date=None,
                is_active=True,
            )

            # 3. Enrol the creator as an active manager
            membership = MessMemberShip.objects.create(
                user=user,
                mess=mess,
                season=season,
                role='manager',
                status='active',
            )

        return {
            'mess': mess,
            'season': season,
            'membership': membership,
        }


# ---------------------------------------------------------------------------
# Season roll-over — closes the running season and opens the next one
# ---------------------------------------------------------------------------

def get_header(request, name):
    """
    Reads an integer header.  Django normalises ``season_id`` and
    ``season-id`` to the same key, so either spelling from the client works.
    """
    raw = request.headers.get(name.replace('_', '-'))
    if raw is None or not str(raw).strip():
        raise serializers.ValidationError({name: f"The '{name}' header is required."})
    try:
        return int(str(raw).strip())
    except ValueError:
        raise serializers.ValidationError({name: f"The '{name}' header must be a valid id."})


class StartNewSeasonSerializer(serializers.Serializer):
    """
    Ends the mess' most recent season and starts a fresh one, carrying every
    member who has not left over to it.

    The caller identifies itself through request headers:
        ``season_id``     - the season the client believes is the running one
        ``membership_id`` - the caller's membership inside that season

    Both must point at the latest season of the same mess, and the membership
    must be an active manager of it.
    """
    MANAGER_ROLES = ('manager',)

    name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    start_date = serializers.DateField(required=False)

    def validate(self, attrs):
        request = self.context['request']
        season_id = get_header(request, 'season_id')
        membership_id = get_header(request, 'membership_id')

        membership = (
            MessMemberShip.objects
            .select_related('mess', 'season')
            .filter(pk=membership_id, user=request.user)
            .first()
        )
        if membership is None:
            raise PermissionDenied("The membership_id header does not belong to you.")

        if membership.season_id != season_id:
            raise serializers.ValidationError(
                {"season_id": "The season_id header does not match the given membership."}
            )

        if membership.status != 'active' or membership.left_at is not None:
            raise PermissionDenied("Your membership in this mess is no longer active.")

        if membership.role not in self.MANAGER_ROLES:
            raise PermissionDenied("Only the manager of the mess can start a new season.")

        latest_season = (
            MessSeason.objects
            .filter(mess_id=membership.mess_id)
            .order_by('-start_date', '-id')
            .first()
        )
        if latest_season is None or latest_season.pk != season_id:
            raise serializers.ValidationError(
                {"season_id": "This is not the latest season of the mess."}
            )

        start_date = attrs.get('start_date') or timezone.now().date()
        if start_date < latest_season.start_date:
            raise serializers.ValidationError(
                {"start_date": "The new season cannot start before the season it replaces."}
            )

        attrs['start_date'] = start_date
        self.current_season = latest_season
        return attrs

    def create(self, validated_data):
        current_season = self.current_season
        mess = current_season.mess
        start_date = validated_data['start_date']

        with transaction.atomic():
            season_count = MessSeason.objects.filter(mess=mess).count()
            name = (validated_data.get('name') or '').strip() or f'Season {season_count + 1}'

            # 1. Close the running season on the day the new one begins.
            current_season.is_active = False
            if current_season.end_date is None:
                current_season.end_date = start_date
            current_season.save(update_fields=['is_active', 'end_date', 'updated_at'])

            # 2. Open the new season.
            new_season = MessSeason.objects.create(
                mess=mess,
                name=name,
                start_date=start_date,
                end_date=None,
                is_active=True,
            )

            # 3. Carry over everyone who did not leave the closing season.
            carried_over = (
                MessMemberShip.objects
                .filter(
                    mess=mess,
                    season=current_season,
                    status='active',
                    left_at__isnull=True,
                )
                .order_by('id')
            )
            MessMemberShip.objects.bulk_create([
                MessMemberShip(
                    user_id=old.user_id,
                    mess=mess,
                    season=new_season,
                    role=old.role,
                    status='active',
                )
                for old in carried_over
            ])

        memberships = (
            MessMemberShip.objects
            .filter(season=new_season)
            .select_related('user')
            .order_by('id')
        )

        return {
            'previous_season': current_season,
            'season': new_season,
            'memberships': memberships,
        }
