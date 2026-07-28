from django.contrib import admin

# Register your models here.
from .models import Mess,MessSeason, MessMemberShip, MessMemberShipRequest, MessMemberShipInvitation

admin.site.register(Mess)
admin.site.register(MessSeason)
admin.site.register(MessMemberShip)
admin.site.register(MessMemberShipRequest)
admin.site.register(MessMemberShipInvitation)