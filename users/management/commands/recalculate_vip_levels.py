"""
Management command: recalculate_vip_levels

Backfills every user's vip_level from their existing total_investment.

This exists because vip_level was previously never recalculated after
total_investment changed, so users who invested enough to qualify for a
higher VIP tier before this fix was applied are still stuck at VIP 0 (or
whatever they were before). Run this once after deploying the
update_vip_level() fix to correct all existing accounts; safe to rerun
any time since it's idempotent.

Usage:
    python manage.py recalculate_vip_levels
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from users.models import UserProfile


class Command(BaseCommand):
    help = "Recalculate vip_level for all users based on their total_investment."

    def handle(self, *args, **options):
        profiles = UserProfile.objects.select_related('user').all()
        total = profiles.count()
        changed = 0

        for profile in profiles:
            with transaction.atomic():
                leveled_up, old_level, new_level = profile.update_vip_level()
            if leveled_up:
                changed += 1
                self.stdout.write(
                    f"  {profile.user.username}: VIP {old_level} -> VIP {new_level} "
                    f"(total_investment=UGX {profile.total_investment:,.2f})"
                )

        self.stdout.write(self.style.SUCCESS(
            f"\nChecked {total} profiles — {changed} vip_level corrected."
        ))