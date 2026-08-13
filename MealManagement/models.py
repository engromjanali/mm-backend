from django.core.validators import MinValueValidator
from django.db import models
from MessManagement.models import MessSeason, MessMemberShip

# Create your models here.

class Meals(models.Model):
    mess_season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='meals')
    mess_member = models.ForeignKey(MessMemberShip, on_delete=models.CASCADE, related_name='meals')
    date = models.DateField()
    breakfast = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    lunch = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    dinner = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    total_meals = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
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
