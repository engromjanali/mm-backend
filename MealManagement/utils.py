from datetime import datetime

from rest_framework.exceptions import ValidationError

# `10-10-2020` (day-month-year) is the format the meal APIs are documented with.
# The ISO form is accepted too so browser date inputs work without conversion.
DATE_INPUT_FORMATS = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d']
DATE_OUTPUT_FORMAT = '%d-%m-%Y'


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
