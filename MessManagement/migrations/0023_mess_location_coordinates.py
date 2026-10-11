from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0022_mess_map_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='mess',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='mess',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True),
        ),
    ]
