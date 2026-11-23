from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from MessManagement.models import MessSeason, MessMemberShip

# Create your models here.

class Meals(models.Model):
    mess_season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='meals')
    mess_member = models.ForeignKey(MessMemberShip, on_delete=models.CASCADE, related_name='meals')
    date = models.DateField()
    # Half meals are allowed (0.5 steps), so counts are one-decimal values.
    breakfast = models.DecimalField(max_digits=3, decimal_places=1, default=0, validators=[MinValueValidator(0)])
    lunch = models.DecimalField(max_digits=3, decimal_places=1, default=0, validators=[MinValueValidator(0)])
    dinner = models.DecimalField(max_digits=3, decimal_places=1, default=0, validators=[MinValueValidator(0)])
    total_meals = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meals'
        # One meal sheet row per member per day within a season.
        unique_together = ('mess_season', 'mess_member', 'date')
        ordering = ['-date', '-id']

    def save(self, *args, **kwargs):
        # total_meals is always derived, never trusted from the client.
        self.total_meals = (self.breakfast or 0) + (self.lunch or 0) + (self.dinner or 0)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields) | {'total_meals'}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.mess_member_id} | {self.date} | {self.total_meals}"


class MealRequestCampaign(models.Model):
    """
    A dated request the manager opens so members can confirm the meals they
    will have. Responses are open until ``end_at`` (or until the manager closes
    the request). Several requests may share a date.
    """

    mess_season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='meal_request_campaigns')
    date = models.DateField()
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, default='')
    end_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_meal_request_campaigns')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meal_request_campaigns'
        ordering = ['-date', '-id']

    @property
    def is_closed(self):
        from django.utils import timezone

        return self.closed_at is not None or self.end_at <= timezone.now()

    @property
    def status(self):
        return 'closed' if self.is_closed else 'open'

    def __str__(self):
        return f"{self.title} | {self.date}"


class MealRequestSelection(models.Model):
    """One member's meal counts for a meal request."""

    request = models.ForeignKey(MealRequestCampaign, on_delete=models.CASCADE, related_name='selections')
    mess_member = models.ForeignKey(MessMemberShip, on_delete=models.CASCADE, related_name='meal_request_selections')
    breakfast = models.DecimalField(max_digits=3, decimal_places=1, default=0, validators=[MinValueValidator(0)])
    lunch = models.DecimalField(max_digits=3, decimal_places=1, default=0, validators=[MinValueValidator(0)])
    dinner = models.DecimalField(max_digits=3, decimal_places=1, default=0, validators=[MinValueValidator(0)])
    total_meals = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meal_request_selections'
        unique_together = ('request', 'mess_member')
        ordering = ['request', 'mess_member__user__full_name', 'id']

    def save(self, *args, **kwargs):
        self.total_meals = (self.breakfast or 0) + (self.lunch or 0) + (self.dinner or 0)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields) | {'total_meals'}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.request_id} | {self.mess_member_id} | {self.total_meals}"
