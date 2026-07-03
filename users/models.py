"""
Models for the Users app - Investment/Financial Platform
File: users/models.py
"""

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
import uuid


class UserProfile(models.Model):
    """Extended user profile with financial information and VIP status."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        help_text="Link to Django User model"
    )

    # Personal Information
    nickname    = models.CharField(max_length=100, blank=True, null=True)
    avatar      = models.ImageField(upload_to='avatars/', blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    # Balance Management
    recharge_balance    = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    withdrawal_balance  = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    commission_balance  = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # VIP Information
    vip_level = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(8)]
    )
    total_investment    = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    vip_progress        = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # User Statistics
    total_orders        = models.IntegerField(default=0)
    total_earnings      = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_withdrawn     = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_recharged     = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Security
    transaction_password        = models.CharField(max_length=128, blank=True, null=True)
    transaction_password_set    = models.BooleanField(default=False)

    # Referral System
    referral_code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    referred_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referrals'
    )
    total_referrals     = models.IntegerField(default=0)
    referral_earnings   = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Account Status
    is_active   = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)

    # Timestamps
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)
    last_login_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = "User Profile"
        verbose_name_plural = "User Profiles"
        ordering            = ['-created_at']

    def __str__(self):
        display_name = self.nickname or self.user.username
        return f"{display_name} (VIP {self.vip_level})"

    def generate_referral_code(self):
        """Generate unique referral code if not exists"""
        if not self.referral_code:
            self.referral_code = f"REF{self.user.id}{uuid.uuid4().hex[:6].upper()}"
            self.save()
        return self.referral_code

    def update_vip_level(self):
        """
        Recalculate vip_level from total_investment against the VIPLevel
        thresholds and persist it if it changed.

        This is the missing piece: total_investment gets bumped on every
        purchase, but nothing previously looked up which VIPLevel that
        total now qualifies for and wrote it back onto vip_level. Call this
        any time total_investment changes (e.g. right after a purchase).

        Returns True if the level changed (useful for firing a
        "VIP Upgraded!" notification), False otherwise.
        """
        # Highest level whose required_investment the user's total meets.
        qualifying = VIPLevel.objects.filter(
            is_active=True,
            required_investment__lte=self.total_investment
        ).order_by('-level').first()

        new_level = qualifying.level if qualifying else 0

        if new_level != self.vip_level:
            old_level = self.vip_level
            self.vip_level = new_level
            self.save(update_fields=['vip_level'])
            return True, old_level, new_level

        return False, self.vip_level, self.vip_level


class Wallet(models.Model):
    """User's mobile money wallet information for withdrawals."""
    WALLET_TYPES = [
        ('MTN',    'MTN Mobile Money'),
        ('Airtel', 'Airtel Money'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet'
    )

    wallet_type     = models.CharField(max_length=20, choices=WALLET_TYPES)
    wallet_account  = models.CharField(max_length=20)
    owner_name      = models.CharField(max_length=100)
    usdt_wallet     = models.CharField(max_length=200, blank=True, null=True)

    is_verified         = models.BooleanField(default=False)
    is_active           = models.BooleanField(default=True)
    verification_date   = models.DateTimeField(null=True, blank=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Wallet"
        verbose_name_plural = "Wallets"

    def __str__(self):
        return f"{self.user.username} - {self.wallet_type} ({self.wallet_account})"


class Notification(models.Model):
    """User notifications displayed in mail.html."""
    NOTIFICATION_TYPES = [
        ('system',               'System Notification'),
        ('promotion',            'Promotion'),
        ('vip_upgrade',          'VIP Upgrade'),
        ('withdrawal_approved',  'Withdrawal Approved'),
        ('withdrawal_rejected',  'Withdrawal Rejected'),
        ('recharge_confirmed',   'Recharge Confirmed'),
        ('settlement',           'Settlement Notification'),
        ('referral',             'Referral Notification'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True
    )

    title               = models.CharField(max_length=200)
    message             = models.TextField()
    notification_type   = models.CharField(max_length=30, choices=NOTIFICATION_TYPES, default='system')

    image           = models.ImageField(upload_to='notifications/', blank=True, null=True)
    link_url        = models.URLField(blank=True, null=True)

    is_read         = models.BooleanField(default=False)
    read_at         = models.DateTimeField(null=True, blank=True)
    is_broadcast    = models.BooleanField(default=False)
    is_important    = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Notification"
        verbose_name_plural = "Notifications"
        ordering            = ['-created_at']

    def __str__(self):
        target = self.user.username if self.user else "All Users"
        return f"{self.title} - {target}"


class Order(models.Model):
    """User's product purchases/investments."""
    STATUS_CHOICES = [
        ('normal',    'Normal'),
        ('finish',    'Finish'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders'
    )

    # ✅ FIX: use string reference 'store.InvestmentProduct' — no import needed,
    # no circular dependency possible.
    product = models.ForeignKey(
        'store.InvestmentProduct',
        on_delete=models.PROTECT,
        related_name='orders'
    )

    order_number    = models.CharField(max_length=50, unique=True)
    quantity        = models.IntegerField(default=1)
    total_amount    = models.DecimalField(max_digits=12, decimal_places=2)
    daily_income    = models.DecimalField(max_digits=12, decimal_places=2)
    total_income_generated  = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    estimated_total_income  = models.DecimalField(max_digits=12, decimal_places=2)

    duration_days   = models.IntegerField()
    days_completed  = models.IntegerField(default=0)
    days_remaining  = models.IntegerField()
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='normal')

    purchase_date           = models.DateTimeField(auto_now_add=True)
    start_date              = models.DateField()
    end_date                = models.DateField()
    completed_date          = models.DateTimeField(null=True, blank=True)
    next_settlement_date    = models.DateField(null=True, blank=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Order"
        verbose_name_plural = "Orders"
        ordering            = ['-created_at']

    def __str__(self):
        return f"{self.order_number} - {self.user.username}"

    def sync_progress(self):
        """
        Recompute this order's progress based on elapsed time since start_date.

        - Marks each Settlement whose day has elapsed as paid (is_paid=True),
          leaving future days untouched (still pending).
        - Sums the paid settlements into total_income_generated, so the
          "income generated" figure grows day by day while the order is
          in progress.
        - That income is NOT credited to the user's withdrawal balance while
          the order is still active — it's just a running tally for display.
        - Only once every day of the duration has elapsed does the order get
          finalized: status -> 'finish' and the full earned amount is
          credited to the user's withdrawal_balance in one go.

        Self-healing: since this is driven off the calendar date rather than
        a daily cron tick, it produces the correct state any time it's
        called (e.g. on page load), even if nobody viewed the order for
        several days in a row.
        """
        if self.status != 'normal':
            return self

        today = timezone.now().date()
        elapsed = (today - self.start_date).days
        elapsed_days = max(0, min(self.duration_days, elapsed))

        settlements = list(self.settlements.order_by('day_number'))

        for s in settlements:
            if s.day_number <= elapsed_days and not s.is_paid:
                s.is_paid = True
                s.paid_at = timezone.now()
                s.save(update_fields=['is_paid', 'paid_at'])

        total_generated = sum(
            (s.amount for s in settlements if s.is_paid),
            Decimal('0.00')
        )

        update_fields = []

        if self.days_completed != elapsed_days:
            self.days_completed = elapsed_days
            update_fields.append('days_completed')

        new_days_remaining = max(0, self.duration_days - elapsed_days)
        if self.days_remaining != new_days_remaining:
            self.days_remaining = new_days_remaining
            update_fields.append('days_remaining')

        if self.total_income_generated != total_generated:
            self.total_income_generated = total_generated
            update_fields.append('total_income_generated')

        # Finalize the order once every day has been settled — this is the
        # only point at which earnings actually move into the user's balance.
        if elapsed_days >= self.duration_days and settlements:
            self.status = 'finish'
            self.completed_date = timezone.now()
            self.next_settlement_date = None
            update_fields += ['status', 'completed_date', 'next_settlement_date']

            if update_fields:
                self.save(update_fields=update_fields)

            self._credit_completed_earnings(total_generated)
            return self

        if update_fields:
            self.save(update_fields=update_fields)

        return self

    def _credit_completed_earnings(self, amount):
        """Credit the finished order's total earnings to the user's
        withdrawal balance, exactly once, with a Transaction record."""
        import uuid as _uuid

        if amount <= 0:
            return

        profile = getattr(self.user, 'profile', None)
        if profile is None:
            return

        # Guard against double-crediting if sync_progress is ever called
        # again on an already-finished order.
        already_credited = Transaction.objects.filter(
            reference_id=self.order_number,
            transaction_type='settlement',
        ).exists()
        if already_credited:
            return

        balance_before = profile.withdrawal_balance
        profile.withdrawal_balance += amount
        profile.total_earnings += amount
        profile.save(update_fields=['withdrawal_balance', 'total_earnings'])

        Transaction.objects.create(
            user=self.user,
            transaction_number=f"TXN{timezone.now().strftime('%Y%m%d%H%M%S')}{_uuid.uuid4().hex[:6].upper()}",
            transaction_type='settlement',
            amount=amount,
            balance_type='withdrawal_balance',
            balance_before=balance_before,
            balance_after=profile.withdrawal_balance,
            description=f'Investment completed: {self.product.name} ({self.order_number})',
            reference_id=self.order_number,
            status='completed',
        )


class Recharge(models.Model):
    """Recharge/Deposit records from recharge.html."""
    PAYMENT_METHODS = [
        ('MTN',    'MTN Mobile Money'),
        ('Airtel', 'Airtel Money'),
        ('USDT',   'USDT (TRC-20)'),
    ]

    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('processing', 'Processing'),
        ('completed',  'Completed'),
        ('failed',     'Failed'),
        ('cancelled',  'Cancelled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recharges'
    )

    recharge_number     = models.CharField(max_length=50, unique=True)
    amount              = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method      = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    user_payment_account    = models.CharField(max_length=20)
    merchant_account        = models.CharField(max_length=20)
    merchant_name           = models.CharField(max_length=100)

    payment_screenshot          = models.ImageField(upload_to='recharge_proofs/', blank=True, null=True)
    external_transaction_id     = models.CharField(max_length=100, blank=True, null=True)

    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_recharges'
    )
    admin_notes = models.TextField(blank=True, null=True)

    created_at      = models.DateTimeField(auto_now_add=True)
    expires_at      = models.DateTimeField()
    completed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = "Recharge"
        verbose_name_plural = "Recharges"
        ordering            = ['-created_at']

    def __str__(self):
        return f"{self.recharge_number} - {self.user.username}"


class Settlement(models.Model):
    """Daily income settlement records for orders."""
    order = models.ForeignKey(
        'Order',
        on_delete=models.CASCADE,
        related_name='settlements'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='settlements'
    )

    settlement_date = models.DateField()
    amount          = models.DecimalField(max_digits=12, decimal_places=2)
    day_number      = models.IntegerField()

    is_paid     = models.BooleanField(default=False)
    paid_at     = models.DateTimeField(null=True, blank=True)
    credited_to = models.CharField(max_length=20, default='withdrawal_balance')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Settlement"
        verbose_name_plural = "Settlements"
        ordering            = ['-settlement_date', '-created_at']
        unique_together     = ['order', 'day_number']

    def __str__(self):
        return f"{self.order.order_number} - Day {self.day_number}"


class Transaction(models.Model):
    """All financial transactions for balance.html."""
    TRANSACTION_TYPES = [
        ('recharge',             'Recharge'),
        ('withdrawal',           'Withdrawal'),
        ('buy_product',          'Buy Product'),
        ('settlement',           'Settlement Income'),
        ('promotion_commission', 'Promotion Commission'),
        ('system_deduction',     'System Deduction'),
        ('referral_bonus',       'Referral Bonus'),
        ('vip_reward',           'VIP Reward'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='transactions'
    )

    transaction_number  = models.CharField(max_length=50, unique=True)
    transaction_type    = models.CharField(max_length=30, choices=TRANSACTION_TYPES)
    amount              = models.DecimalField(max_digits=12, decimal_places=2)

    balance_type    = models.CharField(max_length=30)
    balance_before  = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after   = models.DecimalField(max_digits=12, decimal_places=2)

    description     = models.TextField(blank=True, null=True)
    reference_id    = models.CharField(max_length=100, blank=True, null=True)
    status          = models.CharField(max_length=20, default='completed')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Transaction"
        verbose_name_plural = "Transactions"
        ordering            = ['-created_at']

    def __str__(self):
        return f"{self.transaction_number} - {self.user.username}"


class Withdrawal(models.Model):
    """Withdrawal requests from withdrawal.html."""
    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('processing', 'Processing'),
        ('completed',  'Completed'),
        ('rejected',   'Rejected'),
        ('cancelled',  'Cancelled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='withdrawals'
    )
    wallet = models.ForeignKey(
        'Wallet',
        on_delete=models.PROTECT,
        related_name='withdrawals'
    )

    withdrawal_number   = models.CharField(max_length=50, unique=True)
    amount              = models.DecimalField(max_digits=12, decimal_places=2)
    withdrawal_fee_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'))
    withdrawal_fee      = models.DecimalField(max_digits=12, decimal_places=2)
    net_amount          = models.DecimalField(max_digits=12, decimal_places=2)

    destination_wallet_type = models.CharField(max_length=20)
    destination_account     = models.CharField(max_length=20)
    destination_name        = models.CharField(max_length=100)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_withdrawals'
    )
    rejection_reason    = models.TextField(blank=True, null=True)
    admin_notes         = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Withdrawal"
        verbose_name_plural = "Withdrawals"
        ordering            = ['-created_at']

    def __str__(self):
        return f"{self.withdrawal_number} - {self.user.username}"


class VIPLevel(models.Model):
    """VIP Level configuration with benefits and requirements."""
    level                   = models.IntegerField(unique=True)
    name                    = models.CharField(max_length=50)
    required_investment     = models.DecimalField(max_digits=12, decimal_places=2)

    daily_withdrawal_limit  = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('5000000.00'))
    commission_rate         = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    max_orders_per_day      = models.IntegerField(default=30000)
    withdrawal_fee_rate     = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'))

    color_code  = models.CharField(max_length=7, default="#e0e0e0")
    icon        = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    is_active   = models.BooleanField(default=True)

    class Meta:
        verbose_name        = "VIP Level"
        verbose_name_plural = "VIP Levels"
        ordering            = ['level']

    def __str__(self):
        return f"VIP {self.level} - {self.name}"


# ==================== SIGNALS ====================

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create UserProfile when User is created."""
    if created:
        profile = UserProfile.objects.create(user=instance)
        profile.generate_referral_code()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved."""
    if hasattr(instance, 'profile'):
        instance.profile.save()

        # Add this to your users/models.py (or accounts/models.py — wherever your user model lives)

import random
import string
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class PasswordResetCode(models.Model):
    user       = models.ForeignKey(
                   settings.AUTH_USER_MODEL,
                   on_delete=models.CASCADE,
                   related_name='reset_codes'
                 )
    code       = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used    = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self):
        """Code is valid for 15 minutes and not yet used."""
        expiry = self.created_at + timedelta(minutes=15)
        return not self.is_used and timezone.now() < expiry

    @classmethod
    def generate_code(cls):
        return ''.join(random.choices(string.digits, k=6))

    def __str__(self):
        return f"{self.user.email} — {self.code} ({'used' if self.is_used else 'active'})"