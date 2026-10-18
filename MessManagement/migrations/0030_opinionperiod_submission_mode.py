from django.db import migrations, models


def copy_submission_mode(apps, schema_editor):
    OpinionPeriod = apps.get_model('MessManagement', 'OpinionPeriod')
    OpinionPeriod.objects.filter(allow_named_opinions=True).update(submission_mode='all')


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0029_anonymousopinion_author_photo_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='opinionperiod',
            name='submission_mode',
            field=models.CharField(choices=[('anonymous_only', 'Name hidden'), ('named_only', 'Name revealed'), ('all', 'All')], default='anonymous_only', max_length=20),
        ),
        migrations.RunPython(copy_submission_mode, migrations.RunPython.noop),
    ]
