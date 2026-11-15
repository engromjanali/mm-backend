from django.contrib import admin

from .models import Feedback, FeedbackImage, FeedbackComment


class FeedbackImageInline(admin.TabularInline):
    model = FeedbackImage
    extra = 0
    readonly_fields = ('image', 'created_at')


class FeedbackCommentInline(admin.TabularInline):
    model = FeedbackComment
    extra = 0
    readonly_fields = ('user', 'comment', 'image', 'created_at')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'is_public', 'created_at')
    list_editable = ('is_public',)
    list_filter = ('is_public', 'created_at')
    search_fields = ('user__full_name', 'user__email', 'description')
    readonly_fields = ('user', 'description', 'created_at')
    inlines = [FeedbackImageInline, FeedbackCommentInline]
    ordering = ('-created_at',)


@admin.register(FeedbackComment)
class FeedbackCommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'feedback', 'user', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__full_name', 'user__email', 'comment')
    readonly_fields = ('feedback', 'user', 'comment', 'image', 'created_at')
    ordering = ('-created_at',)
