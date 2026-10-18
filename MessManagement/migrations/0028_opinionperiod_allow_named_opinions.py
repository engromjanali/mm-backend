from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0027_anonymousopinion_author_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='opinionperiod',
            name='allow_named_opinions',
            field=models.BooleanField(default=False),
        ),
    ]
