from django.db import migrations
from django.db.models import F


def compact_notification_content(apps, schema_editor):
    notification = apps.get_model('AuthManagement', 'Notification')
    notification.objects.using(schema_editor.connection.alias).update(description=F('title'), title='New Notice')


class Migration(migrations.Migration):
    dependencies = [('AuthManagement', '0007_notification')]

    operations = [migrations.RunPython(compact_notification_content, migrations.RunPython.noop)]
