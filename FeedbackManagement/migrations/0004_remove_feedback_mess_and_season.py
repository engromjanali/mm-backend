from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('FeedbackManagement', '0003_feedbackcomment'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='feedback',
            name='mess',
        ),
        migrations.RemoveField(
            model_name='feedback',
            name='season',
        ),
        migrations.AlterModelOptions(
            name='feedback',
            options={'ordering': ['-created_at', '-id']},
        ),
    ]
