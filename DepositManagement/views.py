"""
Deposit APIs, scoped to the caller's active season.

A deposit belongs to one member (``performed_by``). A positive amount is a
credit (money in), a negative amount a debit (money out). A manager is also a
member, so they appear in member lists and totals and have "my deposits" too.

User endpoints live under ``/api/v1/user/`` and manager endpoints under
``/api/v1/admin/``.
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from MealManagement.utils import DATE_INPUT_FORMATS, parse_date_value
from MessManagement.membership_views import get_managed_membership
from MessManagement.models import MessMemberShip
from MessManagement.utils import get_active_membership
from .models import Deposit

ZERO = Decimal('0')


def deposit_json(deposit):
    return {
        "id": deposit.id,
        "member_id": deposit.performed_by_id,
        "member_name": deposit.performed_by.user.full_name,
        "amount": float(deposit.amount),
        "type": "debit" if deposit.amount < 0 else "credit",
        "date": deposit.date.isoformat(),
        "note": deposit.description or "",
        "payment_method": deposit.payment_method,
        "recorded_by": deposit.recorded_by.user.full_name if deposit.recorded_by else None,
        "created_at": deposit.created_at,
    }


def summarize(queryset):
    """Credit / debit / net / entries over a deposit queryset (one DB query)."""
    totals = queryset.aggregate(
        credit=Sum('amount', filter=Q(amount__gt=0)),
        debit=Sum('amount', filter=Q(amount__lt=0)),
        entries=Count('id'),
    )
    credit = totals['credit'] or ZERO
    debit = -(totals['debit'] or ZERO)
    return {"credit": float(credit), "debit": float(debit), "net": float(credit - debit), "entries": totals['entries']}


def season_deposits(season):
    return Deposit.objects.select_related('performed_by__user', 'recorded_by__user').filter(season=season)


class DepositWriteSerializer(serializers.Serializer):
    member_id = serializers.IntegerField(required=False)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    date = serializers.DateField(input_formats=DATE_INPUT_FORMATS, required=False)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    payment_method = serializers.ChoiceField(choices=['cash', 'bank_transfer', 'mobile_payment'], required=False)

    def validate_amount(self, value):
        if value == 0:
            raise serializers.ValidationError("Amount can't be zero. Use a positive amount for credit, negative for debit.")
        return value

    def validate_date(self, value):
        season = self.context['season']
        if value < season.start_date or (season.end_date and value > season.end_date):
            raise serializers.ValidationError("Date must be inside the current season.")
        return value


# ---------------------------------------------------------------------------
# User endpoints  (/api/v1/user/...)
# ---------------------------------------------------------------------------

class MyDepositListView(APIView):
    """
    GET /api/v1/user/deposits

    The caller's own deposits in their active season, plus their totals.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        membership = get_active_membership(request.user)
        if not membership:
            raise ValidationError({"detail": "You are not connected to an active mess."})
        deposits = season_deposits(membership.season).filter(performed_by=membership)
        return Response({"data": [deposit_json(d) for d in deposits], "summary": summarize(deposits)})


# ---------------------------------------------------------------------------
# Admin endpoints  (/api/v1/admin/...)  — manager / acting manager only
# ---------------------------------------------------------------------------

class AdminDepositListCreateView(APIView):
    """
    GET  /api/v1/admin/deposits?member_id=&date=&start=&end=
         Deposits of the active season. Filters are optional; ``date`` is a single
         day, ``start``/``end`` an inclusive range. Returns the list and its totals.
    POST /api/v1/admin/deposits  {member_id, amount, date?, note?, payment_method?}
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        manager = get_managed_membership(request.user)
        deposits = season_deposits(manager.season)

        member_id = request.query_params.get('member_id')
        if member_id:
            deposits = deposits.filter(performed_by_id=member_id)
        day = parse_date_value(request.query_params.get('date'), 'date')
        if day:
            deposits = deposits.filter(date=day)
        start = parse_date_value(request.query_params.get('start'), 'start')
        end = parse_date_value(request.query_params.get('end'), 'end')
        if start and end and start > end:
            raise ValidationError({"start": "Start date must be on or before end date."})
        if start:
            deposits = deposits.filter(date__gte=start)
        if end:
            deposits = deposits.filter(date__lte=end)

        return Response({"data": [deposit_json(d) for d in deposits], "summary": summarize(deposits)})

    def post(self, request):
        manager = get_managed_membership(request.user)
        serializer = DepositWriteSerializer(data=request.data, context={'season': manager.season})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if 'member_id' not in data:
            raise ValidationError({"member_id": "This field is required."})
        member = MessMemberShip.objects.filter(
            id=data['member_id'], season=manager.season, status='active', left_at__isnull=True,
        ).first()
        if not member:
            raise ValidationError({"member_id": "Member is not part of the current season."})

        deposit = Deposit.objects.create(
            season=manager.season,
            performed_by=member,
            recorded_by=manager,
            amount=data['amount'],
            date=data.get('date') or Deposit._meta.get_field('date').get_default(),
            description=data.get('note') or '',
            payment_method=data.get('payment_method', 'cash'),
        )
        return Response(deposit_json(season_deposits(manager.season).get(id=deposit.id)), status=status.HTTP_201_CREATED)


class AdminDepositDetailView(APIView):
    """
    PATCH  /api/v1/admin/deposits/<id>  {amount?, date?, note?, payment_method?}
    DELETE /api/v1/admin/deposits/<id>
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get(self, request, pk):
        manager = get_managed_membership(request.user)
        deposit = season_deposits(manager.season).filter(id=pk).first()
        if not deposit:
            raise NotFound("Deposit not found in the current season.")
        return manager, deposit

    def patch(self, request, pk):
        manager, deposit = self._get(request, pk)
        serializer = DepositWriteSerializer(data=request.data, partial=True, context={'season': manager.season})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if 'amount' in data:
            deposit.amount = data['amount']
        if 'date' in data:
            deposit.date = data['date']
        if 'note' in data:
            deposit.description = data['note'] or ''
        if 'payment_method' in data:
            deposit.payment_method = data['payment_method']
        deposit.recorded_by = manager
        deposit.save()
        return Response(deposit_json(deposit))

    def delete(self, request, pk):
        _, deposit = self._get(request, pk)
        deposit.delete()
        return Response({"message": "Deposit deleted."})


class AdminDepositSummaryView(APIView):
    """
    GET /api/v1/admin/deposits/summary

    Mess-wide totals for the active season, every member's balance (including
    members without deposits, sorted by net), and the manager's own totals.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        manager = get_managed_membership(request.user)
        deposits = season_deposits(manager.season)
        members = (
            MessMemberShip.objects.select_related('user')
            .filter(season=manager.season, status='active', left_at__isnull=True)
            .annotate(
                credit=Sum('deposits_performed__amount', filter=Q(deposits_performed__amount__gt=0)),
                debit=Sum('deposits_performed__amount', filter=Q(deposits_performed__amount__lt=0)),
                entries=Count('deposits_performed'),
            )
        )
        balances = []
        for m in members:
            credit = m.credit or ZERO
            debit = -(m.debit or ZERO)
            balances.append({
                "member_id": m.id, "member_name": m.user.full_name,
                "credit": float(credit), "debit": float(debit), "net": float(credit - debit), "entries": m.entries,
            })
        balances.sort(key=lambda b: b['net'], reverse=True)

        return Response({
            "season": {"id": manager.season_id, "name": manager.season.name},
            "summary": {**summarize(deposits), "members": len(balances), "active_members": sum(1 for b in balances if b['entries'])},
            "member_balances": balances,
            "mine": summarize(deposits.filter(performed_by=manager)),
        })
