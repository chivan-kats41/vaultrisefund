# services/models.py
from django.db import models
from django.conf import settings


class SupportTicket(models.Model):
    STATUS_CHOICES = [
        ('open',     'Open'),
        ('pending',  'Pending Admin Reply'),
        ('resolved', 'Resolved'),
    ]
    user       = models.ForeignKey(
                   settings.AUTH_USER_MODEL,
                   on_delete=models.CASCADE,
                   related_name='support_tickets'
                 )
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Ticket #{self.id} — {self.user.username} [{self.status}]"


class SupportMessage(models.Model):
    SENDER_CHOICES = [
        ('user',  'User'),
        ('admin', 'Admin'),
        ('bot',   'Auto-reply Bot'),
    ]
    ticket      = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='messages')
    sender_type = models.CharField(max_length=10, choices=SENDER_CHOICES)
    user        = models.ForeignKey(
                    settings.AUTH_USER_MODEL,
                    on_delete=models.SET_NULL,
                    null=True, blank=True,
                    related_name='support_messages'
                  )
    message     = models.TextField(blank=True)
    is_read     = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.sender_type}] {self.message[:50]}"


class SupportMessageImage(models.Model):
    """Multiple images per message — for proof uploads, screenshots, etc."""
    message    = models.ForeignKey(SupportMessage, on_delete=models.CASCADE, related_name='images')
    image      = models.ImageField(upload_to='support_images/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for message #{self.message_id}"