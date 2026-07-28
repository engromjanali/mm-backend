from django.db import models
from MessManagement.models import MessSeason, Mess

# Create your models here.

class FundsBreakdown(models.Model):
    mess = models.OneToOneField(Mess, on_delete=models.CASCADE, related_name='funds_breakdown_mess')
    season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='funds_season')
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    type = models.CharField(max_length=20, choices=[('income', 'Income'), ('expense', 'Expense')], default='income')
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Funds(models.Model):
    mess = models.OneToOneField(Mess, on_delete=models.CASCADE, related_name='funds_mess')
    funds = models.ForeignKey(FundsBreakdown, on_delete=models.CASCADE, related_name='funds_breakdown')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)
