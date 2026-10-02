from django.db import models
from django.utils import timezone
from MessManagement.models import MessSeason, MessMemberShip
# Create your models here.


class Deposit(models.Model):
    """
    Money a member put into (positive ``amount`` = credit) or took out of
    (negative ``amount`` = debit) the mess account during a season.
    """
    season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='deposits_season')
    # The member the deposit belongs to (a manager is also a member).
    performed_by = models.ForeignKey(MessMemberShip, on_delete=models.CASCADE, related_name='deposits_performed')
    # Manager / acting manager who entered the record.
    recorded_by = models.ForeignKey(MessMemberShip, on_delete=models.SET_NULL, null=True, blank=True, related_name='deposits_recorded')
    date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=[('cash', 'Cash'), ('bank_transfer', 'Bank Transfer'), ('mobile_payment', 'Mobile Payment')], default='cash')
    description = models.TextField(blank=True, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'deposits'
        ordering = ['-date', '-id']