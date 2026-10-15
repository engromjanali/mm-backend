from django.db import migrations, models
import django.db.models.deletion


def copy_current_season(apps, schema_editor):
    User = apps.get_model('AuthManagement', 'User')
    for user in User.objects.filter(current_membership__isnull=False).select_related('current_membership'):
        user.current_season_id = user.current_membership.season_id
        user.save(update_fields=['current_season'])


class Migration(migrations.Migration):

    dependencies = [
        ('AuthManagement', '0004_account_deletion_request'),
        ('MessManagement', '0025_alter_messmembership_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='current_season',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='MessManagement.messseason'),
        ),
        migrations.RunPython(copy_current_season, migrations.RunPython.noop),
    ]
