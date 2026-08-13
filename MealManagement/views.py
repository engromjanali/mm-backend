from django.db.models import Sum
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from MessManagement.utils import get_verified_membership_and_season
from .models import Meals
from .serializers import MealsSerializer, MealWriteSerializer
from .utils import (
    DATE_OUTPUT_FORMAT,
    apply_date_filters,
    get_pagination_params,
    parse_date_value,
)


def _summarise(queryset):
    """Aggregate meal counts across a (pre-pagination) queryset."""
    totals = queryset.aggregate(
        breakfast=Sum('breakfast'),
        lunch=Sum('lunch'),
        dinner=Sum('dinner'),
        total_meals=Sum('total_meals'),
    )
    return {key: value or 0 for key, value in totals.items()}


def _format_filters(applied):
    """Renders the resolved date filters back to the client in DD-MM-YYYY."""
    return {
        key: value.strftime(DATE_OUTPUT_FORMAT) if value else None
        for key, value in applied.items()
    }


def _resolve_meal(request, membership, season, pk=None):
    """
    Locates the meal row a write is targeting, either by its own id
    (`meal_id` / `id`, or the URL pk) or by the `membership_id` + `date` pair.
    Returns ``(meal, error_response)`` — exactly one of which is None.
    """
    meal_id = pk or request.data.get('meal_id') or request.data.get('id')

    if meal_id:
        try:
            meal = Meals.objects.select_related('mess_member__user').get(
                id=meal_id,
                mess_season=season,
                mess_member__mess=membership.mess,
            )
        except (Meals.DoesNotExist, ValueError, TypeError):
            return None, Response(
                {"error": "Meal entry not found in this session."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return meal, None

    membership_id = request.data.get('membership_id')
    raw_date = request.data.get('date')

    if not membership_id or not raw_date:
        return None, Response(
            {"error": "Provide either meal_id, or both membership_id and date."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    date_value = parse_date_value(raw_date, 'date')

    try:
        meal = Meals.objects.select_related('mess_member__user').get(
            mess_season=season,
            mess_member__mess=membership.mess,
            mess_member_id=membership_id,
            date=date_value,
        )
    except (Meals.DoesNotExist, ValueError, TypeError):
        return None, Response(
            {"error": "No meal entry found for this member on the given date."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return meal, None


class MealAddView(APIView):
    """
    POST /api/v1/meal/add

    Records a meal entry for one member on one date within the session taken
    from the `Session-ID` header. Manager / Acting Manager only.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        membership, season = get_verified_membership_and_season(request, require_write=True)

        serializer = MealWriteSerializer(
            data=request.data,
            context={'request': request, 'membership': membership, 'season': season},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        meal = serializer.save()
        return Response(
            {"message": "Meal added successfully.", "data": MealsSerializer(meal).data},
            status=status.HTTP_201_CREATED,
        )


class MealUpdateView(APIView):
    """
    PUT / PATCH / POST /api/v1/meal/update  (or /api/v1/meal/update/<int:pk>/)

    Targets a row by `meal_id`, or by `membership_id` + `date`.
    Manager / Acting Manager only.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _update_meal(self, request, pk=None, partial=False):
        membership, season = get_verified_membership_and_season(request, require_write=True)

        meal, error = _resolve_meal(request, membership, season, pk=pk)
        if error:
            return error

        serializer = MealWriteSerializer(
            meal,
            data=request.data,
            partial=partial,
            context={'request': request, 'membership': membership, 'season': season},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        meal = serializer.save()
        return Response(
            {"message": "Meal updated successfully.", "data": MealsSerializer(meal).data},
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk=None, *args, **kwargs):
        return self._update_meal(request, pk=pk, partial=False)

    def patch(self, request, pk=None, *args, **kwargs):
        return self._update_meal(request, pk=pk, partial=True)

    def post(self, request, pk=None, *args, **kwargs):
        return self._update_meal(request, pk=pk, partial=True)


class MealDeleteView(APIView):
    """
    DELETE / POST /api/v1/meal/delete  (or /api/v1/meal/delete/<int:pk>/)

    Targets a row by `meal_id`, or by `membership_id` + `date`.
    Manager / Acting Manager only.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _delete_meal(self, request, pk=None):
        membership, season = get_verified_membership_and_season(request, require_write=True)

        meal, error = _resolve_meal(request, membership, season, pk=pk)
        if error:
            return error

        deleted = MealsSerializer(meal).data
        meal.delete()
        return Response(
            {"message": "Meal deleted successfully.", "data": deleted},
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk=None, *args, **kwargs):
        return self._delete_meal(request, pk=pk)

    def post(self, request, pk=None, *args, **kwargs):
        return self._delete_meal(request, pk=pk)


class MealListView(APIView):
    """
    GET /api/v1/meal/list?date=10-10-2020
    GET /api/v1/meal/list?start_date=10-10-2020&end_date=20-10-2023

    The caller's own meals for the session in the `Session-ID` header.
    Available to every active member.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        membership, season = get_verified_membership_and_season(request, require_write=False)

        queryset = Meals.objects.select_related('mess_member__user').filter(
            mess_season=season,
            mess_member=membership,
        )
        queryset, applied = apply_date_filters(queryset, request)

        total_size = queryset.count()
        summary = _summarise(queryset)
        limit, offset, start, end = get_pagination_params(request)

        return Response({
            "total_size": total_size,
            "limit": limit,
            "offset": offset,
            "filters": _format_filters(applied),
            "summary": summary,
            "data": MealsSerializer(queryset[start:end], many=True).data,
        })


class MealListAllView(APIView):
    """
    GET /api/v1/meal/list-all?date=10-10-2020
    GET /api/v1/meal/list-all?start_date=10-10-2020&end_date=20-10-2023

    Every member's meals for the session, optionally narrowed to one member
    with `membership_id`. Available to every active member.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        membership, season = get_verified_membership_and_season(request, require_write=False)

        queryset = Meals.objects.select_related('mess_member__user').filter(
            mess_season=season,
            mess_member__mess=membership.mess,
        )

        membership_id = request.query_params.get('membership_id')
        if membership_id:
            if not str(membership_id).strip().isdigit():
                return Response(
                    {"error": "membership_id must be a valid integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(mess_member_id=int(membership_id))

        queryset, applied = apply_date_filters(queryset, request)

        total_size = queryset.count()
        summary = _summarise(queryset)
        limit, offset, start, end = get_pagination_params(request)

        # Per-member roll-up across the whole filtered range, not just this page.
        member_totals = (
            queryset
            .values('mess_member_id', 'mess_member__user__full_name', 'mess_member__role')
            .annotate(
                breakfast=Sum('breakfast'),
                lunch=Sum('lunch'),
                dinner=Sum('dinner'),
                total_meals=Sum('total_meals'),
            )
            .order_by('mess_member__user__full_name')
        )

        return Response({
            "total_size": total_size,
            "limit": limit,
            "offset": offset,
            "filters": _format_filters(applied),
            "summary": summary,
            "member_summary": [
                {
                    "membership_id": row['mess_member_id'],
                    "member_name": row['mess_member__user__full_name'],
                    "member_role": row['mess_member__role'],
                    "breakfast": row['breakfast'] or 0,
                    "lunch": row['lunch'] or 0,
                    "dinner": row['dinner'] or 0,
                    "total_meals": row['total_meals'] or 0,
                }
                for row in member_totals
            ],
            "data": MealsSerializer(queryset[start:end], many=True).data,
        })


class MealDetailView(APIView):
    """
    GET /api/v1/meal/{id}

    A single meal row from the caller's mess and session.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        membership, season = get_verified_membership_and_season(request, require_write=False)

        try:
            meal = Meals.objects.select_related('mess_member__user').get(
                id=pk,
                mess_season=season,
                mess_member__mess=membership.mess,
            )
        except Meals.DoesNotExist:
            return Response(
                {"error": "Meal entry not found in this session."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(MealsSerializer(meal).data, status=status.HTTP_200_OK)
