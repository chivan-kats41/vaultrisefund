# Generated manually to match project migration style

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_backfill_registration_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='accounts',
            name='nickname',
            field=models.CharField(blank=True, max_length=50),
        ),
    ]