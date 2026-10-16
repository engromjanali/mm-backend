from django.db import migrations, models
import django.db.models.deletion


def copy_notice_mess(apps, schema_editor):
    Notices = apps.get_model('MessManagement', 'Notices')
    for notice in Notices.objects.select_related('season').iterator():
        notice.mess_id = notice.season.mess_id
        notice.save(update_fields=['mess'])
    pinned_mess_ids = Notices.objects.filter(is_pinned=True).values_list('mess_id', flat=True).distinct()
    for mess_id in pinned_mess_ids:
        keep = Notices.objects.filter(mess_id=mess_id, is_pinned=True).order_by('-created_at', '-id').first()
        Notices.objects.filter(mess_id=mess_id, is_pinned=True).exclude(pk=keep.pk).update(is_pinned=False)


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0025_alter_messmembership_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='notices',
            name='mess',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notices', to='MessManagement.mess'),
        ),
        migrations.RunPython(copy_notice_mess, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='notices',
            name='one_pinned_notice_per_season',
        ),
        migrations.RemoveField(
            model_name='notices',
            name='season',
        ),
        migrations.AlterField(
            model_name='notices',
            name='mess',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notices', to='MessManagement.mess'),
        ),
        migrations.AddConstraint(
            model_name='notices',
            constraint=models.UniqueConstraint(condition=models.Q(is_pinned=True), fields=('mess',), name='one_pinned_notice_per_mess'),
        ),
    ]
