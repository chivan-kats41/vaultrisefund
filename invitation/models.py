from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

# ✅ FIX: Import investment models from store — do NOT redefine them here.
# Redefining them caused duplicate db_table errors.
from store.models import (
    InvestmentProduct,
    UserInvestment,
    DailyEarningLog,
)


# ==================== REFERRAL MODELS ====================

class CommissionRate(models.Model):
    level      = models.IntegerField()          # 1, 2, or 3
    vip_level  = models.IntegerField(default=0)
    rate       = models.DecimalField(max_digits=5, decimal_places=2)
    is_active  = models.BooleanField(default=True)

    class Meta:
        unique_together = ('level', 'vip_level')

    def __str__(self):
        return f"Level {self.level} VIP{self.vip_level}: {self.rate}%"

    @classmethod
    def get_rate(cls, level, vip_level=0):
        defaults = {1: Decimal('12.00'), 2: Decimal('8.00'), 3: Decimal('16.00')}
        try:
            return cls.objects.get(level=level, vip_level=vip_level, is_active=True).rate
        except cls.DoesNotExist:
            return defaults.get(level, Decimal('0.00'))


class ReferralRelationship(models.Model):
    referrer                = models.ForeignKey(
                                settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='referrals_made'
                              )
    referee                 = models.ForeignKey(
                                settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='referred_by_rel'
                              )
    level                   = models.IntegerField()   # 1, 2, or 3
    is_active               = models.BooleanField(default=False)
    total_purchases         = models.IntegerField(default=0)
    total_purchase_amount   = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_commission_earned = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    created_at              = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('referrer', 'referee', 'level')

    def __str__(self):
        return f"L{self.level}: {self.referrer} -> {self.referee}"

    def activate(self):
        self.is_active = True
        self.save(update_fields=['is_active'])

    def add_purchase(self, amount):
        self.total_purchases       += 1
        self.total_purchase_amount += amount
        self.save(update_fields=['total_purchases', 'total_purchase_amount'])

    def add_commission(self, amount):
        self.total_commission_earned += amount
        self.save(update_fields=['total_commission_earned'])


class Commission(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('paid',      'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    referrer          = models.ForeignKey(
                          settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                          related_name='commissions_earned'
                        )
    referee           = models.ForeignKey(
                          settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                          related_name='commissions_generated'
                        )
    relationship      = models.ForeignKey(
                          ReferralRelationship, on_delete=models.CASCADE,
                          related_name='commissions'
                        )
    level             = models.IntegerField()
    order_amount      = models.DecimalField(max_digits=15, decimal_places=2)
    commission_rate   = models.DecimalField(max_digits=5, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=15, decimal_places=2)
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    transaction       = models.ForeignKey(
                          'users.Transaction', on_delete=models.SET_NULL,
                          null=True, blank=True, related_name='commissions'
                        )
    created_at        = models.DateTimeField(auto_now_add=True)
    paid_at           = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Commission L{self.level}: {self.referrer} UGX {self.commission_amount}"

    def mark_as_paid(self, transaction=None):
        self.status  = 'paid'
        self.paid_at = timezone.now()
        if transaction:
            self.transaction = transaction
        self.save(update_fields=['status', 'paid_at', 'transaction'])

    def cancel(self, reason=None):
        self.status = 'cancelled'
        self.save(update_fields=['status'])


class InvitationClick(models.Model):
    referrer        = models.ForeignKey(
                        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                        related_name='invitation_clicks'
                      )
    ip_address      = models.GenericIPAddressField(null=True, blank=True)
    user_agent      = models.TextField(blank=True)
    converted       = models.BooleanField(default=False)
    registered_user = models.ForeignKey(
                        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                        null=True, blank=True, related_name='registration_click'
                      )
    clicked_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Click by {self.referrer} at {self.clicked_at}"