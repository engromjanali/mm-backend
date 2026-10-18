from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0028_opinionperiod_allow_named_opinions'),
    ]

    operations = [
        migrations.AddField(
            model_name='anonymousopinion',
            name='author_photo_url',
            field=models.URLField(blank=True, default='', max_length=500),
        ),
    ]
