from django.db import models
from MessManagement.models import MessSeason, MessMemberShip
# Create your models here.


class Deposit(models.Model):
    season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='deposits_season')
    performed_by = models.ForeignKey(MessMemberShip, on_delete=models.CASCADE, related_name='deposits_performed')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=[('cash', 'Cash'), ('bank_transfer', 'Bank Transfer'), ('mobile_payment', 'Mobile Payment')], default='cash')
    description = models.TextField(blank=True, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)