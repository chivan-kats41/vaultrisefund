"""
File: invitation/management/commands/sync_relationships.py

Synchronize relationship statistics with actual data.

Usage:
    python manage.py sync_relationships
    python manage.py sync_relationships --user john_doe
    python manage.py sync_relationships --fix
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count
from decimal import Decimal

from invitation.models import ReferralRelationship, Commission
from users.models import Order

User = get_user_model()


class Command(BaseCommand):
    help = 'Synchronize referral relationship statistics with actual data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Sync relationships for specific user (username)',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Fix discrepancies automatically',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        username = options.get('user')
        fix = options.get('fix')
        verbose = options.get('verbose')

        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('RELATIONSHIP SYNCHRONIZATION'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        # Get relationships
        relationships = ReferralRelationship.objects.all()

        if username:
            try:
                user = User.objects.get(username=username)
                relationships = relationships.filter(referrer=user)
                self.stdout.write(f'Filtering for user: {username}')
            except User.DoesNotExist:
                raise CommandError(f'User "{username}" does not exist')

        relationships = relationships.select_related('referrer', 'referee')

        total = relationships.count()
        self.stdout.write(f'\nTotal relationships: {total}\n')

        if not fix:
            self.stdout.write(self.style.WARNING('*** CHECK MODE (use --fix to apply changes) ***\n'))

        # Process relationships
        checked = 0
        discrepancies = 0
        fixed = 0

        for relationship in relationships:
            checked += 1

            # Get actual commission data
            commissions = Commission.objects.filter(
                relationship=relationship,
                status='paid'
            ).aggregate(
                total=Sum('commission_amount'),
                count=Count('id')
            )

            actual_commission = commissions['total'] or Decimal('0.00')
            stored_commission = relationship.total_commission_earned

            # Get actual order data
            orders = Order.objects.filter(
                user=relationship.referee,
                status__in=['normal', 'finish']
            ).aggregate(
                count=Count('id'),
                total_amount=Sum('total_amount')
            )

            actual_purchases = orders['count'] or 0
            actual_amount = orders['total_amount'] or Decimal('0.00')
            stored_purchases = relationship.total_purchases
            stored_amount = relationship.total_purchase_amount

            # Check for discrepancies
            has_discrepancy = False

            if actual_commission != stored_commission:
                has_discrepancy = True
                self.stdout.write(
                    f'\n{relationship.referrer.username} → {relationship.referee.username} (L{relationship.level})'
                )
                self.stdout.write(
                    self.style.WARNING(
                        f'  Commission mismatch: Stored={stored_commission:,.2f}, '
                        f'Actual={actual_commission:,.2f}'
                    )
                )

            if actual_purchases != stored_purchases:
                has_discrepancy = True
                if verbose or not has_discrepancy:
                    self.stdout.write(
                        f'\n{relationship.referrer.username} → {relationship.referee.username} (L{relationship.level})'
                    )
                self.stdout.write(
                    self.style.WARNING(
                        f'  Purchases mismatch: Stored={stored_purchases}, '
                        f'Actual={actual_purchases}'
                    )
                )

            if actual_amount != stored_amount:
                has_discrepancy = True
                if verbose or not has_discrepancy:
                    self.stdout.write(
                        f'\n{relationship.referrer.username} → {relationship.referee.username} (L{relationship.level})'
                    )
                self.stdout.write(
                    self.style.WARNING(
                        f'  Amount mismatch: Stored={stored_amount:,.2f}, '
                        f'Actual={actual_amount:,.2f}'
                    )
                )

            if has_discrepancy:
                discrepancies += 1

                if fix:
                    relationship.total_commission_earned = actual_commission
                    relationship.total_purchases = actual_purchases
                    relationship.total_purchase_amount = actual_amount
                    relationship.save(update_fields=[
                        'total_commission_earned',
                        'total_purchases',
                        'total_purchase_amount'
                    ])
                    self.stdout.write(self.style.SUCCESS('  ✓ Fixed'))
                    fixed += 1
                else:
                    self.stdout.write(self.style.WARNING('  → Would fix'))

        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'Total relationships checked: {checked}')
        
        if discrepancies > 0:
            self.stdout.write(self.style.WARNING(f'Discrepancies found: {discrepancies}'))
            if fix:
                self.stdout.write(self.style.SUCCESS(f'Fixed: {fixed}'))
            else:
                self.stdout.write(self.style.WARNING('Use --fix to apply changes'))
        else:
            self.stdout.write(self.style.SUCCESS('All relationships are in sync!'))

