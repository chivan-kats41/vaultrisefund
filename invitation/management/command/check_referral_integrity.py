"""
File: invitation/management/commands/check_referral_integrity.py

Check referral system data integrity and report issues.

Usage:
    python manage.py check_referral_integrity
    python manage.py check_referral_integrity --fix
"""

from django.core.management.base import BaseCommand

from invitation.utils import validate_referral_integrity, fix_relationship_data


class Command(BaseCommand):
    help = 'Check referral system data integrity'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix issues automatically',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        fix = options['fix']
        verbose = options['verbose']

        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('REFERRAL INTEGRITY CHECK'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        # Run validation
        report = validate_referral_integrity()

        # Display results
        if report['valid']:
            self.stdout.write(self.style.SUCCESS('\n✓ System is valid!'))
        else:
            self.stdout.write(self.style.ERROR('\n✗ Issues found!'))

        # Errors
        if report['errors']:
            self.stdout.write('\n' + self.style.ERROR('ERRORS'))
            self.stdout.write('-' * 60)
            for error in report['errors']:
                self.stdout.write(
                    self.style.ERROR(f"• {error['type']}: {error['message']}")
                )
                if verbose and 'relationship_id' in error:
                    self.stdout.write(f"  ID: {error['relationship_id']}")

        # Warnings
        if report['warnings']:
            self.stdout.write('\n' + self.style.WARNING('WARNINGS'))
            self.stdout.write('-' * 60)
            for warning in report['warnings']:
                self.stdout.write(
                    self.style.WARNING(f"• {warning['type']}: {warning['message']}")
                )
                if verbose:
                    for key, value in warning.items():
                        if key not in ['type', 'message']:
                            self.stdout.write(f"  {key}: {value}")

        # Statistics
        stats = report['statistics']
        self.stdout.write('\n' + self.style.SUCCESS('STATISTICS'))
        self.stdout.write('-' * 60)
        self.stdout.write(f"Total relationships: {stats['total_relationships']}")
        self.stdout.write(f"Total commissions: {stats['total_commissions']}")
        self.stdout.write(f"Total clicks: {stats['total_clicks']}")
        self.stdout.write(self.style.ERROR(f"Errors found: {stats['errors_found']}"))
        self.stdout.write(self.style.WARNING(f"Warnings found: {stats['warnings_found']}"))

        # Fix if requested
        if fix and (report['errors'] or report['warnings']):
            self.stdout.write('\n' + self.style.WARNING('ATTEMPTING FIXES...'))
            self.stdout.write('-' * 60)
            
            fixes = fix_relationship_data(dry_run=False)
            
            self.stdout.write(f"Circular refs removed: {fixes['circular_refs_removed']}")
            self.stdout.write(f"Statistics updated: {fixes['statistics_updated']}")
            self.stdout.write(f"Commissions recalculated: {fixes['commissions_recalculated']}")
            
            if fixes['details']:
                for detail in fixes['details']:
                    self.stdout.write(f"  • {detail}")
            
            self.stdout.write(self.style.SUCCESS('\n✓ Fixes applied'))
        elif not fix and (report['errors'] or report['warnings']):
            self.stdout.write(
                self.style.WARNING('\nUse --fix to attempt automatic repairs')
            )
