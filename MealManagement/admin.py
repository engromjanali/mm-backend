from django.contrib import admin

# Register your models here.
from .models import MealRequestCampaign, MealRequestSelection, Meals


@admin.register(Meals)
class MealsAdmin(admin.ModelAdmin):
    list_display = ('id', 'mess_season', 'mess_member', 'date', 'breakfast', 'lunch', 'dinner', 'total_meals')
    list_filter = ('mess_season', 'date')
    search_fields = ('mess_member__user__full_name', 'mess_member__user__email')
    date_hierarchy = 'date'


@admin.register(MealRequestCampaign)
class MealRequestCampaignAdmin(admin.ModelAdmin):
    list_display = ('id', 'mess_season', 'title', 'date', 'end_at', 'closed_at', 'created_by')
    list_filter = ('mess_season', 'date')
    search_fields = ('title',)
    date_hierarchy = 'date'


@admin.register(MealRequestSelection)
class MealRequestSelectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'request', 'mess_member', 'breakfast', 'lunch', 'dinner', 'total_meals')
    list_filter = ('request__mess_season',)
    search_fields = ('mess_member__user__full_name', 'mess_member__user__email')
