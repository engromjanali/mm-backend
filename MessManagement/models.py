from django.db import models
from AuthManagement.models import User

class Mess(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=False)
    phone = models.CharField(max_length=20, unique=False)
    address = models.CharField(max_length=255)
    manager = models.OneToOneField(User, on_delete=models.CASCADE, related_name='managed_messes')
    act_manager = models.OneToOneField(User, on_delete=models.CASCADE, related_name='active_messes', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class MessSeason(models.Model):
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='seasons')
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)



class MessMemberShip(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mess_memberships')
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='memberships')
    season = models.ForeignKey(MessSeason, on_delete=models.CASCADE, related_name='memberships')
    status = models.CharField(max_length=20, choices=[('active', 'Active'), ('inactive', 'Inactive')], default='active')
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'mess', 'season')



class MessMemberShipRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='membership_requests')
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='membership_requests')
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(blank=True, null=True)
    response_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'mess')


class MessMemberShipInvitation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='membership_invitations')
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='membership_invitations')
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined')], default='pending')
    invited_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(blank=True, null=True)
    Invitation_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'mess')




class Notices(models.Model):
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='notices')
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)





    