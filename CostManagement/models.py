from django.db import models
from MessManagement.models import MessSeason, MessMemberShip

# Create your models here.

class Cost(models.Model):
    season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='costs_season')
    performed_by = models.ForeignKey(MessMemberShip, on_delete=models.CASCADE, related_name='costs_performed')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CostBreakdown(models.Model):
    cost = models.ForeignKey(Cost, on_delete=models.CASCADE, related_name='breakdowns')
    name = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)




