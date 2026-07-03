"""
Django Management Command: Setup VIP Levels
File: users/management/commands/setup_vip_levels.py

Creates the 9 VIP levels (V0-V8) with proper configuration

Usage:
    python manage.py setup_vip_levels
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from users.models import VIPLevel


class Command(BaseCommand):
    help = 'Setup VIP levels with proper configuration'

    def handle(self, *args, **options):
        """Create or update VIP levels"""
        
        vip_data = [
            {
                'level': 0,
                'name': 'Bronze',
                'required_investment': Decimal('0.00'),
                'daily_withdrawal_limit': Decimal('5000000.00'),
                'commission_rate': Decimal('0.00'),
                'max_orders_per_day': 30000,
                'withdrawal_fee_rate': Decimal('10.00'),
                'color_code': '#9e9e9e',
                'icon': '🥉',
                'description': 'Welcome to Agnicoeagle! Start your investment journey.',
            },
            {
                'level': 1,
                'name': 'Copper',
                'required_investment': Decimal('15000.00'),
                'daily_withdrawal_limit': Decimal('5000000.00'),
                'commission_rate': Decimal('1.00'),
                'max_orders_per_day': 30000,
                'withdrawal_fee_rate': Decimal('10.00'),
                'color_code': '#b87333',
                'icon': '🪙',
                'description': 'Unlock basic benefits and start earning commissions.',
            },
            {
                'level': 2,
                'name': 'Silver',
                'required_investment': Decimal('250000.00'),
                'daily_withdrawal_limit': Decimal('5000000.00'),
                'commission_rate': Decimal('2.00'),
                'max_orders_per_day': 30000,
                'withdrawal_fee_rate': Decimal('9.00'),
                'color_code': '#c0c0c0',
                'icon': '🥈',
                'description': 'Enhanced benefits with reduced withdrawal fees.',
            },
            {
                'level': 3,
                'name': 'Gold',
                'required_investment': Decimal('700000.00'),
                'daily_withdrawal_limit': Decimal('5000000.00'),
                'commission_rate': Decimal('3.00'),
                'max_orders_per_day': 30000,
                'withdrawal_fee_rate': Decimal('8.00'),
                'color_code': '#ffd700',
                'icon': '🥇',
                'description': 'Premium member with priority support.',
            },
            {
                'level': 4,
                'name': 'Platinum',
                'required_investment': Decimal('3000000.00'),
                'daily_withdrawal_limit': Decimal('10000000.00'),
                'commission_rate': Decimal('4.00'),
                'max_orders_per_day': 50000,
                'withdrawal_fee_rate': Decimal('7.00'),
                'color_code': '#e5e4e2',
                'icon': '💎',
                'description': 'Exclusive benefits and higher withdrawal limits.',
            },
            {
                'level': 5,
                'name': 'Diamond',
                'required_investment': Decimal('8000000.00'),
                'daily_withdrawal_limit': Decimal('15000000.00'),
                'commission_rate': Decimal('5.00'),
                'max_orders_per_day': 75000,
                'withdrawal_fee_rate': Decimal('6.00'),
                'color_code': '#b9f2ff',
                'icon': '💠',
                'description': 'Elite member with maximum benefits.',
            },
            {
                'level': 6,
                'name': 'Crown',
                'required_investment': Decimal('20000000.00'),
                'daily_withdrawal_limit': Decimal('20000000.00'),
                'commission_rate': Decimal('6.00'),
                'max_orders_per_day': 100000,
                'withdrawal_fee_rate': Decimal('5.00'),
                'color_code': '#ff6b35',
                'icon': '👑',
                'description': 'Royal status with exceptional privileges.',
            },
            {
                'level': 7,
                'name': 'Imperial',
                'required_investment': Decimal('60000000.00'),
                'daily_withdrawal_limit': Decimal('30000000.00'),
                'commission_rate': Decimal('7.00'),
                'max_orders_per_day': 150000,
                'withdrawal_fee_rate': Decimal('4.00'),
                'color_code': '#9d4edd',
                'icon': '⚜️',
                'description': 'Imperial member with VIP treatment.',
            },
            {
                'level': 8,
                'name': 'Legend',
                'required_investment': Decimal('100000000.00'),
                'daily_withdrawal_limit': Decimal('50000000.00'),
                'commission_rate': Decimal('8.00'),
                'max_orders_per_day': 200000,
                'withdrawal_fee_rate': Decimal('3.00'),
                'color_code': '#ff0080',
                'icon': '🌟',
                'description': 'Legendary status - the highest achievement!',
            },
        ]
        
        created_count = 0
        updated_count = 0
        
        with transaction.atomic():
            for vip_info in vip_data:
                vip, created = VIPLevel.objects.update_or_create(
                    level=vip_info['level'],
                    defaults=vip_info
                )
                
                if created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Created VIP {vip.level}: {vip.name}')
                    )
                else:
                    updated_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'↻ Updated VIP {vip.level}: {vip.name}')
                    )
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ VIP Setup Complete!\n'
                f'  Created: {created_count} levels\n'
                f'  Updated: {updated_count} levels\n'
                f'  Total: {created_count + updated_count} VIP levels\n'
            )
        )
        self.stdout.write('='*60 + '\n')
        
        # Display VIP summary table
        self.stdout.write(self.style.HTTP_INFO('\nVIP LEVELS SUMMARY:'))
        self.stdout.write('-' * 100)
        self.stdout.write(
            f"{'Level':<8} {'Name':<12} {'Investment':<20} {'Commission':<12} {'Fee Rate':<10}"
        )
        self.stdout.write('-' * 100)
        
        for vip in VIPLevel.objects.all().order_by('level'):
            self.stdout.write(
                f"{vip.icon} V{vip.level:<5} {vip.name:<12} "
                f"UGX {vip.required_investment:>15,.2f}  "
                f"{vip.commission_rate:>10}%  "
                f"{vip.withdrawal_fee_rate:>8}%"
            )
        
        self.stdout.write('-' * 100)
        self.stdout.write(
            self.style.SUCCESS(
                '\n✓ All VIP levels are now configured and ready to use!\n'
            )
        )