from django.db import models
from django.utils import timezone
from MessManagement.models import MessSeason, MessMemberShip


class Fund(models.Model):
    """
    A shared mess-fund entry for a season. It isn't tied to a member: a
    positive ``amount`` is a credit (money into the fund), a negative amount
    a debit (money taken out).
    """
    season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='funds')
    date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    # Manager / acting manager who entered or last edited the record.
    recorded_by = models.ForeignKey(MessMemberShip, on_delete=models.SET_NULL, null=True, blank=True, related_name='funds_recorded')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'funds'
        ordering = ['-date', '-id']
