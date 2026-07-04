# invitation/migrations/0003_update_commission_rates.py
from django.db import migrations
from decimal import Decimal


def set_rates(apps, schema_editor):
    CommissionRate = apps.get_model('invitation', 'CommissionRate')
    rates = {1: Decimal('16.00'), 2: Decimal('12.00'), 3: Decimal('8.00')}

    for level, rate in rates.items():
        obj, created = CommissionRate.objects.get_or_create(
            level=level,
            vip_level=0,
            defaults={'rate': rate, 'is_active': True},
        )
        if not created:
            obj.rate = rate
            obj.is_active = True
            obj.save(update_fields=['rate', 'is_active'])


def reverse_rates(apps, schema_editor):
    pass  # no automatic reverse; add old values here if you need true reversibility


class Migration(migrations.Migration):

    dependencies = [
        ("invitation", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(set_rates, reverse_rates),
    ]