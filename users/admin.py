from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, Count
from django.urls import reverse
from django.utils.safestring import mark_safe
from decimal import Decimal

from .models import (
    UserProfile, VIPLevel, Wallet, Order,
    Settlement, Transaction, Recharge, Withdrawal, Notification
)


# ── helper: pre-format a Decimal/float as a UGX string ───────────────────────
def ugx(amount):
    """Return a plain Python str like '1,234.50' — safe to pass to format_html."""
    try:
        return f"{float(amount):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


# ==================== USER PROFILE ADMIN ====================

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):

    list_display = [
        'user_display', 'nickname', 'vip_badge', 'total_balance_display',
        'recharge_balance', 'withdrawal_balance', 'total_orders',
        'is_verified', 'created_at'
    ]
    list_filter = ['vip_level', 'is_verified', 'is_active', 'created_at']
    search_fields = [
        'user__username', 'user__email', 'nickname',
        'phone_number', 'referral_code'
    ]
    readonly_fields = [
        'user', 'created_at', 'updated_at', 'last_login_at',
        'total_balance_display', 'referral_stats_display'
    ]

    fieldsets = (
        ('User Information', {
            'fields': ('user', 'nickname', 'avatar', 'phone_number')
        }),
        ('Balance Management', {
            'fields': (
                'recharge_balance', 'withdrawal_balance', 'commission_balance',
                'total_balance_display'
            )
        }),
        ('VIP Information', {
            'fields': ('vip_level', 'total_investment', 'vip_progress')
        }),
        ('Statistics', {
            'fields': (
                'total_orders', 'total_earnings',
                'total_withdrawn', 'total_recharged'
            )
        }),
        ('Security', {
            'fields': ('transaction_password_set',),
            'classes': ('collapse',)
        }),
        ('Referral System', {
            'fields': (
                'referral_code', 'referred_by', 'total_referrals',
                'referral_earnings', 'referral_stats_display'
            ),
            'classes': ('collapse',)
        }),
        ('Account Status', {
            'fields': ('is_active', 'is_verified')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_login_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['verify_users', 'upgrade_vip', 'add_bonus_balance']

    def user_display(self, obj):
        try:
            meta       = obj.user._meta
            url = reverse(
                f'admin:{meta.app_label}_{meta.model_name}_change',
                args=[obj.user.id]
            )
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        except Exception:
            return obj.user.username
    user_display.short_description = 'User'

    def vip_badge(self, obj):
        colors = {
            0: '#9e9e9e', 1: '#2196f3', 2: '#03a9f4', 3: '#ffc107',
            4: '#9c27b0', 5: '#4caf50', 6: '#ff5722', 7: '#e91e63', 8: '#00bcd4',
        }
        color = colors.get(obj.vip_level, '#9e9e9e')
        return format_html(
            '<span style="background-color:{}; color:white; '
            'padding:3px 10px; border-radius:12px; font-weight:bold;">'
            'VIP {}</span>',
            color, obj.vip_level
        )
    vip_badge.short_description = 'VIP Level'

    def total_balance_display(self, obj):
        total = obj.recharge_balance + obj.withdrawal_balance + obj.commission_balance
        return format_html(
            '<strong style="color:#4caf50;">UGX {}</strong>', ugx(total)
        )
    total_balance_display.short_description = 'Total Balance'

    def referral_stats_display(self, obj):
        return format_html(
            'Total Referrals: <strong>{}</strong><br>'
            'Referral Earnings: <strong>UGX {}</strong>',
            obj.total_referrals, ugx(obj.referral_earnings)
        )
    referral_stats_display.short_description = 'Referral Statistics'

    def verify_users(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f'{updated} users verified successfully.')
    verify_users.short_description = 'Verify selected users'

    def upgrade_vip(self, request, queryset):
        for profile in queryset:
            if profile.vip_level < 8:
                profile.vip_level += 1
                profile.save()
        self.message_user(request, f'{queryset.count()} users upgraded.')
    upgrade_vip.short_description = 'Upgrade VIP level'

    def add_bonus_balance(self, request, queryset):
        bonus = Decimal('10000')
        for profile in queryset:
            profile.withdrawal_balance += bonus
            profile.save()
        self.message_user(request, f'Added UGX {ugx(bonus)} bonus to {queryset.count()} users.')
    add_bonus_balance.short_description = 'Add UGX 10,000 bonus'


# ==================== VIP LEVEL ADMIN ====================

@admin.register(VIPLevel)
class VIPLevelAdmin(admin.ModelAdmin):

    list_display  = [
        'level_badge', 'name', 'required_investment_display',
        'commission_rate', 'withdrawal_fee_rate', 'max_orders_per_day', 'is_active'
    ]
    list_filter   = ['is_active']
    search_fields = ['name', 'level']

    fieldsets = (
        ('Basic Information', {
            'fields': ('level', 'name', 'required_investment', 'description')
        }),
        ('Benefits', {
            'fields': (
                'daily_withdrawal_limit', 'commission_rate',
                'max_orders_per_day', 'withdrawal_fee_rate'
            )
        }),
        ('Display Settings', {
            'fields': ('color_code', 'icon', 'is_active')
        }),
    )

    def level_badge(self, obj):
        return format_html(
            '<span style="background-color:{}; color:white; '
            'padding:5px 15px; border-radius:15px; font-weight:bold;">VIP {}</span>',
            obj.color_code, obj.level
        )
    level_badge.short_description = 'Level'

    def required_investment_display(self, obj):
        return format_html('<strong>UGX {}</strong>', ugx(obj.required_investment))
    required_investment_display.short_description = 'Required Investment'


# ==================== WALLET ADMIN ====================

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):

    list_display  = [
        'user', 'wallet_type_badge', 'wallet_account',
        'owner_name', 'is_verified', 'is_active', 'created_at'
    ]
    list_filter   = ['wallet_type', 'is_verified', 'is_active', 'created_at']
    search_fields = ['user__username', 'wallet_account', 'owner_name', 'usdt_wallet']
    readonly_fields = ['created_at', 'updated_at', 'verification_date']

    fieldsets = (
        ('User & Wallet Type', {'fields': ('user', 'wallet_type')}),
        ('Wallet Details',     {'fields': ('wallet_account', 'owner_name', 'usdt_wallet')}),
        ('Verification',       {'fields': ('is_verified', 'verification_date', 'is_active')}),
        ('Timestamps',         {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    actions = ['verify_wallets', 'deactivate_wallets']

    def wallet_type_badge(self, obj):
        colors = {'MTN': '#ffcb05', 'Airtel': '#e60000'}
        color  = colors.get(obj.wallet_type, '#666')
        return format_html(
            '📱 <span style="color:{}; font-weight:bold;">{}</span>',
            color, obj.wallet_type
        )
    wallet_type_badge.short_description = 'Wallet Type'

    def verify_wallets(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(is_verified=True, verification_date=timezone.now())
        self.message_user(request, f'{updated} wallets verified successfully.')
    verify_wallets.short_description = 'Verify selected wallets'

    def deactivate_wallets(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} wallets deactivated.')
    deactivate_wallets.short_description = 'Deactivate selected wallets'


# ==================== ORDER ADMIN ====================

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    list_display = [
        'order_number', 'user', 'product', 'total_amount_display',
        'status_badge', 'progress_bar', 'daily_income_display', 'purchase_date'
    ]
    list_filter   = ['status', 'purchase_date', 'product']
    search_fields = ['order_number', 'user__username', 'product__name']

    actions = ['complete_orders', 'cancel_orders']

    def get_readonly_fields(self, request, obj=None):
        base = ['order_number', 'purchase_date', 'created_at', 'updated_at', 'completed_date']
        if obj:
            base.append('progress_display')
        return base

    def get_fieldsets(self, request, obj=None):
        if obj:
            return (
                ('Order Information',   {'fields': ('order_number', 'user', 'product', 'quantity')}),
                ('Financial Details',   {'fields': ('total_amount', 'daily_income', 'total_income_generated', 'estimated_total_income')}),
                ('Duration & Progress', {'fields': ('duration_days', 'days_completed', 'days_remaining', 'progress_display', 'status')}),
                ('Dates',               {'fields': ('purchase_date', 'start_date', 'end_date', 'next_settlement_date', 'completed_date')}),
            )
        return (
            ('Order Information',   {'fields': ('user', 'product', 'quantity')}),
            ('Financial Details',   {'fields': ('total_amount', 'daily_income', 'total_income_generated', 'estimated_total_income')}),
            ('Duration & Progress', {'fields': ('duration_days', 'days_completed', 'days_remaining', 'status')}),
            ('Dates',               {'fields': ('start_date', 'end_date', 'next_settlement_date')}),
        )

    def total_amount_display(self, obj):
        return format_html('UGX {}', ugx(obj.total_amount))
    total_amount_display.short_description = 'Total Amount'

    def daily_income_display(self, obj):
        return format_html(
            '<span style="color:#4caf50;">UGX {}</span>', ugx(obj.daily_income)
        )
    daily_income_display.short_description = 'Daily Income'

    def status_badge(self, obj):
        colors = {'normal': '#4caf50', 'finish': '#2196f3', 'cancelled': '#f44336'}
        color  = colors.get(obj.status, '#9e9e9e')
        return format_html(
            '<span style="background-color:{}; color:white; '
            'padding:3px 10px; border-radius:12px;">{}</span>',
            color, obj.status.title()
        )
    status_badge.short_description = 'Status'

    def progress_bar(self, obj):
        if not obj or not obj.pk or not obj.duration_days:
            return '-'
        pct     = (obj.days_completed / obj.duration_days) * 100
        pct_str = f"{pct:.0f}"
        return format_html(
            '<div style="width:100px; background:#e0e0e0; border-radius:10px; overflow:hidden;">'
            '<div style="width:{}%; background:#4caf50; height:20px; text-align:center; '
            'color:white; font-size:11px; line-height:20px;">{}%</div></div>',
            pct_str, pct_str
        )
    progress_bar.short_description = 'Progress'

    def progress_display(self, obj):
        if not obj or not obj.pk or not obj.duration_days:
            return 'N/A'
        pct = (obj.days_completed / obj.duration_days) * 100
        return format_html(
            'Days Completed: <strong>{} / {}</strong><br>'
            'Days Remaining: <strong>{}</strong><br>'
            'Progress: <strong>{}%</strong>',
            obj.days_completed or 0, obj.duration_days,
            obj.days_remaining or 0, f"{pct:.2f}"
        )
    progress_display.short_description = 'Progress Details'

    def complete_orders(self, request, queryset):
        from django.utils import timezone
        for order in queryset.filter(status='normal'):
            order.status         = 'finish'
            order.completed_date = timezone.now()
            order.days_remaining = 0
            order.save()
        self.message_user(request, f'{queryset.count()} orders completed.')
    complete_orders.short_description = 'Complete selected orders'

    def cancel_orders(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} orders cancelled.')
    cancel_orders.short_description = 'Cancel selected orders'


# ==================== SETTLEMENT ADMIN ====================

class SettlementInline(admin.TabularInline):
    model           = Settlement
    extra           = 0
    readonly_fields = ['settlement_date', 'amount', 'day_number', 'is_paid', 'paid_at']
    can_delete      = False

    def has_add_permission(self, request, obj=None):
        return False


OrderAdmin.inlines = [SettlementInline]


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):

    list_display  = [
        'order_display', 'user', 'day_number', 'settlement_date',
        'amount_display', 'payment_status', 'paid_at'
    ]
    list_filter   = ['is_paid', 'settlement_date', 'credited_to']
    search_fields = ['order__order_number', 'user__username']
    readonly_fields = ['created_at', 'paid_at']
    date_hierarchy  = 'settlement_date'

    fieldsets = (
        ('Settlement Information', {'fields': ('order', 'user', 'day_number', 'settlement_date')}),
        ('Payment Details',        {'fields': ('amount', 'is_paid', 'paid_at', 'credited_to')}),
    )

    actions = ['process_settlements']

    def order_display(self, obj):
        url = reverse('admin:users_order_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_display.short_description = 'Order'

    def amount_display(self, obj):
        return format_html(
            '<span style="color:#4caf50; font-weight:bold;">UGX {}</span>',
            ugx(obj.amount)
        )
    amount_display.short_description = 'Amount'

    def payment_status(self, obj):
        if obj.is_paid:
            return format_html('<span style="color:#4caf50;">✓ Paid</span>')
        return format_html('<span style="color:#ff9800;">⏳ Pending</span>')
    payment_status.short_description = 'Status'

    def process_settlements(self, request, queryset):
        from django.utils import timezone
        processed = 0
        for settlement in queryset.filter(is_paid=False):
            try:
                profile = settlement.user.profile
                profile.withdrawal_balance    += settlement.amount
                profile.total_earnings        += settlement.amount
                profile.save(update_fields=['withdrawal_balance', 'total_earnings'])

                settlement.order.days_completed         += 1
                settlement.order.total_income_generated += settlement.amount
                settlement.order.save()

                settlement.is_paid = True
                settlement.paid_at = timezone.now()
                settlement.save()
                processed += 1
            except Exception as e:
                self.message_user(request, f"Error on settlement {settlement.id}: {e}", level='error')
        self.message_user(request, f'{processed} settlements processed.')
    process_settlements.short_description = 'Process selected settlements'


# ==================== TRANSACTION ADMIN ====================

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):

    list_display  = [
        'transaction_number', 'user', 'transaction_type_badge',
        'amount_display', 'balance_type', 'status', 'created_at'
    ]
    list_filter   = ['transaction_type', 'balance_type', 'status', 'created_at']
    search_fields = ['transaction_number', 'user__username', 'description', 'reference_id']
    readonly_fields = ['transaction_number', 'created_at']
    date_hierarchy  = 'created_at'

    fieldsets = (
        ('Transaction Information', {
            'fields': ('transaction_number', 'user', 'transaction_type', 'amount', 'status')
        }),
        ('Balance Details', {
            'fields': ('balance_type', 'balance_before', 'balance_after')
        }),
        ('Additional Information', {
            'fields': ('description', 'reference_id'),
            'classes': ('collapse',)
        }),
    )

    def transaction_type_badge(self, obj):
        icons = {
            'recharge': '💰', 'withdrawal': '💸', 'buy_product': '🛒',
            'settlement': '📈', 'promotion_commission': '🎁',
            'system_deduction': '⚠️', 'referral_bonus': '🤝', 'vip_reward': '👑',
        }
        icon = icons.get(obj.transaction_type, '💳')
        return format_html('{} {}', icon, obj.get_transaction_type_display())
    transaction_type_badge.short_description = 'Type'

    def amount_display(self, obj):
        color = '#4caf50' if obj.amount >= 0 else '#f44336'
        sign  = '+' if obj.amount >= 0 else ''
        return format_html(
            '<span style="color:{}; font-weight:bold;">{}UGX {}</span>',
            color, sign, ugx(obj.amount)
        )
    amount_display.short_description = 'Amount'


# ==================== RECHARGE ADMIN ====================

@admin.register(Recharge)
class RechargeAdmin(admin.ModelAdmin):

    list_display  = [
        'recharge_number', 'user', 'amount_display', 'payment_method_badge',
        'status_badge', 'created_at', 'action_buttons'
    ]
    list_filter   = ['status', 'payment_method', 'created_at']
    search_fields = ['recharge_number', 'user__username', 'user_payment_account', 'merchant_account']
    readonly_fields = ['recharge_number', 'created_at', 'expires_at', 'completed_at', 'processed_by']
    date_hierarchy  = 'created_at'

    fieldsets = (
        ('Recharge Information', {
            'fields': ('recharge_number', 'user', 'amount', 'payment_method', 'status')
        }),
        ('Payment Details', {
            'fields': (
                'user_payment_account', 'merchant_account', 'merchant_name',
                'external_transaction_id', 'payment_screenshot'
            )
        }),
        ('Processing', {
            'fields': ('processed_by', 'admin_notes', 'created_at', 'expires_at', 'completed_at')
        }),
    )

    actions = ['approve_recharges', 'reject_recharges']

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            if not obj.recharge_number:
                import uuid
                obj.recharge_number = f"RCH{uuid.uuid4().hex[:12].upper()}"
            if not obj.expires_at:
                from django.utils import timezone
                from datetime import timedelta
                obj.expires_at = timezone.now() + timedelta(minutes=15)
        super().save_model(request, obj, form, change)

    def amount_display(self, obj):
        return format_html(
            '<span style="color:#4caf50; font-weight:bold;">UGX {}</span>',
            ugx(obj.amount)
        )
    amount_display.short_description = 'Amount'

    def payment_method_badge(self, obj):
        icons = {'MTN': '📱', 'Airtel': '📱', 'USDT': '₮'}
        return format_html('{} {}', icons.get(obj.payment_method, '💳'), obj.payment_method)
    payment_method_badge.short_description = 'Payment Method'

    def status_badge(self, obj):
        colors = {
            'pending': '#ff9800', 'processing': '#2196f3', 'completed': '#4caf50',
            'failed': '#f44336',  'cancelled': '#9e9e9e',
        }
        color = colors.get(obj.status, '#9e9e9e')
        return format_html(
            '<span style="background-color:{}; color:white; padding:3px 10px; border-radius:12px;">{}</span>',
            color, obj.status.title()
        )
    status_badge.short_description = 'Status'

    def action_buttons(self, obj):
        if obj.status == 'pending':
            return format_html(
                '<a class="button" href="/admin/users/recharge/{}/approve/">Approve</a> '
                '<a class="button" href="/admin/users/recharge/{}/reject/">Reject</a>',
                obj.id, obj.id
            )
        return '-'
    action_buttons.short_description = 'Actions'

    def approve_recharges(self, request, queryset):
        from django.utils import timezone
        approved = 0
        for recharge in queryset.filter(status='pending'):
            profile = recharge.user.profile
            profile.recharge_balance += recharge.amount
            profile.total_recharged  += recharge.amount
            profile.save()

            Transaction.objects.create(
                user=recharge.user,
                transaction_number=f"TXN{recharge.recharge_number}",
                transaction_type='recharge',
                amount=recharge.amount,
                balance_type='recharge_balance',
                balance_before=profile.recharge_balance - recharge.amount,
                balance_after=profile.recharge_balance,
                description=f'Recharge via {recharge.payment_method}',
                reference_id=recharge.recharge_number,
                status='completed'
            )

            recharge.status       = 'completed'
            recharge.completed_at = timezone.now()
            recharge.processed_by = request.user
            recharge.save()
            approved += 1

        self.message_user(request, f'{approved} recharges approved.')
    approve_recharges.short_description = 'Approve selected recharges'

    def reject_recharges(self, request, queryset):
        from django.utils import timezone
        rejected = 0
        for recharge in queryset.filter(status='pending'):
            recharge.status       = 'failed'
            recharge.processed_by = request.user
            recharge.save()
            rejected += 1
        self.message_user(request, f'{rejected} recharges rejected.')
    reject_recharges.short_description = 'Reject selected recharges'


# ==================== WITHDRAWAL ADMIN ====================

@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):

    list_display  = [
        'withdrawal_number', 'user', 'amount_display', 'net_amount_display',
        'destination_display', 'status_badge', 'created_at', 'action_buttons'
    ]
    list_filter   = ['status', 'destination_wallet_type', 'created_at']
    search_fields = ['withdrawal_number', 'user__username', 'destination_account', 'destination_name']
    readonly_fields = [
        'withdrawal_number', 'withdrawal_fee', 'net_amount',
        'created_at', 'processed_at', 'processed_by'
    ]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Withdrawal Information', {
            'fields': ('withdrawal_number', 'user', 'wallet', 'amount', 'status')
        }),
        ('Fee Calculation', {
            'fields': ('withdrawal_fee_rate', 'withdrawal_fee', 'net_amount')
        }),
        ('Destination Details', {
            'fields': ('destination_wallet_type', 'destination_account', 'destination_name')
        }),
        ('Processing', {
            'fields': ('processed_by', 'processed_at', 'rejection_reason', 'admin_notes')
        }),
    )

    actions = ['approve_withdrawals', 'reject_withdrawals']

    def amount_display(self, obj):
        return format_html(
            '<span style="color:#f44336; font-weight:bold;">UGX {}</span>',
            ugx(obj.amount)
        )
    amount_display.short_description = 'Amount'

    def net_amount_display(self, obj):
        return format_html(
            '<span style="color:#4caf50; font-weight:bold;">UGX {}</span>',
            ugx(obj.net_amount)
        )
    net_amount_display.short_description = 'Net Amount'

    def destination_display(self, obj):
        return format_html(
            '{}<br><small>{}</small>',
            obj.destination_account, obj.destination_wallet_type
        )
    destination_display.short_description = 'Destination'

    def status_badge(self, obj):
        colors = {
            'pending': '#ff9800', 'processing': '#2196f3', 'completed': '#4caf50',
            'rejected': '#f44336', 'cancelled': '#9e9e9e',
        }
        color = colors.get(obj.status, '#9e9e9e')
        return format_html(
            '<span style="background-color:{}; color:white; padding:3px 10px; border-radius:12px;">{}</span>',
            color, obj.status.title()
        )
    status_badge.short_description = 'Status'

    def action_buttons(self, obj):
        if obj.status == 'pending':
            return format_html(
                '<a class="button" href="/admin/users/withdrawal/{}/approve/">Approve</a> '
                '<a class="button" href="/admin/users/withdrawal/{}/reject/">Reject</a>',
                obj.id, obj.id
            )
        return '-'
    action_buttons.short_description = 'Actions'

    def approve_withdrawals(self, request, queryset):
        from django.utils import timezone
        approved = 0
        for withdrawal in queryset.filter(status='pending'):
            profile = withdrawal.user.profile
            if profile.withdrawal_balance < withdrawal.amount:
                continue

            profile.withdrawal_balance -= withdrawal.amount
            profile.total_withdrawn    += withdrawal.net_amount
            profile.save()

            Transaction.objects.create(
                user=withdrawal.user,
                transaction_type='withdrawal',
                amount=-withdrawal.amount,
                balance_type='withdrawal_balance',
                balance_before=profile.withdrawal_balance + withdrawal.amount,
                balance_after=profile.withdrawal_balance,
                description=f'Withdrawal to {withdrawal.destination_wallet_type} {withdrawal.destination_account}',
                reference_id=withdrawal.withdrawal_number,
                status='completed'
            )

            if withdrawal.withdrawal_fee > 0:
                Transaction.objects.create(
                    user=withdrawal.user,
                    transaction_type='system_deduction',
                    amount=-withdrawal.withdrawal_fee,
                    balance_type='withdrawal_balance',
                    balance_before=profile.withdrawal_balance,
                    balance_after=profile.withdrawal_balance,
                    description=f'Withdrawal fee ({withdrawal.withdrawal_fee_rate}%)',
                    reference_id=withdrawal.withdrawal_number,
                    status='completed'
                )

            withdrawal.status       = 'completed'
            withdrawal.processed_at = timezone.now()
            withdrawal.processed_by = request.user
            withdrawal.save()

            Notification.objects.create(
                user=withdrawal.user,
                title="Withdrawal Approved",
                message=(
                    f"Your withdrawal of UGX {ugx(withdrawal.amount)} has been approved. "
                    f"Net: UGX {ugx(withdrawal.net_amount)}"
                ),
                notification_type='withdrawal_approved'
            )
            approved += 1

        self.message_user(request, f'{approved} withdrawals approved.')
    approve_withdrawals.short_description = 'Approve selected withdrawals'

    def reject_withdrawals(self, request, queryset):
        from django.utils import timezone
        rejected = 0
        for withdrawal in queryset.filter(status='pending'):
            withdrawal.status           = 'rejected'
            withdrawal.processed_at     = timezone.now()
            withdrawal.processed_by     = request.user
            withdrawal.rejection_reason = 'Rejected by admin'
            withdrawal.save()

            Notification.objects.create(
                user=withdrawal.user,
                title="Withdrawal Rejected",
                message=f"Your withdrawal of UGX {ugx(withdrawal.amount)} has been rejected.",
                notification_type='withdrawal_rejected'
            )
            rejected += 1

        self.message_user(request, f'{rejected} withdrawals rejected.')
    reject_withdrawals.short_description = 'Reject selected withdrawals'


# ==================== NOTIFICATION ADMIN ====================

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):

    list_display  = [
        'title', 'user_or_broadcast', 'notification_type_badge',
        'is_important', 'is_read', 'created_at'
    ]
    list_filter   = ['notification_type', 'is_broadcast', 'is_important', 'is_read', 'created_at']
    search_fields = ['title', 'message', 'user__username']
    readonly_fields = ['created_at', 'read_at']
    date_hierarchy  = 'created_at'

    fieldsets = (
        ('Notification Content', {
            'fields': ('title', 'message', 'notification_type', 'image', 'link_url')
        }),
        ('Target',  {'fields': ('user', 'is_broadcast')}),
        ('Status',  {'fields': ('is_important', 'is_read', 'read_at')}),
    )

    actions = ['mark_as_read', 'broadcast_to_all', 'delete_old_notifications']

    def user_or_broadcast(self, obj):
        if obj.is_broadcast or obj.user is None:
            return format_html(
                '<span style="background-color:#2196f3; color:white; '
                'padding:3px 10px; border-radius:12px;">📢 Broadcast</span>'
            )
        return obj.user.username
    user_or_broadcast.short_description = 'Target'

    def notification_type_badge(self, obj):
        icons = {
            'system': '⚙️', 'promotion': '🎉', 'vip_upgrade': '👑',
            'withdrawal_approved': '✅', 'withdrawal_rejected': '❌',
            'recharge_confirmed': '💰', 'settlement': '📈', 'referral': '🤝',
        }
        icon = icons.get(obj.notification_type, '📬')
        return format_html('{} {}', icon, obj.get_notification_type_display())
    notification_type_badge.short_description = 'Type'

    def mark_as_read(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(is_read=True, read_at=timezone.now())
        self.message_user(request, f'{updated} notifications marked as read.')
    mark_as_read.short_description = 'Mark as read'

    def broadcast_to_all(self, request, queryset):
        updated = queryset.update(is_broadcast=True, user=None)
        self.message_user(request, f'{updated} notifications set to broadcast.')
    broadcast_to_all.short_description = 'Convert to broadcast'

    def delete_old_notifications(self, request, queryset):
        from django.utils import timezone
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=30)
        old    = queryset.filter(created_at__lt=cutoff, is_read=True)
        count  = old.count()
        old.delete()
        self.message_user(request, f'{count} old notifications deleted.')
    delete_old_notifications.short_description = 'Delete old (30+ days)'


# ==================== ADMIN SITE CUSTOMIZATION ====================

admin.site.site_header = "Agnicoeagle Investment Platform"
admin.site.site_title  = "Agnicoeagle Admin"
admin.site.index_title = "Dashboard"