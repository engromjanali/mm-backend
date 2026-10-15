import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_recorders(apps, schema_editor):
    Deposit = apps.get_model('DepositManagement', 'Deposit')
    for deposit in Deposit.objects.filter(recorded_by__isnull=False).select_related('recorded_by'):
        deposit.recorded_by_user_id = deposit.recorded_by.user_id
        deposit.save(update_fields=['recorded_by_user'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('DepositManagement', '0003_deposit_date_and_recorded_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='deposit',
            name='recorded_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(copy_recorders, migrations.RunPython.noop),
        migrations.RemoveField(model_name='deposit', name='recorded_by'),
        migrations.RenameField(model_name='deposit', old_name='recorded_by_user', new_name='recorded_by'),
        migrations.AlterField(
            model_name='deposit',
            name='recorded_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deposits_recorded', to=settings.AUTH_USER_MODEL),
        ),
    ]
