"""
Django Admin Configuration for Blog App
File: blog/admin.py

Provides comprehensive admin interface for managing:
- Blog posts with approval workflow
- Multiple images per post
- Comments and moderation
- Likes and views analytics
- Reports and flagged content
- Rewards and payments

CRITICAL FIX (this update):
----------------------------
Editing a BlogPost directly in the change form and setting status to
"Approved" previously just did a plain save — it never called
BlogPost.approve(), so the commission wallet was never credited and no
Notification was ever sent, even though the post showed as "approved" in
the list. BlogPostAdmin.save_model() below now detects a transition into
'approved' or 'rejected' and routes it through post.approve() / post.reject()
instead of a raw save, so the change form now behaves identically to the
API endpoints (blog/views.py: api_blog_admin_approve / api_blog_admin_reject).

The bulk actions (approve_posts, reject_posts, pay_rewards,
mark_as_approved_and_pay) and BlogRewardAdmin.process_payments have also
been rewritten to delegate to BlogPost.approve() / BlogPost.reject() /
BlogPost.credit_reward_and_notify() instead of manually duplicating the
balance-crediting logic — this fixes a broken approve_posts action (it was
missing the now-required reward_amount argument and would have raised a
TypeError), removes duplicate notifications, and makes it impossible to
double-credit the same post's reward twice (credit_reward_and_notify() is
idempotent, guarded by reward_paid).

Features:
- Bulk approval/rejection actions
- Inline image management
- Rich engagement statistics
- Moderation tools
- Reward payment processing
"""

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Sum, Q, Avg
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from decimal import Decimal

from .models import (
    BlogPost,
    BlogImage,
    BlogComment,
    BlogLike,
    BlogView,
    BlogReport,
    BlogReward,
    MIN_REWARD_AMOUNT,
    MAX_REWARD_AMOUNT,
)
from users.models import Transaction, Notification


# ==================== INLINE ADMINS ====================

class BlogImageInline(admin.TabularInline):
    """Inline for managing blog post images"""
    model = BlogImage
    extra = 1
    max_num = 9
    fields = ['image', 'caption', 'order', 'image_preview', 'file_size_display']
    readonly_fields = ['image_preview', 'file_size_display']
    
    def image_preview(self, obj):
        """Show small image preview"""
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 100px; max-height: 100px; '
                'border-radius: 5px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = 'Preview'
    
    def file_size_display(self, obj):
        """Display file size in human-readable format"""
        if obj.file_size:
            size_kb = obj.file_size / 1024
            if size_kb > 1024:
                return f"{size_kb / 1024:.2f} MB"
            return f"{size_kb:.2f} KB"
        return "N/A"
    file_size_display.short_description = 'File Size'


class BlogCommentInline(admin.TabularInline):
    """Inline for viewing recent comments on a post"""
    model = BlogComment
    extra = 0
    max_num = 5
    fields = ['user', 'content_preview', 'like_count', 'is_flagged', 'created_at']
    readonly_fields = ['user', 'content_preview', 'like_count', 'created_at']
    can_delete = True
    
    def content_preview(self, obj):
        """Show comment preview"""
        preview = obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
        return preview
    content_preview.short_description = 'Comment'
    
    def has_add_permission(self, request, obj=None):
        return False


# ==================== BLOG POST ADMIN FORM ====================

class BlogPostAdminForm(forms.ModelForm):
    """
    Validates the reward_amount range at the form level whenever an admin
    sets status to 'approved', so they get a clear inline error immediately
    instead of a generic failure after clicking Save.
    """

    class Meta:
        model = BlogPost
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        reward_amount = cleaned_data.get('reward_amount')

        if status == 'approved':
            if reward_amount is None or reward_amount <= 0:
                raise forms.ValidationError(
                    'A reward_amount is required to approve a post.'
                )
            if reward_amount < MIN_REWARD_AMOUNT or reward_amount > MAX_REWARD_AMOUNT:
                raise forms.ValidationError(
                    f'Reward amount must be between UGX {MIN_REWARD_AMOUNT:,.0f} '
                    f'and UGX {MAX_REWARD_AMOUNT:,.0f}.'
                )

        return cleaned_data


# ==================== BLOG POST ADMIN ====================

@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    """Admin interface for Blog Posts with approval workflow"""

    form = BlogPostAdminForm
    
    list_display = [
        'id',
        'user_display',
        'content_preview',
        'image_count_display',
        'status_badge',
        'engagement_display',
        'reward_display',
        'created_at',
        'action_buttons'
    ]
    
    list_filter = [
        'status',
        'is_featured',
        'is_pinned',
        'reward_paid',
        'created_at',
        'published_at'
    ]
    
    search_fields = [
        'user__username',
        'user__email',
        'content',
        'slug'
    ]
    
    readonly_fields = [
        'user',
        'created_at',
        'updated_at',
        'published_at',
        'approved_by',
        'approved_at',
        'rejected_at',
        'engagement_stats_display',
        'images_display',
        'reward_paid',
        'reward_paid_at'
    ]
    
    date_hierarchy = 'created_at'
    
    list_per_page = 25
    
    fieldsets = (
        ('Post Information', {
            'fields': (
                'user',
                'content',
                'slug',
                'meta_description'
            )
        }),
        ('Status & Visibility', {
            'fields': (
                'status',
                'is_featured',
                'is_pinned'
            )
        }),
        ('Approval Details', {
            'fields': (
                'approved_by',
                'approved_at',
                'rejection_reason',
                'rejected_at'
            ),
            'classes': ('collapse',)
        }),
        ('Reward Information', {
            'fields': (
                'reward_amount',
                'reward_currency',
                'reward_paid',
                'reward_paid_at'
            ),
            'description': (
                'Set reward_amount (UGX 100 - 500,000) BEFORE changing status '
                'to "Approved" and saving. Saving with status=Approved will '
                'automatically credit this amount to the user\'s commission '
                'wallet and send them a notification — you do not need any '
                'separate "pay reward" step.'
            )
        }),
        ('Engagement Metrics', {
            'fields': (
                'view_count',
                'like_count',
                'comment_count',
                'share_count',
                'engagement_stats_display'
            ),
            'classes': ('collapse',)
        }),
        ('Images', {
            'fields': ('images_display',),
            'classes': ('collapse',)
        }),
        ('Admin Notes', {
            'fields': ('admin_notes',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
                'published_at'
            ),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [BlogImageInline, BlogCommentInline]
    
    actions = [
        'approve_posts',
        'reject_posts',
        'feature_posts',
        'unfeature_posts',
        'pin_posts',
        'unpin_posts',
        'pay_rewards',
        'mark_as_approved_and_pay'
    ]

    # ---------------------------------------------------------------
    # THE ACTUAL FIX: route change-form saves through approve()/reject()
    # ---------------------------------------------------------------
    def save_model(self, request, obj, form, change):
        """
        Detects a status transition into 'approved' or 'rejected' on a
        normal change-form save and routes it through BlogPost.approve()
        / BlogPost.reject() instead of a raw save, so the commission
        wallet credit + Transaction + Notification always fire — exactly
        like the api_blog_admin_approve / api_blog_admin_reject endpoints.

        Editing any other field (content, admin_notes, is_featured, etc.)
        without changing status behaves like a completely normal save.

        approve() is safe to call even if invoked more than once on the
        same post, since credit_reward_and_notify() is guarded by
        reward_paid and will not credit twice.
        """
        old_status = None
        if change and obj.pk:
            old_status = BlogPost.objects.filter(pk=obj.pk).values_list(
                'status', flat=True
            ).first()

        transitioning_to_approved = obj.status == 'approved' and old_status != 'approved'
        transitioning_to_rejected = obj.status == 'rejected' and old_status != 'rejected'

        if transitioning_to_approved:
            reward_amount = obj.reward_amount
            # Persist every other edited field first (content, notes, etc.)
            super().save_model(request, obj, form, change)
            try:
                obj.approve(approved_by=request.user, reward_amount=reward_amount)
                self.message_user(
                    request,
                    f"Post #{obj.id} approved — UGX {reward_amount:,.2f} "
                    f"credited to {obj.user.username}'s commission wallet."
                )
            except ValueError as e:
                # Range check failed (belt-and-braces on top of the form's
                # own validation). Post stays saved with its other field
                # edits, but not actually approved.
                self.message_user(request, str(e), level='error')
            return

        if transitioning_to_rejected:
            super().save_model(request, obj, form, change)
            obj.reject(reason=obj.rejection_reason)
            self.message_user(request, f"Post #{obj.id} rejected and user notified.")
            return

        # No status transition — ordinary save.
        super().save_model(request, obj, form, change)
    
    def user_display(self, obj):
        """Display username with link to user"""
        try:
            url = reverse('admin:auth_user_change', args=[obj.user.id])
            vip = obj.user.profile.vip_level
            return format_html(
                '<a href="{}">{}</a> <small>(VIP {})</small>',
                url, obj.user.username, vip
            )
        except:
            return obj.user.username
    user_display.short_description = 'User'
    
    def content_preview(self, obj):
        """Display content preview"""
        preview = obj.content[:60] + '...' if len(obj.content) > 60 else obj.content
        return format_html(
            '<div style="max-width: 300px; white-space: pre-wrap;">{}</div>',
            preview
        )
    content_preview.short_description = 'Content'
    
    def image_count_display(self, obj):
        """Display number of images"""
        count = obj.image_count
        if count > 0:
            return format_html(
                '<span style="background: #4caf50; color: white; '
                'padding: 3px 8px; border-radius: 10px; font-size: 11px;">'
                '📷 {}</span>',
                count
            )
        return format_html(
            '<span style="color: #999;">No images</span>'
        )
    image_count_display.short_description = 'Images'
    
    def status_badge(self, obj):
        """Display status with colored badge"""
        colors = {
            'pending': '#ff9800',
            'approved': '#4caf50',
            'rejected': '#f44336',
            'archived': '#9e9e9e',
        }
        icons = {
            'pending': '⏳',
            'approved': '✓',
            'rejected': '✗',
            'archived': '📦',
        }
        
        color = colors.get(obj.status, '#9e9e9e')
        icon = icons.get(obj.status, '○')
        
        badge = format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 5px 12px; border-radius: 15px; font-weight: bold; '
            'font-size: 12px;">{} {}</span>',
            color, icon, obj.status.title()
        )
        
        # Add featured/pinned indicators
        extras = []
        if obj.is_featured:
            extras.append('<span style="color: #ffd700;">⭐</span>')
        if obj.is_pinned:
            extras.append('<span style="color: #2196f3;">📌</span>')
        
        if extras:
            badge = format_html('{} {}', badge, ' '.join(extras))
        
        return badge
    status_badge.short_description = 'Status'
    
    def engagement_display(self, obj):
        """Display engagement metrics"""
        return format_html(
            '<div style="font-size: 11px;">'
            '👁️ {} | 👍 {} | 💬 {} | 📤 {}'
            '</div>',
            obj.view_count,
            obj.like_count,
            obj.comment_count,
            obj.share_count
        )
    engagement_display.short_description = 'Engagement'
    
    def reward_display(self, obj):
        """Display reward information"""
        if obj.reward_amount > 0:
            # Convert Decimal to float and format as string first
            amount = float(obj.reward_amount)
            formatted_amount = f'{amount:,.0f}'
            
            if obj.reward_paid:
                return format_html(
                    '<span style="background: #4caf50; color: white; '
                    'padding: 4px 10px; border-radius: 12px; font-size: 11px;">'
                    '💰 {} {} ✓</span>',
                    obj.reward_currency, 
                    formatted_amount
                )
            else:
                return format_html(
                    '<span style="background: #ff9800; color: white; '
                    'padding: 4px 10px; border-radius: 12px; font-size: 11px;">'
                    '💰 {} {} ⏳</span>',
                    obj.reward_currency, 
                    formatted_amount
                )
        return format_html('<span style="color: #999;">No reward</span>')
    reward_display.short_description = 'Reward'
    
    def engagement_stats_display(self, obj):
        """Display detailed engagement statistics"""
        if not obj or not obj.pk:
            return "Save to view stats"
        
        score = obj.engagement_score
        
        html = '<div style="font-family: monospace;">'
        html += f'<strong>Engagement Score:</strong> {score}<br><br>'
        html += f'<strong>Views:</strong> {obj.view_count}<br>'
        html += f'<strong>Likes:</strong> {obj.like_count}<br>'
        html += f'<strong>Comments:</strong> {obj.comment_count}<br>'
        html += f'<strong>Shares:</strong> {obj.share_count}<br>'
        html += '</div>'
        
        return format_html(html)
    engagement_stats_display.short_description = 'Engagement Statistics'
    
    def images_display(self, obj):
        """Display all images in a grid"""
        if not obj or not obj.pk:
            return "Save to view images"
        
        images = obj.images.all()
        
        if not images:
            return "No images"
        
        html = '<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;">'
        
        for img in images:
            html += f'''
                <div style="position: relative;">
                    <img src="{img.image.url}" 
                         style="width: 100%; height: 150px; object-fit: cover; border-radius: 8px;" />
                    <div style="font-size: 10px; margin-top: 5px;">
                        {img.file_size / 1024:.1f} KB
                    </div>
                </div>
            '''
        
        html += '</div>'
        
        return format_html(html)
    images_display.short_description = 'Post Images'
    
    def action_buttons(self, obj):
        """Display quick action buttons"""
        if obj.status == 'pending':
            return format_html(
                '<a class="button" style="background: #4caf50; color: white; '
                'padding: 5px 10px; border-radius: 5px; text-decoration: none;" '
                'href="#" onclick="return confirm(\'Approve this post?\');">Approve</a> '
                '<a class="button" style="background: #f44336; color: white; '
                'padding: 5px 10px; border-radius: 5px; text-decoration: none;" '
                'href="#" onclick="return confirm(\'Reject this post?\');">Reject</a>'
            )
        return '-'
    action_buttons.short_description = 'Quick Actions'
    
    # ==================== ADMIN ACTIONS ====================
    
    def approve_posts(self, request, queryset):
        """
        Bulk approve blog posts. Each post must already have a valid
        reward_amount set (UGX 100 - 500,000) — since a bulk action has no
        per-post input field, there's no way to ask for one here. Set
        reward_amount on each post first (e.g. via the list view's editable
        column, or open each post and set it) before running this action.

        Delegates entirely to BlogPost.approve(), so the commission wallet
        credit, Transaction, and Notification all fire exactly as they
        would through the API or a single change-form save. No separate
        notification is created here — approve() already sends one.
        """
        approved = 0
        skipped = 0
        for post in queryset.filter(status='pending'):
            if not post.reward_amount or post.reward_amount <= 0:
                skipped += 1
                continue
            try:
                post.approve(approved_by=request.user, reward_amount=post.reward_amount)
                approved += 1
            except ValueError:
                skipped += 1

        msg = f'{approved} posts approved.'
        if skipped:
            msg += (
                f' {skipped} skipped — set a valid reward_amount '
                f'(UGX {MIN_REWARD_AMOUNT:,.0f} - {MAX_REWARD_AMOUNT:,.0f}) '
                f'on each post first.'
            )
        self.message_user(request, msg)
    approve_posts.short_description = 'Approve selected posts (reward_amount must already be set)'
    
    def reject_posts(self, request, queryset):
        """
        Bulk reject blog posts. Delegates to BlogPost.reject(), which
        already creates the "your post was rejected" Notification — no
        duplicate notification is created here.
        """
        rejected = 0
        for post in queryset.filter(status='pending'):
            post.reject(reason="Rejected by admin")
            rejected += 1
        
        self.message_user(request, f'{rejected} posts rejected.')
    reject_posts.short_description = 'Reject selected posts'
    
    def feature_posts(self, request, queryset):
        """Mark posts as featured"""
        updated = queryset.update(is_featured=True)
        self.message_user(request, f'{updated} posts marked as featured.')
    feature_posts.short_description = 'Mark as featured'
    
    def unfeature_posts(self, request, queryset):
        """Remove featured status"""
        updated = queryset.update(is_featured=False)
        self.message_user(request, f'{updated} posts unfeatured.')
    unfeature_posts.short_description = 'Remove featured status'
    
    def pin_posts(self, request, queryset):
        """Pin posts to top"""
        updated = queryset.update(is_pinned=True)
        self.message_user(request, f'{updated} posts pinned.')
    pin_posts.short_description = 'Pin to top'
    
    def unpin_posts(self, request, queryset):
        """Unpin posts"""
        updated = queryset.update(is_pinned=False)
        self.message_user(request, f'{updated} posts unpinned.')
    unpin_posts.short_description = 'Unpin posts'
    
    def pay_rewards(self, request, queryset):
        """
        Pay out rewards for posts that are approved but not yet paid —
        mainly a catch-up tool for posts approved before this crediting
        system existed. Delegates to BlogPost.credit_reward_and_notify(),
        which is idempotent (guarded by reward_paid), so this can never
        double-credit a post that approve() already paid out.
        """
        paid = 0
        total_amount = Decimal('0.00')
        
        for post in queryset.filter(status='approved', reward_paid=False, reward_amount__gt=0):
            try:
                transaction = post.credit_reward_and_notify(post.reward_amount)
                if transaction is not None:
                    paid += 1
                    total_amount += post.reward_amount
            except Exception as e:
                self.message_user(
                    request,
                    f'Error processing reward for post {post.id}: {e}',
                    level='error'
                )
                continue
        
        self.message_user(
            request,
            f'{paid} rewards paid totaling {total_amount:,.2f}'
        )
    pay_rewards.short_description = 'Pay rewards (for posts approved but not yet credited)'
    
    def mark_as_approved_and_pay(self, request, queryset):
        """
        Approve posts (setting a default reward if none is set) and pay
        rewards in one action. Approving already credits the wallet, so
        there is no separate "pay" step needed afterward.
        """
        processed = 0
        
        for post in queryset.filter(status='pending'):
            # Set default reward if not set
            if post.reward_amount == 0:
                post.reward_amount = Decimal('5000.00')
                post.save(update_fields=['reward_amount'])
            
            try:
                post.approve(approved_by=request.user, reward_amount=post.reward_amount)
                processed += 1
            except ValueError as e:
                self.message_user(request, f'Post {post.id}: {e}', level='error')
        
        self.message_user(request, f'{processed} posts approved and rewards paid.')
    mark_as_approved_and_pay.short_description = 'Approve & pay rewards'


# ==================== BLOG IMAGE ADMIN ====================

@admin.register(BlogImage)
class BlogImageAdmin(admin.ModelAdmin):
    """Admin interface for Blog Images"""
    
    list_display = [
        'id',
        'blog_link',
        'image_preview',
        'order',
        'file_size_display',
        'dimensions_display',
        'uploaded_at'
    ]
    
    list_filter = ['uploaded_at']
    
    search_fields = [
        'blog__user__username',
        'caption'
    ]
    
    readonly_fields = [
        'blog',
        'image_preview_large',
        'file_size',
        'width',
        'height',
        'uploaded_at'
    ]
    
    fieldsets = (
        ('Image Information', {
            'fields': ('blog', 'image', 'caption', 'order')
        }),
        ('Preview', {
            'fields': ('image_preview_large',)
        }),
        ('Metadata', {
            'fields': ('file_size', 'width', 'height', 'uploaded_at'),
            'classes': ('collapse',)
        }),
    )
    
    def blog_link(self, obj):
        """Link to blog post"""
        url = reverse('admin:blog_blogpost_change', args=[obj.blog.id])
        return format_html('<a href="{}">Post #{}</a>', url, obj.blog.id)
    blog_link.short_description = 'Blog Post'
    
    def image_preview(self, obj):
        """Small preview"""
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 80px; max-height: 80px; '
                'border-radius: 5px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = 'Preview'
    
    def image_preview_large(self, obj):
        """Large preview"""
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 500px; border-radius: 10px;" />',
                obj.image.url
            )
        return "No image"
    image_preview_large.short_description = 'Image Preview'
    
    def file_size_display(self, obj):
        """Human-readable file size"""
        if obj.file_size:
            size_kb = obj.file_size / 1024
            if size_kb > 1024:
                return f"{size_kb / 1024:.2f} MB"
            return f"{size_kb:.2f} KB"
        return "N/A"
    file_size_display.short_description = 'File Size'
    
    def dimensions_display(self, obj):
        """Display image dimensions"""
        if obj.width and obj.height:
            return f"{obj.width} × {obj.height} px"
        return "N/A"
    dimensions_display.short_description = 'Dimensions'


# ==================== BLOG COMMENT ADMIN ====================

@admin.register(BlogComment)
class BlogCommentAdmin(admin.ModelAdmin):
    """Admin interface for Blog Comments"""
    
    list_display = [
        'id',
        'user',
        'blog_link',
        'content_preview',
        'like_count',
        'is_reply_badge',
        'flagged_badge',
        'created_at'
    ]
    
    list_filter = [
        'is_flagged',
        'is_deleted',
        'created_at'
    ]
    
    search_fields = [
        'user__username',
        'content',
        'blog__user__username'
    ]
    
    readonly_fields = [
        'user',
        'blog',
        'parent',
        'created_at',
        'updated_at',
        'reply_count_display'
    ]
    
    fieldsets = (
        ('Comment Information', {
            'fields': ('user', 'blog', 'parent', 'content')
        }),
        ('Engagement', {
            'fields': ('like_count', 'reply_count_display')
        }),
        ('Moderation', {
            'fields': ('is_deleted', 'is_flagged')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['flag_comments', 'unflag_comments', 'delete_comments']
    
    def blog_link(self, obj):
        """Link to blog post"""
        url = reverse('admin:blog_blogpost_change', args=[obj.blog.id])
        return format_html('<a href="{}">Post #{}</a>', url, obj.blog.id)
    blog_link.short_description = 'Blog Post'
    
    def content_preview(self, obj):
        """Comment preview"""
        preview = obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
        return preview
    content_preview.short_description = 'Comment'
    
    def is_reply_badge(self, obj):
        """Show if comment is a reply"""
        if obj.is_reply:
            return format_html(
                '<span style="background: #2196f3; color: white; '
                'padding: 3px 8px; border-radius: 10px; font-size: 11px;">↩️ Reply</span>'
            )
        return format_html('<span style="color: #999;">Comment</span>')
    is_reply_badge.short_description = 'Type'
    
    def flagged_badge(self, obj):
        """Show flagged status"""
        if obj.is_flagged:
            return format_html(
                '<span style="background: #f44336; color: white; '
                'padding: 3px 8px; border-radius: 10px; font-size: 11px;">🚩 Flagged</span>'
            )
        return format_html('<span style="color: #4caf50;">✓ OK</span>')
    flagged_badge.short_description = 'Status'
    
    def reply_count_display(self, obj):
        """Display number of replies"""
        if not obj or not obj.pk:
            return "N/A"
        return obj.reply_count
    reply_count_display.short_description = 'Replies'
    
    def flag_comments(self, request, queryset):
        """Flag comments for review"""
        updated = queryset.update(is_flagged=True)
        self.message_user(request, f'{updated} comments flagged.')
    flag_comments.short_description = 'Flag for review'
    
    def unflag_comments(self, request, queryset):
        """Unflag comments"""
        updated = queryset.update(is_flagged=False)
        self.message_user(request, f'{updated} comments unflagged.')
    unflag_comments.short_description = 'Unflag comments'
    
    def delete_comments(self, request, queryset):
        """Soft delete comments"""
        updated = queryset.update(is_deleted=True)
        self.message_user(request, f'{updated} comments deleted.')
    delete_comments.short_description = 'Delete comments'


# ==================== BLOG REPORT ADMIN ====================

@admin.register(BlogReport)
class BlogReportAdmin(admin.ModelAdmin):
    """Admin interface for Blog Reports"""
    
    list_display = [
        'id',
        'blog_link',
        'reporter',
        'reason_badge',
        'resolved_badge',
        'created_at',
        'action_buttons'
    ]
    
    list_filter = [
        'reason',
        'is_resolved',
        'created_at'
    ]
    
    search_fields = [
        'reporter__username',
        'blog__user__username',
        'description'
    ]
    
    readonly_fields = [
        'blog',
        'reporter',
        'reason',
        'description',
        'created_at',
        'resolved_at'
    ]
    
    fieldsets = (
        ('Report Information', {
            'fields': ('blog', 'reporter', 'reason', 'description', 'created_at')
        }),
        ('Resolution', {
            'fields': ('is_resolved', 'resolved_by', 'resolved_at', 'admin_notes')
        }),
    )
    
    actions = ['mark_as_resolved', 'reject_and_remove_post']
    
    def blog_link(self, obj):
        """Link to reported blog post"""
        url = reverse('admin:blog_blogpost_change', args=[obj.blog.id])
        return format_html('<a href="{}">Post #{}</a>', url, obj.blog.id)
    blog_link.short_description = 'Reported Post'
    
    def reason_badge(self, obj):
        """Display report reason"""
        colors = {
            'spam': '#ff9800',
            'inappropriate': '#f44336',
            'harassment': '#e91e63',
            'fake': '#9c27b0',
            'copyright': '#3f51b5',
            'other': '#607d8b',
        }
        color = colors.get(obj.reason, '#9e9e9e')
        
        return format_html(
            '<span style="background: {}; color: white; '
            'padding: 4px 10px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_reason_display()
        )
    reason_badge.short_description = 'Reason'
    
    def resolved_badge(self, obj):
        """Display resolution status"""
        if obj.is_resolved:
            return format_html(
                '<span style="color: #4caf50; font-weight: bold;">✓ Resolved</span>'
            )
        return format_html(
            '<span style="color: #ff9800; font-weight: bold;">⏳ Pending</span>'
        )
    resolved_badge.short_description = 'Status'
    
    def action_buttons(self, obj):
        """Quick action buttons"""
        if not obj.is_resolved:
            return format_html(
                '<a class="button" style="background: #4caf50; color: white; '
                'padding: 5px 10px; border-radius: 5px; text-decoration: none;" '
                'href="#" onclick="return confirm(\'Mark as resolved?\');">Resolve</a>'
            )
        return '-'
    action_buttons.short_description = 'Actions'
    
    def mark_as_resolved(self, request, queryset):
        """Mark reports as resolved"""
        resolved = 0
        for report in queryset.filter(is_resolved=False):
            report.is_resolved = True
            report.resolved_by = request.user
            report.resolved_at = timezone.now()
            report.save()
            resolved += 1
        
        self.message_user(request, f'{resolved} reports marked as resolved.')
    mark_as_resolved.short_description = 'Mark as resolved'
    
    def reject_and_remove_post(self, request, queryset):
        """Reject the reported blog posts"""
        removed = 0
        for report in queryset:
            blog = report.blog
            if blog.status != 'rejected':
                blog.reject(reason=f"Reported for: {report.get_reason_display()}")
                removed += 1
            
            report.is_resolved = True
            report.resolved_by = request.user
            report.resolved_at = timezone.now()
            report.admin_notes = "Post rejected due to report"
            report.save()
        
        self.message_user(request, f'{removed} reported posts rejected.')
    reject_and_remove_post.short_description = 'Reject reported posts'


# ==================== BLOG REWARD ADMIN ====================

@admin.register(BlogReward)
class BlogRewardAdmin(admin.ModelAdmin):
    """Admin interface for Blog Rewards"""
    
    list_display = [
        'id',
        'blog_link',
        'user',
        'amount_display',
        'payment_status',
        'paid_at',
        'created_at'
    ]
    
    list_filter = [
        'is_paid',
        'currency',
        'created_at',
        'paid_at'
    ]
    
    search_fields = [
        'user__username',
        'blog__id'
    ]
    
    readonly_fields = [
        'blog',
        'user',
        'transaction',
        'approved_by',
        'created_at',
        'paid_at'
    ]
    
    fieldsets = (
        ('Reward Information', {
            'fields': ('blog', 'user', 'amount', 'currency')
        }),
        ('Payment Status', {
            'fields': ('is_paid', 'paid_at', 'transaction')
        }),
        ('Approval Details', {
            'fields': ('approved_by', 'notes', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['process_payments']
    
    def blog_link(self, obj):
        """Link to blog post"""
        url = reverse('admin:blog_blogpost_change', args=[obj.blog.id])
        return format_html('<a href="{}">Post #{}</a>', url, obj.blog.id)
    blog_link.short_description = 'Blog Post'
    
    def amount_display(self, obj):
        """Formatted amount"""
        # Convert Decimal to float and format as string first
        amount = float(obj.amount)
        formatted_amount = f'{amount:,.0f}'
        
        return format_html(
            '<span style="color: #4caf50; font-weight: bold; font-size: 14px;">'
            '{} {}</span>',
            obj.currency, 
            formatted_amount
        )
    amount_display.short_description = 'Amount'
    
    def payment_status(self, obj):
        """Display payment status"""
        if obj.is_paid:
            return format_html(
                '<span style="background: #4caf50; color: white; '
                'padding: 4px 12px; border-radius: 15px; font-size: 11px;">✓ Paid</span>'
            )
        return format_html(
            '<span style="background: #ff9800; color: white; '
            'padding: 4px 12px; border-radius: 15px; font-size: 11px;">⏳ Pending</span>'
        )
    payment_status.short_description = 'Status'
    
    def process_payments(self, request, queryset):
        """
        Process pending BlogReward payments. Delegates the actual crediting
        to BlogPost.credit_reward_and_notify(), which is idempotent — if
        the post's reward was already credited (e.g. via approve() when
        the post was first approved), this just links up the existing
        Transaction to this BlogReward record instead of crediting again.
        """
        paid = 0
        total_amount = Decimal('0.00')
        
        for reward in queryset.filter(is_paid=False):
            try:
                blog = reward.blog
                transaction = blog.credit_reward_and_notify(reward.amount)

                if transaction is None:
                    # Already credited earlier (e.g. via approve()) — find
                    # that existing Transaction to link on this record
                    # instead of crediting the wallet a second time.
                    transaction = Transaction.objects.filter(
                        reference_id=f'BLOG{blog.id}',
                        transaction_type='blog_reward',
                    ).order_by('-created_at').first()

                reward.mark_as_paid(transaction=transaction)
                
                paid += 1
                total_amount += reward.amount
                
            except Exception as e:
                self.message_user(
                    request,
                    f'Error processing reward {reward.id}: {e}',
                    level='error'
                )
                continue
        
        self.message_user(request, f'{paid} rewards paid totaling {total_amount:,.2f}')
    process_payments.short_description = 'Process pending payments'


# ==================== BLOG LIKE ADMIN (Read-Only) ====================

@admin.register(BlogLike)
class BlogLikeAdmin(admin.ModelAdmin):
    """Admin interface for Blog Likes (analytics only)"""
    
    list_display = [
        'id',
        'blog_link',
        'user',
        'created_at'
    ]
    
    list_filter = ['created_at']
    
    search_fields = [
        'user__username',
        'blog__user__username'
    ]
    
    readonly_fields = ['blog', 'user', 'created_at']
    
    def blog_link(self, obj):
        """Link to blog post"""
        url = reverse('admin:blog_blogpost_change', args=[obj.blog.id])
        return format_html('<a href="{}">Post #{}</a>', url, obj.blog.id)
    blog_link.short_description = 'Blog Post'
    
    def has_add_permission(self, request):
        return False


# ==================== BLOG VIEW ADMIN (Read-Only) ====================

@admin.register(BlogView)
class BlogViewAdmin(admin.ModelAdmin):
    """Admin interface for Blog Views (analytics only)"""
    
    list_display = [
        'id',
        'blog_link',
        'viewer',
        'device_badge',
        'ip_address',
        'viewed_at'
    ]
    
    list_filter = [
        'device_type',
        'viewed_at'
    ]
    
    search_fields = [
        'user__username',
        'blog__user__username',
        'ip_address'
    ]
    
    readonly_fields = [
        'blog',
        'user',
        'ip_address',
        'user_agent',
        'device_type',
        'viewed_at'
    ]
    
    date_hierarchy = 'viewed_at'
    
    def blog_link(self, obj):
        """Link to blog post"""
        url = reverse('admin:blog_blogpost_change', args=[obj.blog.id])
        return format_html('<a href="{}">Post #{}</a>', url, obj.blog.id)
    blog_link.short_description = 'Blog Post'
    
    def viewer(self, obj):
        """Display viewer name"""
        return obj.user.username if obj.user else 'Anonymous'
    viewer.short_description = 'Viewer'
    
    def device_badge(self, obj):
        """Display device type with icon"""
        icons = {
            'mobile': '📱',
            'tablet': '📱',
            'desktop': '💻',
            'unknown': '❓'
        }
        return format_html(
            '{} {}',
            icons.get(obj.device_type, '❓'),
            obj.device_type.title()
        )
    device_badge.short_description = 'Device'
    
    def has_add_permission(self, request):
        return False


# ==================== CUSTOM FILTERS ====================

class RewardAmountFilter(admin.SimpleListFilter):
    """Filter blog posts by reward amount range"""
    title = 'Reward Amount'
    parameter_name = 'reward_range'
    
    def lookups(self, request, model_admin):
        return (
            ('0', 'No Reward'),
            ('1-5k', '1,000 - 5,000'),
            ('5k-10k', '5,000 - 10,000'),
            ('10k+', 'Over 10,000'),
        )
    
    def queryset(self, request, queryset):
        if self.value() == '0':
            return queryset.filter(reward_amount=0)
        if self.value() == '1-5k':
            return queryset.filter(
                reward_amount__gte=Decimal('1000'),
                reward_amount__lt=Decimal('5000')
            )
        if self.value() == '5k-10k':
            return queryset.filter(
                reward_amount__gte=Decimal('5000'),
                reward_amount__lt=Decimal('10000')
            )
        if self.value() == '10k+':
            return queryset.filter(reward_amount__gte=Decimal('10000'))


class EngagementFilter(admin.SimpleListFilter):
    """Filter by engagement level"""
    title = 'Engagement Level'
    parameter_name = 'engagement'
    
    def lookups(self, request, model_admin):
        return (
            ('high', 'High (100+ likes)'),
            ('medium', 'Medium (50-100 likes)'),
            ('low', 'Low (< 50 likes)'),
        )
    
    def queryset(self, request, queryset):
        if self.value() == 'high':
            return queryset.filter(like_count__gte=100)
        if self.value() == 'medium':
            return queryset.filter(like_count__gte=50, like_count__lt=100)
        if self.value() == 'low':
            return queryset.filter(like_count__lt=50)


# Add custom filters to BlogPost admin
BlogPostAdmin.list_filter.extend([RewardAmountFilter, EngagementFilter])


# ==================== ADMIN SITE CUSTOMIZATION ====================

admin.site.site_header = "Vaultrise Investment Platform"
admin.site.site_title = "Vaultrise Admin"
admin.site.index_title = "Blog Management Dashboard"