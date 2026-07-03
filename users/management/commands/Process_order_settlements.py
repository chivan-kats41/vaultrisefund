"""
Management command: process_order_settlements

Advances every active ('normal') order's progress for today — marks elapsed
settlement days as paid, updates days_completed / total_income_generated,
and finalizes + credits the user's withdrawal balance for any order whose
full duration has elapsed.

This is a thin wrapper around Order.sync_progress(), which is also called
lazily whenever a user views their orders page. Running this daily via cron
(or Celery beat) just means balances get credited promptly even for users
who don't log in on the day their investment completes.

Usage:
    python manage.py process_order_settlements

Suggested cron entry (run once daily, shortly after midnight):
    5 0 * * *  cd /path/to/project && /path/to/venv/bin/python manage.py process_order_settlements
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from users.models import Order


class Command(BaseCommand):
    help = "Sync progress, settle elapsed days, and credit completed orders."

    def handle(self, *args, **options):
        orders = Order.objects.filter(status='normal').select_related('user', 'product')
        total = orders.count()
        finished = 0
        updated = 0

        for order in orders:
            before_status = order.status
            with transaction.atomic():
                order.sync_progress()
            if order.status == 'finish' and before_status != 'finish':
                finished += 1
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Processed {updated}/{total} active orders — {finished} newly completed and credited."
        ))

