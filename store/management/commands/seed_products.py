from django.core.management.base import BaseCommand
from category.models import category as Category
from store.models import InvestmentProduct
from decimal import Decimal


class Command(BaseCommand):
    help = 'Seed default investment products for all categories'

    def handle(self, *args, **options):

        def get_cat(slug):
            try:
                return Category.objects.get(slug=slug)
            except Category.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f"Category '{slug}' not found. Run 'python manage.py seed_category' first."
                ))
                return None

        stable  = get_cat('stable')
        welfare = get_cat('welfare')
        popular = get_cat('popular')

        if not all([stable, welfare, popular]):
            return

        products = [

            # --- Stable Plan ---
            {
                'name':          'Copper',
                'category':      stable,
                'vip_required':  0,
                'price':         Decimal('15000.00'),
                'daily_earning': Decimal('5250.00'),
                'total_return':  Decimal('315000.00'),
                'duration_days': 60,
                'max_shares':    100,
                'is_active':     True,
            },
            {
                'name':          'Silver',
                'category':      stable,
                'vip_required':  1,
                'price':         Decimal('50000.00'),
                'daily_earning': Decimal('17500.00'),
                'total_return':  Decimal('1050000.00'),
                'duration_days': 60,
                'max_shares':    50,
                'is_active':     True,
            },
            {
                'name':          'Gold',
                'category':      stable,
                'vip_required':  2,
                'price':         Decimal('150000.00'),
                'daily_earning': Decimal('52500.00'),
                'total_return':  Decimal('3150000.00'),
                'duration_days': 60,
                'max_shares':    20,
                'is_active':     True,
            },
            {
                'name':          'Zinc',
                'category':      stable,
                'vip_required':  3,
                'price':         Decimal('500000.00'),
                'daily_earning': Decimal('175000.00'),
                'total_return':  Decimal('10500000.00'),
                'duration_days': 60,
                'max_shares':    10,
                'is_active':     True,
            },

            # --- Welfare Plan ---
            {
                'name':          'Bronze Welfare',
                'category':      welfare,
                'vip_required':  0,
                'price':         Decimal('20000.00'),
                'daily_earning': Decimal('8000.00'),
                'total_return':  Decimal('240000.00'),
                'duration_days': 30,
                'max_shares':    80,
                'is_active':     True,
            },
            {
                'name':          'Silver Welfare',
                'category':      welfare,
                'vip_required':  1,
                'price':         Decimal('75000.00'),
                'daily_earning': Decimal('30000.00'),
                'total_return':  Decimal('900000.00'),
                'duration_days': 30,
                'max_shares':    40,
                'is_active':     True,
            },
            {
                'name':          'Gold Welfare',
                'category':      welfare,
                'vip_required':  2,
                'price':         Decimal('200000.00'),
                'daily_earning': Decimal('80000.00'),
                'total_return':  Decimal('2400000.00'),
                'duration_days': 30,
                'max_shares':    15,
                'is_active':     True,
            },

            # --- Popular Plan ---
            {
                'name':          'Starter Plus',
                'category':      popular,
                'vip_required':  0,
                'price':         Decimal('10000.00'),
                'daily_earning': Decimal('3000.00'),
                'total_return':  Decimal('135000.00'),
                'duration_days': 45,
                'max_shares':    150,
                'is_active':     True,
            },
            {
                'name':          'Growth Pack',
                'category':      popular,
                'vip_required':  1,
                'price':         Decimal('100000.00'),
                'daily_earning': Decimal('30000.00'),
                'total_return':  Decimal('1350000.00'),
                'duration_days': 45,
                'max_shares':    30,
                'is_active':     True,
            },
            {
                'name':          'Premium Pack',
                'category':      popular,
                'vip_required':  2,
                'price':         Decimal('300000.00'),
                'daily_earning': Decimal('90000.00'),
                'total_return':  Decimal('4050000.00'),
                'duration_days': 45,
                'max_shares':    10,
                'is_active':     True,
            },
        ]

        for p in products:
            name = p.pop('name')
            cat  = p.pop('category')

            obj, created = InvestmentProduct.objects.get_or_create(
                name=name,
                category=cat,
                defaults={'name': name, 'category': cat, **p}
            )

            status = self.style.SUCCESS('Created') if created else self.style.WARNING('Already exists')
            self.stdout.write(
                f"{status}: [{obj.category_name}] {obj.name} "
                f"— UGX {obj.price:,} | Daily: UGX {obj.daily_earning:,} | Total: UGX {obj.total_return:,}"
            )

        self.stdout.write(self.style.SUCCESS('\nAll products seeded successfully!'))