"""
Django App Configuration for Invitation System
File: invitation/apps.py

CRITICAL: This file registers signal handlers.
Without this, automatic commission calculation won't work!
"""

from django.apps import AppConfig


class InvitationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'invitation'
    verbose_name = 'Invitation & Referral System'
    
    def ready(self):
        """
        Import signal handlers when Django starts.
        This ensures all signals are connected and working.
        """
        import invitation.signals  # noqa
        print("✓ Invitation signals registered successfully")