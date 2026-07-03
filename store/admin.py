from django.contrib import admin
from django.utils.html import format_html
from .models import InvestmentProduct, UserInvestment, DailyEarningLog


@admin.register(InvestmentProduct)
class InvestmentProductAdmin(admin.ModelAdmin):
    list_display  = ('name', 'category', 'vip_required', 'price',
                     'duration_days', 'daily_earning', 'total_return',
                     'max_shares', 'is_active')
    list_filter   = ('category', 'vip_required', 'is_active')
    list_editable = ('is_active',)
    search_fields = ('name',)

    def preview_image(self, obj):
        if obj.image:
            return format_html('<img src="{}" height="40">', obj.image.url)
        return '-'
    preview_image.short_description = 'Image'


@admin.register(UserInvestment)
class UserInvestmentAdmin(admin.ModelAdmin):
    list_display    = ('user', 'product', 'shares', 'amount_paid',
                       'status', 'total_earned', 'start_date', 'end_date')
    list_filter     = ('status', 'product')
    search_fields   = ('user__phone', 'user__nickname')
    readonly_fields = ('amount_paid', 'start_date', 'end_date', 'created_at')
    date_hierarchy  = 'created_at'


@admin.register(DailyEarningLog)
class DailyEarningLogAdmin(admin.ModelAdmin):
    list_display = ('investment', 'amount', 'date', 'credited_at')
    list_filter  = ('date',)
    date_hierarchy = 'date'