from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0026_notices_belong_to_mess'),
    ]

    operations = [
        migrations.AddField(
            model_name='anonymousopinion',
            name='author_name',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
    ]
