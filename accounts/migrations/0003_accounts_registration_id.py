# Generated manually to match project migration style

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_accounts_options_alter_accounts_is_active_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='accounts',
            name='registration_id',
            field=models.CharField(
                blank=True,
                help_text='Unique 6-digit member/registration ID shown to the user.',
                max_length=6,
                null=True,
                unique=True,
            ),
        ),
    ]