from django.db import migrations, models


def mark_existing_left_memberships(apps, schema_editor):
    MessMemberShip = apps.get_model('MessManagement', 'MessMemberShip')
    MessMemberShip.objects.filter(left_at__isnull=False).update(status='left')


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0024_opinionperiod_anonymousopinion_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='messmembership',
            name='status',
            field=models.CharField(choices=[('active', 'Active'), ('inactive', 'Inactive'), ('left', 'Left')], default='active', max_length=20),
        ),
        migrations.RunPython(mark_existing_left_memberships, migrations.RunPython.noop),
    ]
