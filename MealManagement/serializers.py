from rest_framework import serializers

from MessManagement.models import MessMemberShip
from .models import Meals
from .utils import DATE_INPUT_FORMATS, DATE_OUTPUT_FORMAT, validate_date_in_season, validate_meal_count


class MealsSerializer(serializers.ModelSerializer):
    """
    Read serializer for a single meal row, flattened with the member's
    identity so the client does not need a second lookup to render a sheet.
    """
    date = serializers.DateField(format=DATE_OUTPUT_FORMAT, read_only=True)
    season_id = serializers.IntegerField(source='mess_season_id', read_only=True)
    membership_id = serializers.IntegerField(source='mess_member_id', read_only=True)
    member_name = serializers.CharField(source='mess_member.user.full_name', read_only=True)
    member_role = serializers.CharField(source='mess_member.role', read_only=True)
    # Numbers (not DRF's default decimal strings) so clients read 1.5 directly.
    breakfast = serializers.DecimalField(max_digits=3, decimal_places=1, coerce_to_string=False, read_only=True)
    lunch = serializers.DecimalField(max_digits=3, decimal_places=1, coerce_to_string=False, read_only=True)
    dinner = serializers.DecimalField(max_digits=3, decimal_places=1, coerce_to_string=False, read_only=True)
    total_meals = serializers.DecimalField(max_digits=4, decimal_places=1, coerce_to_string=False, read_only=True)

    class Meta:
        model = Meals
        fields = [
            'id', 'season_id', 'membership_id', 'member_name', 'member_role',
            'date', 'breakfast', 'lunch', 'dinner', 'total_meals',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class MealWriteSerializer(serializers.ModelSerializer):
    """
    Write serializer for add / update.

    Expects ``membership`` (the caller's verified membership) and ``season``
    (the verified MessSeason) in the serializer context. ``membership_id``
    identifies the member the meal belongs to — writes are Manager / Acting
    Manager only, so it is never inferred from the caller.
    """
    membership_id = serializers.IntegerField()
    date = serializers.DateField(input_formats=DATE_INPUT_FORMATS, format=DATE_OUTPUT_FORMAT)
    breakfast = serializers.DecimalField(max_digits=3, decimal_places=1, required=False, default=0)
    lunch = serializers.DecimalField(max_digits=3, decimal_places=1, required=False, default=0)
    dinner = serializers.DecimalField(max_digits=3, decimal_places=1, required=False, default=0)

    class Meta:
        model = Meals
        fields = ['membership_id', 'date', 'breakfast', 'lunch', 'dinner']

    def validate_membership_id(self, value):
        caller_membership = self.context['membership']
        try:
            return MessMemberShip.objects.select_related('user').get(
                id=value,
                mess=caller_membership.mess,
                status='active',
            )
        except MessMemberShip.DoesNotExist:
            raise serializers.ValidationError(
                "No active member with this membership_id exists in your mess."
            )

    def validate_date(self, value):
        return validate_date_in_season(value, self.context['season'])

    def validate_breakfast(self, value):
        return validate_meal_count(value, 'breakfast')

    def validate_lunch(self, value):
        return validate_meal_count(value, 'lunch')

    def validate_dinner(self, value):
        return validate_meal_count(value, 'dinner')

    def validate(self, attrs):
        season = self.context['season']
        # On a partial update these fall back to the row already on disk.
        target_member = attrs.get('membership_id') or getattr(self.instance, 'mess_member', None)
        date_value = attrs.get('date') or getattr(self.instance, 'date', None)

        if target_member and date_value:
            duplicate = Meals.objects.filter(
                mess_season=season,
                mess_member=target_member,
                date=date_value,
            )
            if self.instance is not None:
                duplicate = duplicate.exclude(pk=self.instance.pk)

            if duplicate.exists():
                raise serializers.ValidationError({
                    'date': (
                        f"A meal entry already exists for this member on "
                        f"{date_value.strftime(DATE_OUTPUT_FORMAT)}. Use the update API instead."
                    )
                })

        return attrs

    def _apply(self, instance, validated_data):
        if 'membership_id' in validated_data:
            instance.mess_member = validated_data['membership_id']
        if 'date' in validated_data:
            instance.date = validated_data['date']
        for field in ('breakfast', 'lunch', 'dinner'):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        return instance

    def create(self, validated_data):
        meal = self._apply(Meals(mess_season=self.context['season']), validated_data)
        meal.save()
        return meal

    def update(self, instance, validated_data):
        self._apply(instance, validated_data).save()
        return instance

    def to_representation(self, instance):
        return MealsSerializer(instance).data


# ---------------------------------------------------------------------------
# Admin endpoints  (/api/v1/admin/meals...)
# ---------------------------------------------------------------------------

class AdminMealCountsSerializer(serializers.Serializer):
    """
    Breakfast / lunch / dinner counts. Wider digit limits than the model so
    out-of-range values get the friendlier range / half-meal message.
    """
    breakfast = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
    lunch = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
    dinner = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)

    def validate_breakfast(self, value):
        return validate_meal_count(value, 'breakfast')

    def validate_lunch(self, value):
        return validate_meal_count(value, 'lunch')

    def validate_dinner(self, value):
        return validate_meal_count(value, 'dinner')


class AdminMealKeySerializer(serializers.Serializer):
    """Identifies one record: a member's meal on a date (unique per season)."""
    member_id = serializers.IntegerField()
    date = serializers.DateField(input_formats=DATE_INPUT_FORMATS)


class AdminMealUpdateSerializer(AdminMealKeySerializer, AdminMealCountsSerializer):
    """PATCH body: the record key plus whichever counts change."""


class AdminMealItemSerializer(AdminMealCountsSerializer):
    """One member's row in a bulk day entry."""
    member_id = serializers.IntegerField()


class AdminMealBulkSerializer(serializers.Serializer):
    """
    POST body for a day: ``meals`` rows are validated one by one in the view
    so each error names its row and member.
    """
    date = serializers.DateField(input_formats=DATE_INPUT_FORMATS)
    meals = serializers.ListField(allow_empty=False)
