import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_recorders(apps, schema_editor):
    Cost = apps.get_model('CostManagement', 'Cost')
    for cost in Cost.objects.filter(recorded_by__isnull=False).select_related('recorded_by'):
        cost.recorded_by_user_id = cost.recorded_by.user_id
        cost.save(update_fields=['recorded_by_user'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('CostManagement', '0003_cost_entries_with_products'),
    ]

    operations = [
        migrations.AddField(
            model_name='cost',
            name='recorded_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(copy_recorders, migrations.RunPython.noop),
        migrations.RemoveField(model_name='cost', name='recorded_by'),
        migrations.RenameField(model_name='cost', old_name='recorded_by_user', new_name='recorded_by'),
        migrations.AlterField(
            model_name='cost',
            name='recorded_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='costs_recorded', to=settings.AUTH_USER_MODEL),
        ),
    ]
