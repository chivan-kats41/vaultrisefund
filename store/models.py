from django.db import models
from category.models import category as Category


class InvestmentProduct(models.Model):
    name          = models.CharField(max_length=100)
    category      = models.ForeignKey(
                        Category,
                        on_delete=models.SET_NULL,
                        null=True,
                        related_name='products'
                    )
    image         = models.ImageField(upload_to='products/', null=True, blank=True)
    vip_required  = models.IntegerField(default=0)
    price         = models.DecimalField(max_digits=15, decimal_places=2)
    duration_days = models.IntegerField()
    daily_earning = models.DecimalField(max_digits=15, decimal_places=2)
    total_return  = models.DecimalField(max_digits=15, decimal_places=2)
    max_shares    = models.IntegerField(default=100)
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'investment_products'
        ordering = ['vip_required', 'price']

    def __str__(self):
        return f"{self.name} (VIP{self.vip_required})"

    @property
    def category_name(self):
        return self.category.category_name if self.category else ''

    def as_dict(self):
        return {
            'id':                self.id,
            'product_name':      self.name,
            'category_name':     self.category_name,
            'image':             self.image.url if self.image else '',
            'minimum_vip_level': self.vip_required,
            'price':             str(self.price),
            'revenue_days':      self.duration_days,
            'daily_income':      str(self.daily_earning),
            'total_income':      str(self.total_return),
            'max_shares':        self.max_shares,
            'currency':          'UGX',
        }


class UserInvestment(models.Model):
    STATUS_CHOICES = [
        ('active',    'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    user         = models.ForeignKey(
                       'users.UserProfile', on_delete=models.CASCADE,
                       related_name='investments'
                   )
    product      = models.ForeignKey(
                       InvestmentProduct, on_delete=models.PROTECT,
                       related_name='user_investments'
                   )
    shares       = models.IntegerField(default=1)
    amount_paid  = models.DecimalField(max_digits=15, decimal_places=2)
    start_date   = models.DateField()
    end_date     = models.DateField()
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    total_earned = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    last_payout  = models.DateField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_investments'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.nickname} -> {self.product.name} x{self.shares}"

    @property
    def daily_earning(self):
        return self.product.daily_earning * self.shares

    @property
    def progress_percent(self):
        from datetime import date
        today      = date.today()
        total_days = (self.end_date - self.start_date).days
        elapsed    = (today - self.start_date).days
        if total_days <= 0:
            return 100
        return min(100, int((elapsed / total_days) * 100))

    @property
    def days_remaining(self):
        from datetime import date
        return max(0, (self.end_date - date.today()).days)


class DailyEarningLog(models.Model):
    investment  = models.ForeignKey(
                      UserInvestment, on_delete=models.CASCADE,
                      related_name='earning_logs'
                  )
    amount      = models.DecimalField(max_digits=15, decimal_places=2)
    date        = models.DateField()
    credited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = 'daily_earning_logs'
        unique_together = ('investment', 'date')
        ordering        = ['-date']

    def __str__(self):
        return f"{self.investment} | {self.date} | UGX {self.amount}"


# ── Signals ───────────────────────────────────────────────────────────────────
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=InvestmentProduct)
def on_product_save(sender, instance, **kwargs):
    pass