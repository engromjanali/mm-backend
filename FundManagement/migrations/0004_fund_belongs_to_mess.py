import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def move_to_mess(apps, schema_editor):
    """Point each entry at its season's mess and its recorder membership's user."""
    Fund = apps.get_model('FundManagement', 'Fund')
    for fund in Fund.objects.select_related('season', 'recorded_by'):
        fund.mess_id = fund.season.mess_id
        fund.recorded_by_user_id = fund.recorded_by.user_id if fund.recorded_by else None
        fund.save(update_fields=['mess', 'recorded_by_user'])


def move_to_season(apps, schema_editor):
    """Reverse: put each entry in its mess's active (else latest) season."""
    Fund = apps.get_model('FundManagement', 'Fund')
    MessSeason = apps.get_model('MessManagement', 'MessSeason')
    MessMemberShip = apps.get_model('MessManagement', 'MessMemberShip')
    for fund in Fund.objects.all():
        season = MessSeason.objects.filter(mess_id=fund.mess_id).order_by('-is_active', '-start_date', '-id').first()
        fund.season_id = season.id
        fund.recorded_by_id = (
            MessMemberShip.objects.filter(season=season, user_id=fund.recorded_by_user_id).values_list('id', flat=True).first()
        )
        fund.save(update_fields=['season', 'recorded_by'])


class Migration(migrations.Migration):
    """The fund belongs to the mess, not to a season, so it carries over to every new season."""

    dependencies = [
        ('FundManagement', '0003_replace_with_fund_entries'),
        ('MessManagement', '0015_alter_mess_table_alter_messmembership_table_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='fund',
            name='mess',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='funds', to='MessManagement.mess'),
        ),
        migrations.AddField(
            model_name='fund',
            name='recorded_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='fund',
            name='season',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='funds', to='MessManagement.messseason'),
        ),
        migrations.RunPython(move_to_mess, move_to_season),
        migrations.RemoveField(
            model_name='fund',
            name='season',
        ),
        migrations.RemoveField(
            model_name='fund',
            name='recorded_by',
        ),
        migrations.RenameField(
            model_name='fund',
            old_name='recorded_by_user',
            new_name='recorded_by',
        ),
        migrations.AlterField(
            model_name='fund',
            name='mess',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='funds', to='MessManagement.mess'),
        ),
        migrations.AlterField(
            model_name='fund',
            name='recorded_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='funds_recorded', to=settings.AUTH_USER_MODEL),
        ),
    ]
