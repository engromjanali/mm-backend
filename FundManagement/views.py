"""
Mess fund APIs, scoped to the caller's mess.

A fund entry is shared mess money. It belongs to the mess, not to a season
(it carries over when a new season starts), and isn't tied to a member. A
positive amount is a credit (money into the fund), a negative amount a debit
(money out). Every member — the manager included — can read the fund; only
the manager or acting manager can change it.

User endpoints live under ``/api/v1/user/`` and manager endpoints under
``/api/v1/admin/``.
"""
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from MealManagement.utils import DATE_INPUT_FORMATS, apply_date_filters
from MessManagement.membership_views import get_managed_membership
from MessManagement.utils import get_active_membership, signed_amount_summary
from .models import Fund


def fund_json(fund):
    return {
        "id": fund.id,
        "amount": float(fund.amount),
        "type": "debit" if fund.amount < 0 else "credit",
        "date": fund.date.isoformat(),
        "note": fund.description or "",
        "recorded_by": fund.recorded_by.full_name if fund.recorded_by else None,
        "created_at": fund.created_at,
        "updated_at": fund.updated_at,
    }


def mess_funds(mess):
    return Fund.objects.select_related('recorded_by').filter(mess=mess)


class FundWriteSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    date = serializers.DateField(input_formats=DATE_INPUT_FORMATS, required=False)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_amount(self, value):
        if value == 0:
            raise serializers.ValidationError("Amount can't be zero. Use a positive amount for credit, negative for debit.")
        return value


# ---------------------------------------------------------------------------
# User endpoints  (/api/v1/user/...)
# ---------------------------------------------------------------------------

class FundListView(APIView):
    """
    GET /api/v1/user/funds?date=&start_date=&end_date=

    Fund entries of the caller's mess (every season), with totals for the
    returned list and the fund's overall balance. ``date`` is a single day,
    ``start_date``/``end_date`` an inclusive range (either end optional).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        membership = get_active_membership(request.user)
        if not membership:
            raise PermissionDenied("You are not connected to an active mess.")
        all_funds = mess_funds(membership.mess)
        funds, _ = apply_date_filters(all_funds, request)
        return Response({
            "data": [fund_json(f) for f in funds],
            "summary": signed_amount_summary(funds),
            "balance": signed_amount_summary(all_funds)['net'],
        })


# ---------------------------------------------------------------------------
# Admin endpoints  (/api/v1/admin/...)  — manager / acting manager only
# ---------------------------------------------------------------------------

class AdminFundCreateView(APIView):
    """POST /api/v1/admin/funds  {amount, date?, note?}"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        manager = get_managed_membership(request.user)
        serializer = FundWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        fund = Fund.objects.create(
            mess=manager.mess,
            recorded_by=request.user,
            amount=data['amount'],
            date=data.get('date') or Fund._meta.get_field('date').get_default(),
            description=data.get('note') or '',
        )
        return Response(fund_json(mess_funds(manager.mess).get(id=fund.id)), status=status.HTTP_201_CREATED)


class AdminFundDetailView(APIView):
    """
    PATCH  /api/v1/admin/funds/<id>  {amount?, date?, note?}
    DELETE /api/v1/admin/funds/<id>
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get(self, request, pk):
        manager = get_managed_membership(request.user)
        fund = mess_funds(manager.mess).filter(id=pk).first()
        if not fund:
            raise NotFound("Fund entry not found in your mess.")
        return fund

    def patch(self, request, pk):
        fund = self._get(request, pk)
        serializer = FundWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if 'date' in data:
            fund.date = data['date']
        if 'amount' in data:
            fund.amount = data['amount']
        if 'note' in data:
            fund.description = data['note'] or ''
        fund.recorded_by = request.user
        fund.save()
        return Response(fund_json(mess_funds(fund.mess).get(id=fund.id)))

    def delete(self, request, pk):
        fund = self._get(request, pk)
        fund.delete()
        return Response({"message": "Fund entry deleted."})
