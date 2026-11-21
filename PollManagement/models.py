from django.conf import settings
from django.db import models
from django.utils import timezone

from MessManagement.models import MessMemberShip, MessSeason


class Poll(models.Model):
    """
    A dated question the manager opens for the members of one season.

    A poll is scoped to a season (like meals) and tied to a date so the app can
    show the nearest polls first. Several polls may share a date: each is a
    separate question. A poll is open until ``closes_at`` unless the manager
    closes it earlier or cancels it.
    """
    season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='polls')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_polls')
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    poll_date = models.DateField()
    closes_at = models.DateTimeField()
    allow_multiple = models.BooleanField(default=False)
    max_choices = models.PositiveSmallIntegerField(default=1)
    is_anonymous = models.BooleanField(default=True)
    results_visibility = models.CharField(
        max_length=20,
        choices=[('always', 'Always'), ('after_vote', 'After vote'), ('after_close', 'After close')],
        default='after_vote',
    )
    manually_closed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'polls'
        ordering = ['poll_date', 'closes_at', 'id']
        indexes = [
            models.Index(fields=['season', 'poll_date'], name='poll_season_date_idx'),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(max_choices__gte=1), name='poll_max_choices_positive'),
        ]

    @property
    def is_cancelled(self):
        return self.cancelled_at is not None

    @property
    def is_closed(self):
        """Cancelled, manually closed, or past its deadline."""
        return (
            self.cancelled_at is not None
            or self.manually_closed_at is not None
            or self.closes_at <= timezone.now()
        )

    @property
    def status(self):
        if self.is_cancelled:
            return 'cancelled'
        return 'closed' if self.is_closed else 'open'

    def __str__(self):
        return f"{self.title} | {self.poll_date}"


class PollOption(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=100)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'poll_options'
        ordering = ['position', 'id']

    def __str__(self):
        return self.text


class PollVote(models.Model):
    """
    One selected option by one membership. Re-voting replaces the caller's
    previous options; the unique constraint prevents a duplicate selection.
    """
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='votes')
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name='votes')
    membership = models.ForeignKey(MessMemberShip, on_delete=models.CASCADE, related_name='poll_votes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'poll_votes'
        unique_together = ('poll', 'option', 'membership')
        indexes = [
            models.Index(fields=['poll', 'membership'], name='poll_vote_member_idx'),
        ]

    def __str__(self):
        return f"{self.poll_id} | {self.option_id} | {self.membership_id}"
