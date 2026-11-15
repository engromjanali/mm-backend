from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('FeedbackManagement', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedback',
            name='is_public',
            field=models.BooleanField(db_index=True, default=True),
        ),
    ]
