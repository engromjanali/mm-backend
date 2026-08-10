from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

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
        fields = ['id', 'mess', 'title', 'content', 'is_pinned', 'created_at', 'updated_at']
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
