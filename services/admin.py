# services/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import SupportTicket, SupportMessage, SupportMessageImage


class SupportMessageImageInline(admin.TabularInline):
    model   = SupportMessageImage
    extra   = 0
    fields  = ('image', 'image_preview')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:60px;border-radius:6px;">', obj.image.url)
        return '—'
    image_preview.short_description = 'Preview'


class SupportMessageInline(admin.StackedInline):
    model           = SupportMessage
    extra           = 1
    fields          = ('sender_type', 'message', 'is_read', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display  = ('id', 'user', 'status', 'message_count', 'updated_at')
    list_filter   = ('status',)
    search_fields = ('user__username', 'user__email')
    inlines       = [SupportMessageInline]
    actions       = ['mark_resolved']

    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Messages'

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, SupportMessage) and not instance.pk:
                instance.sender_type = 'admin'
                instance.user        = request.user
            instance.save()
        formset.save_m2m()

    def mark_resolved(self, request, queryset):
        queryset.update(status='resolved')
    mark_resolved.short_description = 'Mark selected tickets as resolved'


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display    = ('ticket', 'sender_type', 'short_message', 'image_count', 'is_read', 'created_at')
    list_filter     = ('sender_type', 'is_read')
    search_fields   = ('message', 'ticket__user__username')
    inlines         = [SupportMessageImageInline]

    def short_message(self, obj):
        return obj.message[:60] + '...' if len(obj.message) > 60 else obj.message
    short_message.short_description = 'Message'

    def image_count(self, obj):
        count = obj.images.count()
        return format_html('<span style="color:#667eea;font-weight:bold;">{} 🖼</span>', count) if count else '—'
    image_count.short_description = 'Images'