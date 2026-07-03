from django.core.management.base import BaseCommand
from category.models import category


class Command(BaseCommand):
    help = 'Seed default product categories'

    def handle(self, *args, **options):
        categories = [
            {
                'category_name': 'Stable Plan',
                'slug': 'stable',
                'description': 'Stable long-term investment plans',
                'kart_image': 'photos/products/stable.jpg',
            },
            {
                'category_name': 'Welfare Plan',
                'slug': 'welfare',
                'description': 'Welfare and social investment plans',
                'kart_image': 'photos/products/welfare.jpg',
            },
            {
                'category_name': 'Popular Plan',
                'slug': 'popular',
                'description': 'Most popular investment plans',
                'kart_image': 'photos/products/popular.jpg',
            },
        ]

        for cat in categories:
            obj, created = category.objects.get_or_create(
                slug=cat['slug'],
                defaults={
                    'category_name': cat['category_name'],
                    'description':   cat['description'],
                    'kart_image':    cat['kart_image'],
                }
            )
            status = self.style.SUCCESS('Created') if created else self.style.WARNING('Already exists')
            self.stdout.write(f"{status}: {obj.category_name}")

        self.stdout.write(self.style.SUCCESS('\nCategories seeded successfully!'))