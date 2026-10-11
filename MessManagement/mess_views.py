"""
Mess details API: the caller's current mess and its active season at a glance.

Any member (the manager included) sees the mess info, the season, the
leadership's contacts, the season's members and a snapshot of the season's
numbers. User endpoints live under ``/api/v1/user/``.
"""
from rest_framework import permissions, serializers
from django.conf import settings
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from DepositManagement.models import Deposit
from FundManagement.models import Fund
from MealManagement.utils import season_meal_rate
from MessManagement.membership_views import get_managed_membership
from MessManagement.models import Mess
from .membership_views import MANAGER_ROLES
from .models import MessMemberShip
from .utils import get_active_membership, signed_amount_summary

# Members list order: manager, acting manager, then everyone else by name.
ROLE_ORDER = {'manager': 0, 'acting_manager': 1, 'member': 2}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _person(user):
    if user is None:
        return None
    return {"user_id": user.id, "name": user.full_name, "email": user.email, "phone": user.phone}


def _season_stats(season, mess, member_count):
    meal_rate, total_meals, total_cost = season_meal_rate(season)
    return {
        "members": member_count,
        "total_meals": float(total_meals),
        "meal_rate": float(meal_rate),
        "total_cost": float(total_cost),
        "total_deposit": signed_amount_summary(Deposit.objects.filter(season=season))['net'],
        # The fund belongs to the mess and carries over between seasons.
        "fund_balance": signed_amount_summary(Fund.objects.filter(mess=mess))['net'],
    }


# ---------------------------------------------------------------------------
# User endpoints  (/api/v1/user/...)
# ---------------------------------------------------------------------------

class MessDetailsUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mess
        fields = ('name', 'address', 'email', 'phone', 'map_url', 'latitude', 'longitude')
        read_only_fields = ('map_url',)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        latitude = attrs.get('latitude', self.instance.latitude if self.instance else None)
        longitude = attrs.get('longitude', self.instance.longitude if self.instance else None)
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError({'latitude': 'Latitude and longitude must be set together.', 'longitude': 'Latitude and longitude must be set together.'})
        if latitude is not None and not -90 <= latitude <= 90:
            raise serializers.ValidationError({'latitude': 'Latitude must be between -90 and 90.'})
        if longitude is not None and not -180 <= longitude <= 180:
            raise serializers.ValidationError({'longitude': 'Longitude must be between -180 and 180.'})
        attrs['map_url'] = '' if latitude is None else f'https://www.google.com/maps/search/?api=1&query={format(latitude.normalize(), "f")},{format(longitude.normalize(), "f")}'
        return attrs


class MyMessView(APIView):
    """
    GET /api/v1/user/mess

    The caller's current mess: info, active season, the caller's role, the
    manager / acting manager, the season's members, season numbers and what
    the caller may do (edit, transfer leadership, leave).
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        membership = get_managed_membership(request.user)
        serializer = MessDetailsUpdateSerializer(membership.mess, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def get(self, request):
        membership = get_active_membership(request.user)
        if not membership:
            raise ValidationError({"detail": "You are not connected to an active mess."})
        mess = membership.mess
        season = membership.season
        role = membership.role

        members = sorted(
            MessMemberShip.objects.select_related('user').filter(season=season, status='active', left_at__isnull=True),
            key=lambda m: (ROLE_ORDER[mess.role_of(m.user_id)], m.user.full_name.lower()),
        )

        return Response({
            "id": mess.id,
            "name": mess.name,
            "address": mess.address,
            "email": mess.email,
            "phone": mess.phone,
            "map_url": mess.map_url,
            "latitude": mess.latitude,
            "longitude": mess.longitude,
            "created_at": mess.created_at,
            "season": {"id": season.id, "name": season.name, "start_date": season.start_date, "end_date": season.end_date},
            "my_role": role,
            "joined_at": membership.joined_at,
            "manager": _person(mess.manager),
            "acting_manager": _person(mess.acting_manager),
            "members": [
                {"membership_id": m.id, "user_id": m.user_id, "name": m.user.full_name, "role": mess.role_of(m.user_id), "joined_at": m.joined_at}
                for m in members
            ],
            "stats": _season_stats(season, mess, len(members)),
            "permissions": {
                "can_edit": role in MANAGER_ROLES,
                "can_transfer": role == 'manager',
                # The manager must hand over leadership before leaving.
                "can_leave": role != 'manager',
            },
        })


class MessLocationSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        get_managed_membership(request.user)
        query = request.query_params.get('q', '').strip()
        if len(query) < 3:
            raise ValidationError({'q': 'Enter at least 3 characters.'})
        if not settings.GOOGLE_MAPS_API_KEY:
            raise ValidationError({'detail': 'Google Maps search is not configured.'})
        payload = json.dumps({'textQuery': query, 'maxResultCount': 5}).encode()
        places_request = Request(
            'https://places.googleapis.com/v1/places:searchText',
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': settings.GOOGLE_MAPS_API_KEY,
                'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.location',
            },
            method='POST',
        )
        try:
            with urlopen(places_request, timeout=5) as response:
                data = json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            raise ValidationError({'detail': 'Location search is temporarily unavailable.'})
        return Response([
            {
                'name': place.get('displayName', {}).get('text', ''),
                'address': place.get('formattedAddress', ''),
                'latitude': place.get('location', {}).get('latitude'),
                'longitude': place.get('location', {}).get('longitude'),
            }
            for place in data.get('places', [])
            if place.get('location', {}).get('latitude') is not None and place.get('location', {}).get('longitude') is not None
        ])
