import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):
    """Cost entries: shopping date + time, who recorded them, and product / price rows (tables were empty)."""

    dependencies = [
        ('CostManagement', '0002_alter_cost_table_alter_costbreakdown_table'),
        ('MessManagement', '0015_alter_mess_table_alter_messmembership_table_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cost',
            name='performed_at',
        ),
        migrations.AddField(
            model_name='cost',
            name='date',
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
        migrations.AddField(
            model_name='cost',
            name='time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cost',
            name='recorded_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='costs_recorded', to='MessManagement.messmembership'),
        ),
        migrations.AlterModelOptions(
            name='cost',
            options={'ordering': ['-date', '-time', '-id']},
        ),
        migrations.RemoveField(
            model_name='costbreakdown',
            name='quantity',
        ),
        migrations.RemoveField(
            model_name='costbreakdown',
            name='unit_price',
        ),
        migrations.RemoveField(
            model_name='costbreakdown',
            name='total_amount',
        ),
        migrations.AddField(
            model_name='costbreakdown',
            name='price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name='costbreakdown',
            options={'ordering': ['id']},
        ),
    ]
