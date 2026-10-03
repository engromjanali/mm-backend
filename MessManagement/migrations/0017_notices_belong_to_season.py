from django.db import migrations, models
import django.db.models.deletion


def assign_seasons(apps, schema_editor):
    """
    Moves each notice from its mess to that mess's active season (or its
    latest season). A notice whose mess has no season can't be shown to anyone
    once notices are season-scoped, so it is removed.
    """
    Notices = apps.get_model('MessManagement', 'Notices')
    MessSeason = apps.get_model('MessManagement', 'MessSeason')
    for notice in Notices.objects.all():
        seasons = MessSeason.objects.filter(mess_id=notice.mess_id)
        season = seasons.filter(is_active=True).order_by('-start_date', '-id').first() or seasons.order_by('-start_date', '-id').first()
        if season is None:
            notice.delete()
        else:
            Notices.objects.filter(pk=notice.pk).update(season=season)


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0016_notices_one_pinned_per_mess'),
    ]

    operations = [
        migrations.AddField(
            model_name='notices',
            name='season',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notices', to='MessManagement.messseason'),
        ),
        migrations.RunPython(assign_seasons, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='notices',
            name='one_pinned_notice_per_mess',
        ),
        migrations.RemoveField(
            model_name='notices',
            name='mess',
        ),
        migrations.AlterField(
            model_name='notices',
            name='season',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notices', to='MessManagement.messseason'),
        ),
        migrations.AddConstraint(
            model_name='notices',
            constraint=models.UniqueConstraint(condition=models.Q(('is_pinned', True)), fields=('season',), name='one_pinned_notice_per_season'),
        ),
    ]
