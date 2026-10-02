import secrets

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import MessManagement.models


def forwards(apps, schema_editor):
    Mess = apps.get_model('MessManagement', 'Mess')
    MessMemberShip = apps.get_model('MessManagement', 'MessMemberShip')
    Invitation = apps.get_model('MessManagement', 'MessMemberShipInvitation')

    # Move leadership from the latest season membership onto the mess.
    for mess in Mess.objects.all():
        memberships = MessMemberShip.objects.filter(mess=mess).order_by('-season__start_date', '-id')
        manager = memberships.filter(role='manager').first()
        acting = memberships.filter(role='acting_manager').first()
        mess.manager_id = manager.user_id if manager else None
        mess.acting_manager_id = acting.user_id if acting else None
        mess.save(update_fields=['manager', 'acting_manager'])

    used = set()
    for invitation in Invitation.objects.all():
        code = secrets.token_hex(4).upper()
        while code in used:
            code = secrets.token_hex(4).upper()
        used.add(code)
        invitation.invite_code = code
        invitation.save(update_fields=['invite_code'])


def backwards(apps, schema_editor):
    Mess = apps.get_model('MessManagement', 'Mess')
    MessMemberShip = apps.get_model('MessManagement', 'MessMemberShip')
    for mess in Mess.objects.all():
        if mess.manager_id:
            MessMemberShip.objects.filter(mess=mess, user_id=mess.manager_id).update(role='manager')
        if mess.acting_manager_id:
            MessMemberShip.objects.filter(mess=mess, user_id=mess.acting_manager_id).update(role='acting_manager')


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0013_notices_is_pinned'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='mess',
            name='manager',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='managed_messes', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='mess',
            name='acting_manager',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='acting_managed_messes', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='messmembershipinvitation',
            name='invite_code',
            field=models.CharField(max_length=16, null=True),
        ),
        migrations.AddField(
            model_name='messmembershipinvitation',
            name='invited_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sent_invitations', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='messmembership',
            name='role',
        ),
        migrations.AlterField(
            model_name='messmembershipinvitation',
            name='invite_code',
            field=models.CharField(default=MessManagement.models.generate_invite_code, max_length=16, unique=True),
        ),
        migrations.AlterField(
            model_name='mess',
            name='address',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='mess',
            name='email',
            field=models.EmailField(blank=True, default='', max_length=254),
        ),
        migrations.AlterField(
            model_name='mess',
            name='phone',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AlterField(
            model_name='messmembershipinvitation',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined'), ('revoked', 'Revoked')], default='pending', max_length=20),
        ),
    ]
