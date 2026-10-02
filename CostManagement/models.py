from django.db import models
from django.utils import timezone
from MessManagement.models import MessSeason, MessMemberShip


class Cost(models.Model):
    """
    One shopping (bazar) entry of a season: the member who did the shopping,
    when, and the products bought (``breakdowns``). ``amount`` is the sum of
    the products' prices.
    """
    season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='costs_season')
    # The member who did the shopping (a manager is also a member).
    performed_by = models.ForeignKey(MessMemberShip, on_delete=models.CASCADE, related_name='costs_performed')
    # Manager / acting manager who entered or last edited the record.
    recorded_by = models.ForeignKey(MessMemberShip, on_delete=models.SET_NULL, null=True, blank=True, related_name='costs_recorded')
    date = models.DateField(default=timezone.localdate)
    # Wall-clock shopping time (no time zone), optional.
    time = models.TimeField(null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'costs'
        ordering = ['-date', '-time', '-id']


class CostBreakdown(models.Model):
    """One product bought in a cost entry and its price."""
    cost = models.ForeignKey(Cost, on_delete=models.CASCADE, related_name='breakdowns')
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'cost_breakdowns'
        ordering = ['id']
