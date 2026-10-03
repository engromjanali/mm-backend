import secrets

from django.db import models
from AuthManagement.models import User

class Mess(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=False, blank=True, default='')
    phone = models.CharField(max_length=20, unique=False, blank=True, default='')
    address = models.CharField(max_length=255, blank=True, default='')
    # Leadership lives on the mess (not on a season membership) so the manager
    # keeps authority over every season's data.
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_messes')
    acting_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='acting_managed_messes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def active_season(self):
        return self.seasons.filter(is_active=True).order_by('-start_date', '-id').first()

    def role_of(self, user_id):
        if self.manager_id == user_id:
            return 'manager'
        if self.acting_manager_id == user_id:
            return 'acting_manager'
        return 'member'

    class Meta:
        db_table = 'messes'


class MessSeason(models.Model):
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='seasons')
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(default=None,null=True,blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mess_seasons'



class MessMemberShip(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mess_memberships')
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='memberships')
    season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='memberships')
    status = models.CharField(max_length=20, choices=[('active', 'Active'), ('inactive', 'Inactive')], default='active')
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(default=None, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mess_memberships'
        unique_together = ('user', 'mess', 'season')

    @property
    def role(self):
        """Role is derived from the mess leadership, never stored per season."""
        return self.mess.role_of(self.user_id)



class MessMemberShipRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_requests')
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='mess_requests')
    # `cancelled` = withdrawn by the user (or made moot when they joined by invite).
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('cancelled', 'Cancelled')], default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(blank=True, null=True)
    response_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mess_membership_requests'

    

def generate_invite_code():
    return secrets.token_hex(4).upper()


class MessMemberShipInvitation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_invitations')
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='mess_invitations')
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_invitations')
    invite_code = models.CharField(max_length=16, unique=True, default=generate_invite_code)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined'), ('revoked', 'Revoked')], default='pending')
    invited_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(blank=True, null=True)
    Invitation_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mess_membership_invitations'





class Notices(models.Model):
    """
    A notice on a season's board. Like deposits and costs it belongs to a
    season, so a new season starts with an empty board.
    """
    season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='notices')
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notices'
        # Pinned notice first, then newest.
        ordering = ['-is_pinned', '-created_at', '-id']
        constraints = [
            # At most one pinned notice per season.
            models.UniqueConstraint(fields=['season'], condition=models.Q(is_pinned=True), name='one_pinned_notice_per_season'),
        ]





    