from django.contrib import admin

from .models import Poll, PollOption, PollVote


class PollOptionInline(admin.TabularInline):
    model = PollOption
    extra = 0


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ('title', 'season', 'poll_date', 'closes_at', 'status', 'created_by')
    list_filter = ('results_visibility', 'is_anonymous', 'season')
    search_fields = ('title', 'description')
    inlines = [PollOptionInline]


@admin.register(PollVote)
class PollVoteAdmin(admin.ModelAdmin):
    list_display = ('poll', 'option', 'membership', 'created_at')
    list_filter = ('poll',)
