from django.contrib import admin

from ContentManagement.models import AppSetting, ContentPage, Faq, SupportChannel


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    """A single row: opening the list goes straight to it; it can't be added twice or deleted."""
    fieldsets = (
        ("App version", {"fields": ("latest_version", "minimum_version", "update_message", "android_store_url", "ios_store_url")}),
        ("Maintenance", {"fields": ("maintenance_mode", "maintenance_message", "maintenance_until")}),
    )
    list_display = ["__str__", "latest_version", "minimum_version", "maintenance_mode", "updated_at"]

    def has_add_permission(self, request):
        return not AppSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContentPage)
class ContentPageAdmin(admin.ModelAdmin):
    list_display = ["kind", "language", "title", "updated_at"]
    list_filter = ["kind", "language"]


@admin.register(Faq)
class FaqAdmin(admin.ModelAdmin):
    list_display = ["question", "language", "order", "is_active", "updated_at"]
    list_filter = ["language", "is_active"]
    list_editable = ["order", "is_active"]
    search_fields = ["question", "answer"]


@admin.register(SupportChannel)
class SupportChannelAdmin(admin.ModelAdmin):
    list_display = ['name', 'kind', 'destination', 'order', 'is_active']
    list_filter = ['kind', 'is_active']
    list_editable = ['order', 'is_active']
    search_fields = ['name', 'destination']
    fieldsets = (
        ('Contact', {'fields': ('name', 'kind', 'destination', 'logo')}),
        ('Visibility', {'fields': ('is_active', 'order')}),
    )
