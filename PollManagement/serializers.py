from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from MealManagement.utils import DATE_INPUT_FORMATS, validate_date_in_season

RESULTS_VISIBILITY = ('always', 'after_vote', 'after_close')
MIN_OPTIONS = 2
MAX_OPTIONS = 10


def local_today():
    """Today in the mess time zone, not the server's UTC date."""
    return timezone.now().astimezone(ZoneInfo(settings.MESS_TIME_ZONE)).date()


def default_closes_at(poll_date):
    """End of the poll date in the mess time zone."""
    end_of_day = datetime.combine(poll_date, time(23, 59, 59))
    return timezone.make_aware(end_of_day, ZoneInfo(settings.MESS_TIME_ZONE))


class PollWriteSerializer(serializers.Serializer):
    """
    Create / edit payload. ``season`` comes from the view's context, so a poll
    can only be created inside the manager's current season.
    """
    title = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')
    poll_date = serializers.DateField(input_formats=DATE_INPUT_FORMATS)
    closes_at = serializers.DateTimeField(required=False)
    options = serializers.ListField(child=serializers.CharField(max_length=100), required=False)
    allow_multiple = serializers.BooleanField(required=False)
    max_choices = serializers.IntegerField(min_value=1, required=False)
    is_anonymous = serializers.BooleanField(required=False)
    results_visibility = serializers.ChoiceField(choices=RESULTS_VISIBILITY, required=False)

    def validate_poll_date(self, value):
        season = self.context['season']
        validate_date_in_season(value, season, 'poll_date')
        if self.instance is None and value < local_today():
            raise serializers.ValidationError("Poll date cannot be in the past.")
        return value

    def validate_options(self, value):
        cleaned = []
        seen = set()
        for raw in value:
            text = (raw or '').strip()
            if not text:
                raise serializers.ValidationError("Options cannot be blank.")
            key = text.casefold()
            if key in seen:
                raise serializers.ValidationError(f'Duplicate option "{text}".')
            seen.add(key)
            cleaned.append(text)
        if len(cleaned) < MIN_OPTIONS:
            raise serializers.ValidationError(f"Add at least {MIN_OPTIONS} options.")
        if len(cleaned) > MAX_OPTIONS:
            raise serializers.ValidationError(f"Add at most {MAX_OPTIONS} options.")
        return cleaned

    def validate(self, attrs):
        season = self.context['season']
        is_create = self.instance is None
        poll_date = attrs.get('poll_date', getattr(self.instance, 'poll_date', None))
        options = attrs.get('options')
        if is_create and not options:
            raise serializers.ValidationError({'options': f"Add at least {MIN_OPTIONS} options."})

        option_count = len(options) if options is not None else self.instance.options.count()
        allow_multiple = attrs.get('allow_multiple', self.instance.allow_multiple if self.instance else False)
        max_choices = attrs.get('max_choices')
        if not allow_multiple:
            max_choices = 1
        else:
            if max_choices is None:
                max_choices = self.instance.max_choices if self.instance else option_count
                if max_choices < 2 and option_count > 1:
                    max_choices = option_count
            if max_choices < 1 or max_choices > option_count:
                raise serializers.ValidationError({
                    'max_choices': f"Max choices must be between 1 and {option_count}.",
                })
        attrs['max_choices'] = max_choices

        closes_at = attrs.get('closes_at')
        if closes_at is None:
            if is_create:
                closes_at = default_closes_at(poll_date)
                attrs['closes_at'] = closes_at
        else:
            if timezone.is_naive(closes_at):
                closes_at = timezone.make_aware(closes_at, ZoneInfo(settings.MESS_TIME_ZONE))
                attrs['closes_at'] = closes_at
            if poll_date and closes_at.astimezone(ZoneInfo(settings.MESS_TIME_ZONE)).date() < poll_date:
                raise serializers.ValidationError({'closes_at': "Deadline cannot be before the poll date."})
            if is_create and closes_at <= timezone.now():
                raise serializers.ValidationError({'closes_at': "Deadline must be in the future."})

        # `season` is only here so validate_poll_date can bound the date.
        attrs['season'] = season
        return attrs


class PollVoteSerializer(serializers.Serializer):
    option_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)

    def validate_option_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("An option can only be selected once.")
        return value


class PollCloseSerializer(serializers.Serializer):
    closed = serializers.BooleanField(required=False, default=True)
