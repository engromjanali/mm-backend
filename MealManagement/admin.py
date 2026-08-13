from django.contrib import admin

# Register your models here.
from .models import Meals


@admin.register(Meals)
class MealsAdmin(admin.ModelAdmin):
    list_display = ('id', 'mess_season', 'mess_member', 'date', 'breakfast', 'lunch', 'dinner', 'total_meals')
    list_filter = ('mess_season', 'date')
    search_fields = ('mess_member__user__full_name', 'mess_member__user__email')
    date_hierarchy = 'date'
