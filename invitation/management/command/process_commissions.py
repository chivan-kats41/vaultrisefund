from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

from invitation.models import Commission
from users.models import Transaction, Notification

User = get_user_model()


class Command(BaseCommand):
    help = 'Process pending commissions and credit to users balances'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Process commissions for specific user (username)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of commissions to process',
        )

    def handle(self, *args, **options):
        username = options.get('user')
        dry_run = options.get('dry_run')
        limit = options.get('limit')

        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('COMMISSION PROCESSING'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        # Get pending commissions
        pending = Commission.objects.filter(status='pending')

        if username:
            try:
                user = User.objects.get(username=username)
                pending = pending.filter(referrer=user)
                self.stdout.write(f'Filtering for user: {username}')
            except User.DoesNotExist:
                raise CommandError(f'User "{username}" does not exist')

        if limit:
            pending = pending[:limit]
            self.stdout.write(f'Limiting to {limit} commissions')

        pending = pending.select_related('referrer', 'referee', 'order')

        total_pending = pending.count()
        self.stdout.write(f'\nTotal pending commissions: {total_pending}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n*** DRY RUN MODE ***\n'))

        if total_pending == 0:
            self.stdout.write(self.style.SUCCESS('No pending commissions to process'))
            return

        # Process commissions
        processed = 0
        failed = 0
        total_amount = Decimal('0.00')

        for commission in pending:
            try:
                referrer = commission.referrer
                referrer_profile = referrer.profile
                amount = commission.commission_amount

                self.stdout.write(
                    f'\nProcessing: {referrer.username} - '
                    f'UGX {amount:,.2f} (Level {commission.level})'
                )

                if not dry_run:
                    # Credit balance
                    old_balance = referrer_profile.commission_balance
                    referrer_profile.commission_balance += amount
                    referrer_profile.referral_earnings += amount
                    referrer_profile.save(update_fields=[
                        'commission_balance', 'referral_earnings'
                    ])

                    # Create transaction
                    transaction = Transaction.objects.create(
                        user=referrer,
                        transaction_number=f"BATCH_COM{commission.id}",
                        transaction_type='promotion_commission',
                        amount=amount,
                        balance_type='commission_balance',
                        balance_before=old_balance,
                        balance_after=referrer_profile.commission_balance,
                        description=f"Batch-processed commission (Level {commission.level})",
                        reference_id=str(commission.id),
                        status='completed'
                    )

                    # Mark as paid
                    commission.mark_as_paid(transaction=transaction)

                    # Send notification
                    Notification.objects.create(
                        user=referrer,
                        title="Commission Credited",
                        message=f"Commission of UGX {amount:,.2f} has been credited to your account.",
                        notification_type='referral'
                    )

                    self.stdout.write(self.style.SUCCESS('  ✓ Processed'))
                else:
                    self.stdout.write(self.style.WARNING('  → Would process'))

                processed += 1
                total_amount += amount

            except Exception as e:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Failed: {str(e)}')
                )
                continue

        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'Total commissions: {total_pending}')
        self.stdout.write(self.style.SUCCESS(f'Successfully processed: {processed}'))
        if failed > 0:
            self.stdout.write(self.style.ERROR(f'Failed: {failed}'))
        self.stdout.write(f'Total amount: UGX {total_amount:,.2f}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - No changes were made'))
