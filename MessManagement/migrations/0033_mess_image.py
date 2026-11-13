from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('MessManagement', '0032_anonymousopinion_nullable_identity'),
    ]

    operations = [
        migrations.AddField(
            model_name='mess',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='mess_images/'),
        ),
    ]
