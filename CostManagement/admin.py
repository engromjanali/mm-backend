from django.contrib import admin

# Register your models here.
from .models import Cost, CostBreakdown

admin.site.register(Cost)
admin.site.register(CostBreakdown)