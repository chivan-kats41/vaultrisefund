from django.db import models


class HoneypotAttempt(models.Model):
    ip_address   = models.GenericIPAddressField()
    path         = models.CharField(max_length=255)
    method       = models.CharField(max_length=10, default='GET')
    email_tried  = models.CharField(max_length=255, blank=True)
    user_agent   = models.CharField(max_length=500, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Honeypot Attempt'
        verbose_name_plural = 'Honeypot Attempts'

    def __str__(self):
        return f"{self.ip_address} → {self.path} ({self.created_at:%Y-%m-%d %H:%M})"