from django.db import models
from MessManagement.models import MessSeason, MessMemberShip

# Create your models here.

class Meals(models.Model):
    mess_season = models.ForeignKey(MessSeason, on_delete=models.CASCADE)
    mess_member = models.ForeignKey(MessMemberShip, on_delete=models.CASCADE)
    date = models.CharField(max_length=10, null=False, blank=False)
    breakfast = models.IntegerField(default=0)
    lunch = models.IntegerField(default=0)
    dinner = models.IntegerField(default=0)
    total_meals = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)    
    updated_at = models.DateTimeField(auto_now=True)


    

