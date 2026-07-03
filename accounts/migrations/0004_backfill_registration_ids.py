import random

from django.db import migrations


def generate_unique_id(Accounts, existing_ids):
    while True:
        candidate = str(random.randint(100000, 999999))
        if candidate not in existing_ids:
            existing_ids.add(candidate)
            return candidate


def backfill_registration_ids(apps, schema_editor):
    Accounts = apps.get_model('accounts', 'Accounts')
    existing_ids = set(
        Accounts.objects.exclude(registration_id__isnull=True)
                         .exclude(registration_id='')
                         .values_list('registration_id', flat=True)
    )
    for account in Accounts.objects.filter(registration_id__isnull=True):
        account.registration_id = generate_unique_id(Accounts, existing_ids)
        account.save(update_fields=['registration_id'])


def noop_reverse(apps, schema_editor):
    # Nothing to undo — leaving registration_id populated on reverse is fine.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_accounts_registration_id'),
    ]

    operations = [
        migrations.RunPython(backfill_registration_ids, noop_reverse),
    ]