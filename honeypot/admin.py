from django.contrib import admin
from .models import HoneypotAttempt


@admin.register(HoneypotAttempt)
class HoneypotAttemptAdmin(admin.ModelAdmin):
    list_display  = ('ip_address', 'method', 'path', 'email_tried', 'created_at')
    list_filter   = ('method', 'created_at')
    search_fields = ('ip_address', 'email_tried', 'path')
    ordering      = ('-created_at',)
    readonly_fields = ('ip_address', 'path', 'method', 'email_tried', 'user_agent', 'created_at')

    def has_add_permission(self, request):
        return False  # these are only ever created by the honeypot views