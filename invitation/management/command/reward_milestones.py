"""
File: invitation/management/commands/reward_milestones.py

Check and process milestone rewards for eligible users.

Usage:
    python manage.py reward_milestones
    python manage.py reward_milestones --user john_doe
    python manage.py reward_milestones --dry-run
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from invitation.utils import check_reward_eligibility, auto_claim_rewards

User = get_user_model()


class Command(BaseCommand):
    help = 'Check and process milestone rewards for eligible users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Check rewards for specific user (username)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show eligible rewards without claiming',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Check all users (slow for large databases)',
        )

    def handle(self, *args, **options):
        username = options.get('user')
        dry_run = options.get('dry_run')
        check_all = options.get('all')

        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('MILESTONE REWARD PROCESSING'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        if dry_run:
            self.stdout.write(self.style.WARNING('\n*** DRY RUN MODE ***\n'))

        # Get users to check
        if username:
            try:
                users = [User.objects.get(username=username)]
            except User.DoesNotExist:
                raise CommandError(f'User "{username}" does not exist')
        elif check_all:
            users = User.objects.filter(is_active=True)
            self.stdout.write(f'Checking all {users.count()} users...\n')
        else:
            # Check users with referrals
            from invitation.models import ReferralRelationship
            referrer_ids = ReferralRelationship.objects.values_list(
                'referrer_id', flat=True
            ).distinct()
            users = User.objects.filter(id__in=referrer_ids)
            self.stdout.write(f'Checking {users.count()} users with referrals...\n')

        # Process each user
        total_eligible = 0
        total_claimed = 0
        total_processed = 0

        for user in users:
            # Check eligibility
            eligible = check_reward_eligibility(user)
            
            if eligible:
                total_eligible += len(eligible)
                
                self.stdout.write(f'\n{user.username}:')
                for reward_info in eligible:
                    self.stdout.write(
                        f"  • {reward_info['icon']} {reward_info['name']}"
                    )
                
                if not dry_run:
                    # Auto-claim rewards
                    result = auto_claim_rewards(user)
                    total_claimed += result['claimed']
                    total_processed += result['processed']
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✓ Claimed: {result['claimed']}, "
                            f"Processed: {result['processed']}"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  → Would claim {len(eligible)} rewards")
                    )

        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'Users checked: {users.count()}')
        self.stdout.write(f'Eligible rewards found: {total_eligible}')
        
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f'Rewards claimed: {total_claimed}'))
            self.stdout.write(self.style.SUCCESS(f'Rewards processed: {total_processed}'))
        else:
            self.stdout.write(self.style.WARNING('DRY RUN - No rewards claimed'))


