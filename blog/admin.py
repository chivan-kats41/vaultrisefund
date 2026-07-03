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

Features:
- Bulk approval/rejection actions
- Inline image management
- Rich engagement statistics
- Moderation tools
- Reward payment processing
"""

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
    BlogReward
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


# ==================== BLOG POST ADMIN ====================

@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    """Admin interface for Blog Posts with approval workflow"""
    
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
    
    # Admin Actions
    
    def approve_posts(self, request, queryset):
        """Bulk approve blog posts"""
        approved = 0
        for post in queryset.filter(status='pending'):
            post.approve(approved_by=request.user)
            
            # Send notification
            try:
                Notification.objects.create(
                    user=post.user,
                    title="Blog Post Approved! ✅",
                    message=f"Your blog post has been approved and is now visible to everyone!",
                    notification_type='system',
                    is_important=True
                )
            except:
                pass
            
            approved += 1
        
        self.message_user(request, f'{approved} posts approved.')
    approve_posts.short_description = 'Approve selected posts'
    
    def reject_posts(self, request, queryset):
        """Bulk reject blog posts"""
        rejected = 0
        for post in queryset.filter(status='pending'):
            post.reject(reason="Rejected by admin")
            
            # Send notification
            try:
                Notification.objects.create(
                    user=post.user,
                    title="Blog Post Rejected",
                    message=f"Your blog post did not meet our guidelines and has been rejected.",
                    notification_type='system'
                )
            except:
                pass
            
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
        """Pay rewards for approved posts"""
        paid = 0
        total_amount = Decimal('0.00')
        
        for post in queryset.filter(status='approved', reward_paid=False, reward_amount__gt=0):
            try:
                user = post.user
                profile = user.profile
                amount = post.reward_amount
                
                # Credit balance
                profile.commission_balance += amount
                profile.save(update_fields=['commission_balance'])
                
                # Create transaction
                transaction = Transaction.objects.create(
                    user=user,
                    transaction_number=f"BLOG{post.id}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
                    transaction_type='referral_bonus',
                    amount=amount,
                    balance_type='commission_balance',
                    balance_before=profile.commission_balance - amount,
                    balance_after=profile.commission_balance,
                    description=f"Blog post reward for post #{post.id}",
                    reference_id=str(post.id),
                    status='completed'
                )
                
                # Create or update reward record
                reward, created = BlogReward.objects.get_or_create(
                    blog=post,
                    defaults={
                        'user': user,
                        'amount': amount,
                        'currency': post.reward_currency,
                        'approved_by': request.user
                    }
                )
                reward.mark_as_paid(transaction=transaction)
                
                # Update post
                post.reward_paid = True
                post.reward_paid_at = timezone.now()
                post.save(update_fields=['reward_paid', 'reward_paid_at'])
                
                # Send notification
                try:
                    Notification.objects.create(
                        user=user,
                        title="Blog Reward Received! 💰",
                        message=f"You've received {post.reward_currency} {amount:,.0f} reward for your blog post!",
                        notification_type='referral',
                        is_important=True
                    )
                except:
                    pass
                
                paid += 1
                total_amount += amount
                
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
    pay_rewards.short_description = 'Pay rewards'
    
    def mark_as_approved_and_pay(self, request, queryset):
        """Approve posts and pay rewards in one action"""
        processed = 0
        
        for post in queryset.filter(status='pending'):
            # Set default reward if not set
            if post.reward_amount == 0:
                post.reward_amount = Decimal('5000.00')  # Default reward
            
            # Approve
            post.approve(approved_by=request.user, reward_amount=post.reward_amount)
            processed += 1
        
        # Now pay the rewards
        self.pay_rewards(request, queryset.filter(status='approved', reward_paid=False))
        
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
        """Process pending reward payments"""
        paid = 0
        total_amount = Decimal('0.00')
        
        for reward in queryset.filter(is_paid=False):
            try:
                user = reward.user
                profile = user.profile
                amount = reward.amount
                
                # Credit balance
                profile.commission_balance += amount
                profile.save(update_fields=['commission_balance'])
                
                # Create transaction
                transaction = Transaction.objects.create(
                    user=user,
                    transaction_number=f"BLOG{reward.blog.id}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
                    transaction_type='referral_bonus',
                    amount=amount,
                    balance_type='commission_balance',
                    balance_before=profile.commission_balance - amount,
                    balance_after=profile.commission_balance,
                    description=f"Blog post reward for post #{reward.blog.id}",
                    reference_id=str(reward.blog.id),
                    status='completed'
                )
                
                # Mark as paid
                reward.mark_as_paid(transaction=transaction)
                
                # Update blog post
                reward.blog.reward_paid = True
                reward.blog.reward_paid_at = timezone.now()
                reward.blog.save(update_fields=['reward_paid', 'reward_paid_at'])
                
                # Send notification
                try:
                    Notification.objects.create(
                        user=user,
                        title="Blog Reward Received! 💰",
                        message=f"You've received {reward.currency} {amount:,.0f} reward for your blog post!",
                        notification_type='referral',
                        is_important=True
                    )
                except:
                    pass
                
                paid += 1
                total_amount += amount
                
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

admin.site.site_header = "Agnicoeagle Investment Platform"
admin.site.site_title = "Agnicoeagle Admin"
admin.site.index_title = "Blog Management Dashboard"