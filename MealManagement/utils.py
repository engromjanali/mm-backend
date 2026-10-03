from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from CostManagement.models import Cost
from .models import Meals

# `10-10-2020` (day-month-year) is the format the meal APIs are documented with.
# The ISO form is accepted too so browser date inputs work without conversion.
DATE_INPUT_FORMATS = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d']
DATE_OUTPUT_FORMAT = '%d-%m-%Y'

# Meal counts per slot: 0–3 in half-meal steps, matching the app's stepper.
MEAL_SLOTS = ('breakfast', 'lunch', 'dinner')
MEAL_STEP = Decimal('0.5')
MAX_MEALS_PER_SLOT = Decimal('3')


class MealConflict(APIException):
    """409 — the meal record (or day) being added already exists."""
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This meal entry already exists."
    default_code = 'conflict'


def parse_date_value(value, field_name='date'):
    """
    Parses a date string coming from a query parameter into a ``datetime.date``.
    Raises a DRF ValidationError (400) rather than blowing up with a ValueError.
    """
    if value is None:
        return None

    value = str(value).strip()
    if not value:
        return None

    for fmt in DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise ValidationError({
        field_name: f"Invalid date '{value}'. Expected format DD-MM-YYYY (e.g. 10-10-2020)."
    })


def validate_date_in_season(date_value, season, field_name='date'):
    """
    Ensures a meal date actually falls inside the season it is being recorded
    against. An open season (``end_date`` is null) only has a lower bound.
    """
    if date_value < season.start_date:
        raise ValidationError({
            field_name: (
                f"Date is before the season started "
                f"({season.start_date.strftime(DATE_OUTPUT_FORMAT)})."
            )
        })

    if season.end_date and date_value > season.end_date:
        raise ValidationError({
            field_name: (
                f"Date is after the season ended "
                f"({season.end_date.strftime(DATE_OUTPUT_FORMAT)})."
            )
        })

    return date_value


def validate_meal_count(value, field_name):
    """
    One slot's count: 0 to MAX_MEALS_PER_SLOT, in half-meal steps. Meant for a
    serializer's ``validate_<slot>``, so it raises a plain message.
    """
    label = field_name.capitalize()
    if value < 0 or value > MAX_MEALS_PER_SLOT:
        raise ValidationError(f"{label} must be between 0 and {MAX_MEALS_PER_SLOT:g} meals.")
    if value % MEAL_STEP != 0:
        raise ValidationError(f"{label} must be a whole or half meal (e.g. 1 or 1.5).")
    return value


def validate_has_meal(counts, message="Add at least one meal (breakfast, lunch or dinner)."):
    """Rejects a record whose breakfast, lunch and dinner are all zero."""
    if not any(counts.get(slot) for slot in MEAL_SLOTS):
        raise ValidationError({"detail": message})


def validate_meal_date(date_value, season, field_name='date'):
    """
    A meal date must be inside the season and not in the future. The server
    runs on UTC while members are ahead of it (e.g. UTC+6), so "today" is
    allowed up to one day past the server's date.
    """
    validate_date_in_season(date_value, season, field_name)
    if date_value > timezone.localdate() + timedelta(days=1):
        raise ValidationError({field_name: "Meals can't be added for a future date."})
    return date_value


def season_meal_rate(season):
    """
    ``(meal_rate, total_meals, total_cost)`` for a season: total cost ÷ total
    meals, ``0`` while no meals are recorded.
    """
    total_meals = Meals.objects.filter(mess_season=season).aggregate(total=Sum('total_meals'))['total'] or Decimal('0')
    total_cost = Cost.objects.filter(season=season).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    meal_rate = (total_cost / total_meals).quantize(Decimal('0.01')) if total_meals else Decimal('0')
    return meal_rate, total_meals, total_cost


def get_pagination_params(request, default_limit=20):
    """
    Reads `limit` / `offset` query params using the same 1-based `offset`
    (page number) convention as the rest of the project.
    """
    try:
        limit = int(request.query_params.get('limit', default_limit))
        if limit < 1:
            limit = default_limit
    except (TypeError, ValueError):
        limit = default_limit

    try:
        offset = int(request.query_params.get('offset', 1))
        if offset < 1:
            offset = 1
    except (TypeError, ValueError):
        offset = 1

    start = (offset - 1) * limit
    return limit, offset, start, start + limit


def apply_date_filters(queryset, request):
    """
    Applies the `date` / `start_date` / `end_date` query params to a Meals
    queryset. `date` (exact day) wins over the range parameters when both
    are supplied. Either end of the range may be omitted.
    """
    exact_date = parse_date_value(request.query_params.get('date'), 'date')
    if exact_date:
        return queryset.filter(date=exact_date), {'date': exact_date}

    start_date = parse_date_value(request.query_params.get('start_date'), 'start_date')
    end_date = parse_date_value(request.query_params.get('end_date'), 'end_date')

    if start_date and end_date and start_date > end_date:
        raise ValidationError({
            'start_date': "start_date cannot be later than end_date."
        })

    if start_date:
        queryset = queryset.filter(date__gte=start_date)
    if end_date:
        queryset = queryset.filter(date__lte=end_date)

    return queryset, {'start_date': start_date, 'end_date': end_date}
