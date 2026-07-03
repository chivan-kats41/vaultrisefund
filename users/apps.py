"""
App Configuration for Users App
File: users/apps.py

This file registers the signals when the app is loaded.
IMPORTANT: The ready() method imports signals.py to register signal handlers.
"""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    verbose_name = 'User Management'
    
    def ready(self):
        """
        Import signal handlers when app is ready.
        This ensures signals are registered before any models are used.
        """
        try:
            # Import signals to register them
            import users.signals
            print("✅ User signals registered successfully")
        except ImportError as e:
            print(f"⚠️ Warning: Could not import user signals: {e}")
        except Exception as e:
            print(f"❌ Error registering user signals: {e}")