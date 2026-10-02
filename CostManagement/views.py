"""
Cost (bazar / shopping) APIs, scoped to the caller's active season.

A cost entry records which member did the shopping, when, and the products
bought with their prices; its amount is the sum of those prices. Every member
— the manager included — can read the season's costs; only the manager or
acting manager can add, edit or delete them.

User endpoints live under ``/api/v1/user/`` and manager endpoints under
``/api/v1/admin/``.
"""
from django.db import transaction
from django.db.models import Count, Sum
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from MealManagement.utils import DATE_INPUT_FORMATS, validate_date_in_season
from MessManagement.membership_views import get_managed_membership
from MessManagement.models import MessMemberShip
from MessManagement.utils import get_active_membership
from .models import Cost, CostBreakdown

TIME_INPUT_FORMATS = ['%H:%M', '%H:%M:%S']


def cost_json(cost):
    return {
        "id": cost.id,
        "member_id": cost.performed_by_id,
        "member_name": cost.performed_by.user.full_name,
        "date": cost.date.isoformat(),
        "time": cost.time.strftime('%H:%M') if cost.time else None,
        "total": float(cost.amount),
        "note": cost.description or "",
        "items": [{"id": item.id, "product": item.name, "price": float(item.price)} for item in cost.breakdowns.all()],
        "recorded_by": cost.recorded_by.user.full_name if cost.recorded_by else None,
        "created_at": cost.created_at,
        "updated_at": cost.updated_at,
    }


def season_costs(season):
    return (
        Cost.objects.select_related('performed_by__user', 'recorded_by__user')
        .prefetch_related('breakdowns')
        .filter(season=season)
    )


def season_member(season, member_id):
    member = MessMemberShip.objects.filter(id=member_id, season=season, status='active', left_at__isnull=True).first()
    if not member:
        raise ValidationError({"member_id": "Member is not part of the current season."})
    return member


def replace_items(cost, items):
    """Replaces the entry's products and keeps ``amount`` equal to their total."""
    cost.breakdowns.all().delete()
    CostBreakdown.objects.bulk_create([CostBreakdown(cost=cost, name=i['product'], price=i['price']) for i in items])
    cost.amount = sum(i['price'] for i in items)


class CostItemSerializer(serializers.Serializer):
    product = serializers.CharField(max_length=100)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_product(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Product name is required.")
        return value

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0.")
        return value


class CostWriteSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()
    date = serializers.DateField(input_formats=DATE_INPUT_FORMATS, required=False)
    time = serializers.TimeField(input_formats=TIME_INPUT_FORMATS, required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    items = CostItemSerializer(many=True)

    def validate_items(self, value):
        # A partial (PATCH) update makes nested fields optional too, so check
        # every product still has both a name and a price.
        if not value or any('product' not in i or 'price' not in i for i in value):
            raise serializers.ValidationError("Add at least one product with a price.")
        return value


# ---------------------------------------------------------------------------
# User endpoints  (/api/v1/user/...)
# ---------------------------------------------------------------------------

class CostListView(APIView):
    """
    GET /api/v1/user/costs

    Every cost entry of the caller's active season (newest first), with the
    season and its totals.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        membership = get_active_membership(request.user)
        if not membership:
            raise PermissionDenied("You are not connected to an active mess.")
        costs = season_costs(membership.season)
        # Separate queries: joining the products would repeat each entry's amount in the sum.
        totals = costs.aggregate(total=Sum('amount'), entries=Count('id'))
        items = CostBreakdown.objects.filter(cost__season=membership.season).count()
        return Response({
            "season": {"id": membership.season_id, "name": membership.season.name},
            "data": [cost_json(c) for c in costs],
            "summary": {"total": float(totals['total'] or 0), "entries": totals['entries'], "items": items},
        })


# ---------------------------------------------------------------------------
# Admin endpoints  (/api/v1/admin/...)  — manager / acting manager only
# ---------------------------------------------------------------------------

class AdminCostCreateView(APIView):
    """POST /api/v1/admin/costs  {member_id, date?, time?, note?, items: [{product, price}]}"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        manager = get_managed_membership(request.user)
        serializer = CostWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if 'date' in data:
            validate_date_in_season(data['date'], manager.season)
        member = season_member(manager.season, data['member_id'])

        with transaction.atomic():
            cost = Cost(
                season=manager.season,
                performed_by=member,
                recorded_by=manager,
                date=data.get('date') or Cost._meta.get_field('date').get_default(),
                time=data.get('time'),
                description=data.get('note') or '',
                amount=0,
            )
            cost.save()
            replace_items(cost, data['items'])
            cost.save(update_fields=['amount'])
        return Response(cost_json(season_costs(manager.season).get(id=cost.id)), status=status.HTTP_201_CREATED)


class AdminCostDetailView(APIView):
    """
    PATCH  /api/v1/admin/costs/<id>  {member_id?, date?, time?, note?, items?}
           ``items`` replaces every product of the entry.
    DELETE /api/v1/admin/costs/<id>
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get(self, request, pk):
        manager = get_managed_membership(request.user)
        cost = season_costs(manager.season).filter(id=pk).first()
        if not cost:
            raise NotFound("Cost entry not found in the current season.")
        return manager, cost

    def patch(self, request, pk):
        manager, cost = self._get(request, pk)
        serializer = CostWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if 'date' in data:
            validate_date_in_season(data['date'], manager.season)
            cost.date = data['date']
        if 'member_id' in data:
            cost.performed_by = season_member(manager.season, data['member_id'])
        if 'time' in data:
            cost.time = data['time']
        if 'note' in data:
            cost.description = data['note'] or ''
        cost.recorded_by = manager

        with transaction.atomic():
            if 'items' in data:
                replace_items(cost, data['items'])
            cost.save()
        return Response(cost_json(season_costs(manager.season).get(id=cost.id)))

    def delete(self, request, pk):
        _, cost = self._get(request, pk)
        cost.delete()
        return Response({"message": "Cost entry deleted."})
