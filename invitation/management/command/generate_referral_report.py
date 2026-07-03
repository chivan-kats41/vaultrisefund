"""
File: invitation/management/commands/generate_referral_report.py

Generate comprehensive referral system reports.

Usage:
    python manage.py generate_referral_report --month 8 --year 2024
    python manage.py generate_referral_report --output report.csv
    python manage.py generate_referral_report --format json
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime
from calendar import monthrange
import json
import csv

from invitation.utils import generate_monthly_report, get_system_health


class Command(BaseCommand):
    help = 'Generate comprehensive referral system reports'

    def add_arguments(self, parser):
        parser.add_argument(
            '--month',
            type=int,
            default=timezone.now().month,
            help='Month to generate report for (1-12)',
        )
        parser.add_argument(
            '--year',
            type=int,
            default=timezone.now().year,
            help='Year to generate report for',
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['text', 'json', 'csv'],
            default='text',
            help='Output format',
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path (optional)',
        )
        parser.add_argument(
            '--health',
            action='store_true',
            help='Show system health metrics',
        )

    def handle(self, *args, **options):
        month = options['month']
        year = options['year']
        format_type = options['format']
        output_file = options['output']
        show_health = options['health']

        if show_health:
            self._show_system_health()
            return

        # Validate month
        if month < 1 or month > 12:
            self.stdout.write(self.style.ERROR('Month must be between 1 and 12'))
            return

        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'REFERRAL REPORT - {year}/{month:02d}'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        # Generate report
        report = generate_monthly_report(year, month)

        if format_type == 'text':
            output = self._format_text(report)
        elif format_type == 'json':
            output = json.dumps(report, indent=2, default=str)
        elif format_type == 'csv':
            output = self._format_csv(report)

        # Output
        if output_file:
            with open(output_file, 'w') as f:
                f.write(output)
            self.stdout.write(
                self.style.SUCCESS(f'\nReport saved to: {output_file}')
            )
        else:
            self.stdout.write(output)

    def _format_text(self, report):
        output = []
        
        output.append(f"\nPeriod: {report['period']['start_date']} to {report['period']['end_date']}")
        
        output.append("\n\nRELATIONSHIPS")
        output.append("-" * 40)
        output.append(f"New relationships: {report['relationships']['new_total']}")
        output.append(f"New active: {report['relationships']['new_active']}")
        
        output.append("\nBy Level:")
        for level, stats in report['relationships']['by_level'].items():
            output.append(f"  Level {level}: {stats['total']} total, {stats['active']} active")
        
        output.append("\n\nCOMMISSIONS")
        output.append("-" * 40)
        output.append(f"Total count: {report['commissions']['total_count']}")
        output.append(f"Total amount: UGX {report['commissions']['total_amount']:,.2f}")
        
        output.append("\nBy Level:")
        for level, stats in report['commissions']['by_level'].items():
            output.append(
                f"  Level {level}: {stats['count']} commissions, "
                f"UGX {stats['total']:,.2f}"
            )
        
        output.append("\n\nMARKETING")
        output.append("-" * 40)
        output.append(f"Total clicks: {report['marketing']['total_clicks']}")
        output.append(f"Conversions: {report['marketing']['conversions']}")
        output.append(f"Conversion rate: {report['marketing']['conversion_rate']:.2f}%")
        
        if report['top_performers']:
            output.append("\n\nTOP PERFORMERS")
            output.append("-" * 40)
            for i, performer in enumerate(report['top_performers'][:10], 1):
                output.append(
                    f"{i}. {performer['referrer__username']}: "
                    f"{performer['count']} referrals, "
                    f"UGX {performer['commission'] or 0:,.2f}"
                )
        
        return '\n'.join(output)

    def _format_csv(self, report):
        output = []
        
        # Header
        output.append("Metric,Value")
        
        # Period
        output.append(f"Start Date,{report['period']['start_date']}")
        output.append(f"End Date,{report['period']['end_date']}")
        
        # Relationships
        output.append(f"New Relationships,{report['relationships']['new_total']}")
        output.append(f"New Active Relationships,{report['relationships']['new_active']}")
        
        # Commissions
        output.append(f"Total Commissions,{report['commissions']['total_count']}")
        output.append(f"Total Commission Amount,{report['commissions']['total_amount']}")
        
        # Marketing
        output.append(f"Total Clicks,{report['marketing']['total_clicks']}")
        output.append(f"Conversions,{report['marketing']['conversions']}")
        output.append(f"Conversion Rate,{report['marketing']['conversion_rate']}")
        
        return '\n'.join(output)

    def _show_system_health(self):
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('SYSTEM HEALTH'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        health = get_system_health()

        # Health score
        score = health['health_score']
        status = health['status']
        
        if status == 'healthy':
            style = self.style.SUCCESS
        elif status == 'warning':
            style = self.style.WARNING
        else:
            style = self.style.ERROR

        self.stdout.write(f"\nHealth Score: {style(f'{score}/100')} ({status})")

        # Metrics
        metrics = health['metrics']
        self.stdout.write("\nMETRICS")
        self.stdout.write("-" * 40)
        self.stdout.write(f"Total users: {metrics['total_users']}")
        self.stdout.write(f"Total relationships: {metrics['total_relationships']}")
        self.stdout.write(f"Active relationships: {metrics['active_relationships']}")
        self.stdout.write(f"Activation rate: {metrics['activation_rate']:.2f}%")
        
        self.stdout.write(f"\nPending commissions: {metrics['pending_commissions_count']}")
        self.stdout.write(f"Pending amount: UGX {metrics['pending_commissions_amount']:,.2f}")
        
        self.stdout.write("\nRECENT ACTIVITY (Last 7 days)")
        self.stdout.write("-" * 40)
        recent = metrics['recent_activity']
        self.stdout.write(f"New relationships: {recent['new_relationships_7d']}")
        self.stdout.write(f"Commissions paid: {recent['commissions_paid_7d']}")

        # Recommendations
        if health['recommendations']:
            self.stdout.write("\nRECOMMENDATIONS")
            self.stdout.write("-" * 40)
            for rec in health['recommendations']:
                self.stdout.write(self.style.WARNING(f"• {rec}"))
