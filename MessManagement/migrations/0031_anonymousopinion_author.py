from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('MessManagement', '0030_opinionperiod_submission_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='anonymousopinion',
            name='author',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='named_opinions', to=settings.AUTH_USER_MODEL),
        ),
    ]
