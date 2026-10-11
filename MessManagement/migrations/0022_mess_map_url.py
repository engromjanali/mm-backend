from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0021_invite_and_request_expiry'),
    ]

    operations = [
        migrations.AddField(
            model_name='mess',
            name='map_url',
            field=models.URLField(blank=True, default='', max_length=500),
        ),
    ]
