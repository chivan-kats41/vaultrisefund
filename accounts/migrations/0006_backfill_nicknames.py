from django.db import migrations


def backfill_nicknames(apps, schema_editor):
    Accounts = apps.get_model('accounts', 'Accounts')
    for account in Accounts.objects.filter(nickname=''):
        account.nickname = account.first_name or f"User{account.registration_id or ''}"
        account.save(update_fields=['nickname'])


def noop_reverse(apps, schema_editor):
    # Nothing to undo — leaving nickname populated on reverse is fine.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_accounts_nickname'),
    ]

    operations = [
        migrations.RunPython(backfill_nicknames, noop_reverse),
    ]