from django.db import migrations, models


def empty_identity_to_null(apps, schema_editor):
    AnonymousOpinion = apps.get_model('MessManagement', 'AnonymousOpinion')
    AnonymousOpinion.objects.filter(author_name='').update(author_name=None)
    AnonymousOpinion.objects.filter(author_photo_url='').update(author_photo_url=None)


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0031_anonymousopinion_author'),
    ]

    operations = [
        migrations.AlterField(
            model_name='anonymousopinion',
            name='author_name',
            field=models.CharField(blank=True, default=None, max_length=150, null=True),
        ),
        migrations.AlterField(
            model_name='anonymousopinion',
            name='author_photo_url',
            field=models.URLField(blank=True, default=None, max_length=500, null=True),
        ),
        migrations.RunPython(empty_identity_to_null, migrations.RunPython.noop),
    ]
