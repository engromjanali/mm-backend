from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from MessManagement.membership_views import get_managed_membership
from MessManagement.models import MessMemberShip
from MessManagement.utils import get_active_membership, get_verified_membership_and_season
from .models import Meals
from .serializers import (
    AdminMealBulkSerializer,
    AdminMealItemSerializer,
    AdminMealKeySerializer,
    AdminMealUpdateSerializer,
    MealsSerializer,
    MealWriteSerializer,
)
from .utils import (
    DATE_OUTPUT_FORMAT,
    MEAL_SLOTS,
    MealConflict,
    apply_date_filters,
    get_pagination_params,
    parse_date_value,
    season_meal_rate,
    validate_has_meal,
    validate_meal_date,
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


# ---------------------------------------------------------------------------
# Session-header endpoints  (/api/v1/meal/...)  — `Membership-ID` + `Session-ID`
# ---------------------------------------------------------------------------

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
            .values('mess_member_id', 'mess_member__user__full_name', 'mess_member__user_id')
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
                    "member_role": membership.mess.role_of(row['mess_member__user_id']),
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


# ---------------------------------------------------------------------------
# User endpoints  (/api/v1/user/...)
# ---------------------------------------------------------------------------

class MyMealListView(APIView):
    """
    GET /api/v1/user/meals

    The caller's own meals in their active season (a manager is a member too),
    with the season's meal rate and the caller's totals.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        membership = get_active_membership(request.user)
        if not membership:
            raise ValidationError({"detail": "You are not connected to an active mess."})
        season = membership.season
        meals = Meals.objects.filter(mess_season=season, mess_member=membership)
        meal_rate, _, _ = season_meal_rate(season)
        my_total = meals.aggregate(total=Sum('total_meals'))['total'] or Decimal('0')

        return Response({
            "season": {"id": season.id, "name": season.name},
            "user_name": request.user.full_name,
            "meal_rate": float(meal_rate),
            "summary": {
                "total_meals": float(my_total),
                "meal_cost": float((my_total * meal_rate).quantize(Decimal('0.01'))),
                "days": meals.count(),
            },
            "days": [
                {
                    "date": meal.date.isoformat(),
                    "breakfast": float(meal.breakfast),
                    "lunch": float(meal.lunch),
                    "dinner": float(meal.dinner),
                    "total": float(meal.total_meals),
                }
                for meal in meals
            ],
        })


# ---------------------------------------------------------------------------
# Admin endpoints  (/api/v1/admin/...)  — manager / acting manager only
# ---------------------------------------------------------------------------

def _day(date_value):
    return date_value.strftime(DATE_OUTPUT_FORMAT)


def _is_active(member):
    return member.status == 'active' and member.left_at is None


def _season_member(season, member_id):
    return MessMemberShip.objects.select_related('user', 'mess').filter(id=member_id, season=season).first()


def _admin_member(season, member_id, field='member_id', require_active=False):
    """The season member ``member_id`` points at; active only when adding meals."""
    member = _season_member(season, member_id)
    if not member:
        raise ValidationError({field: "No member with this ID in the current season."})
    if require_active and not _is_active(member):
        raise ValidationError({field: f"{member.user.full_name} is no longer an active member of this season."})
    return member


def _admin_meal(season, member, date_value):
    meal = Meals.objects.filter(mess_season=season, mess_member=member, date=date_value).first()
    if not meal:
        raise NotFound(f"{member.user.full_name} has no meal on {_day(date_value)}.")
    return meal


def _first_error(errors):
    """First readable message of a serializer's errors, naming bare required fields."""
    field, messages = next(iter(errors.items()))
    message = str(messages[0] if isinstance(messages, list) else messages)
    return f"{field} is required." if message == "This field is required." else message


def _admin_meal_json(meal):
    return {
        "id": meal.id,
        "member_id": meal.mess_member_id,
        "member_name": meal.mess_member.user.full_name,
        "date": meal.date.isoformat(),
        "breakfast": float(meal.breakfast),
        "lunch": float(meal.lunch),
        "dinner": float(meal.dinner),
        "total": float(meal.total_meals),
    }


def _admin_meal_payload(season, mutation=None, message=None):
    """
    Everything the manage-meals view needs: the season's members (the manager
    included, plus anyone who left but still has meals), the meal rate
    (season cost ÷ season meals) and every meal record of the season.
    """
    meals = Meals.objects.select_related('mess_member__user').filter(mess_season=season)
    members = (
        MessMemberShip.objects.select_related('user', 'mess')
        .filter(season=season)
        .filter(Q(status='active', left_at__isnull=True) | Q(meals__mess_season=season))
        .distinct()
        .order_by('user__full_name')
    )
    meal_rate, total_meals, total_cost = season_meal_rate(season)

    payload = {
        "season": {"id": season.id, "name": season.name},
        "members": [
            {"id": m.id, "name": m.user.full_name, "role": m.role, "active": _is_active(m)}
            for m in members
        ],
        "meal_rate": float(meal_rate),
        "summary": {"total_meals": float(total_meals), "total_cost": float(total_cost), "entries": meals.count()},
        "entries": [_admin_meal_json(meal) for meal in meals],
    }
    if mutation:
        payload["mutation"] = mutation
    if message:
        payload["message"] = message
    return payload


class AdminMealView(APIView):
    """
    GET    /api/v1/admin/meals
           Members, meal rate and every meal record of the active season.
    PATCH  /api/v1/admin/meals  {member_id, date, breakfast?, lunch?, dinner?}
           Change a member's meal on a date (the date itself can't change).
    DELETE /api/v1/admin/meals  {member_id, date}  (body or query params)

    Writes return the same payload as GET plus ``mutation`` and ``message``.
    New meals are added a day at a time with ``POST /api/v1/admin/meals/bulk``.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        manager = get_managed_membership(request.user)
        return Response(_admin_meal_payload(manager.season))

    def patch(self, request):
        manager = get_managed_membership(request.user)
        serializer = AdminMealUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not any(slot in data for slot in MEAL_SLOTS):
            raise ValidationError({"detail": "Send breakfast, lunch or dinner to update."})

        member = _admin_member(manager.season, data['member_id'])
        meal = _admin_meal(manager.season, member, data['date'])
        counts = {slot: data.get(slot, getattr(meal, slot)) for slot in MEAL_SLOTS}
        validate_has_meal(counts, "A meal can't be all zero. Delete it instead.")

        for slot, value in counts.items():
            setattr(meal, slot, value)
        meal.save()
        return Response(_admin_meal_payload(
            manager.season,
            mutation={"action": "update", "created_count": 0, "updated_count": 1},
            message=f"Meal updated for {member.user.full_name} on {_day(meal.date)}.",
        ))

    def delete(self, request):
        manager = get_managed_membership(request.user)
        serializer = AdminMealKeySerializer(data=request.data or request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        member = _admin_member(manager.season, data['member_id'])
        meal = _admin_meal(manager.season, member, data['date'])
        meal.delete()
        return Response(_admin_meal_payload(
            manager.season,
            mutation={"action": "delete", "created_count": 0, "updated_count": 0},
            message=f"Meal deleted for {member.user.full_name} on {_day(data['date'])}.",
        ))


class AdminMealBulkView(APIView):
    """
    POST /api/v1/admin/meals/bulk
         {date, meals: [{member_id, breakfast, lunch, dinner}, ...]}

    Adds a day's meals for the listed members in one transaction — all rows
    or none. Add-only: a day that already has meals is rejected with 409 and
    edited per record instead.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        manager = get_managed_membership(request.user)
        season = manager.season
        serializer = AdminMealBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        date_value = validate_meal_date(serializer.validated_data['date'], season)

        rows = []
        seen = set()
        for index, raw in enumerate(serializer.validated_data['meals'], start=1):
            if not isinstance(raw, dict):
                raise ValidationError({"meals": f"Row {index} must be an object with member_id, breakfast, lunch and dinner."})
            item = AdminMealItemSerializer(data=raw)
            if not item.is_valid():
                raise ValidationError({"meals": f"Row {index}: {_first_error(item.errors)}"})
            data = item.validated_data

            member = _season_member(season, data['member_id'])
            if not member:
                raise ValidationError({"meals": f"Row {index}: no member with ID {data['member_id']} in the current season."})
            name = member.user.full_name
            if not _is_active(member):
                raise ValidationError({"meals": f"{name} is no longer an active member of this season."})
            if member.id in seen:
                raise ValidationError({"meals": f"{name} is listed more than once."})
            seen.add(member.id)

            counts = {slot: data.get(slot, Decimal('0')) for slot in MEAL_SLOTS}
            validate_has_meal(counts, f"Add at least one meal for {name}.")
            rows.append((member, counts))

        already_added = MealConflict(f"Meals for {_day(date_value)} are already added. Edit them from Manage meals.")
        if Meals.objects.filter(mess_season=season, date=date_value).exists():
            raise already_added
        try:
            with transaction.atomic():
                for member, counts in rows:
                    # save() (not bulk_create) so total_meals is derived per row.
                    Meals(mess_season=season, mess_member=member, date=date_value, **counts).save()
        except IntegrityError:
            # Another request added this day between the check and the insert.
            raise already_added

        count = len(rows)
        return Response(
            _admin_meal_payload(
                season,
                mutation={"action": "add", "created_count": count, "updated_count": 0},
                message=f"Meal added for {count} member{'s' if count != 1 else ''} on {_day(date_value)}.",
            ),
            status=status.HTTP_201_CREATED,
        )
