"""
Models for the Blog App - User-Generated Content Platform
File: blog/models.py

This module handles:
- Blog post creation and management
- Multi-image upload support
- Approval workflow (pending/approved/rejected)
- Reward system for approved posts
- Comment system
- Like/reaction system
- User engagement tracking

IMPORTANT: All User model references use settings.AUTH_USER_MODEL
"""

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.utils import timezone
from decimal import Decimal
import uuid
import os


def blog_image_upload_path(instance, filename):
    """
    Generate upload path for blog images.
    Structure: blog_images/user_<id>/YYYY/MM/DD/<uuid>_<filename>
    """
    ext = filename.split('.')[-1]
    new_filename = f"{uuid.uuid4().hex[:12]}_{filename}"
    date = timezone.now()
    return f'blog_images/user_{instance.blog.user.id}/{date.year}/{date.month:02d}/{date.day:02d}/{new_filename}'


class BlogPost(models.Model):
    """
    Main blog post model for user-generated content.
    
    Features:
    - Text content with character limits
    - Multiple image attachments
    - Approval workflow
    - Reward system
    - Engagement metrics
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('archived', 'Archived'),
    ]
    
    # Author Information
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blog_posts',
        help_text="Author of the blog post"
    )
    
    # Content
    content = models.TextField(
        max_length=2000,
        help_text="Blog post content (max 2000 characters)"
    )
    
    # Status & Approval
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
        help_text="Current approval status"
    )
    
    is_featured = models.BooleanField(
        default=False,
        help_text="Featured posts appear at the top"
    )
    
    is_pinned = models.BooleanField(
        default=False,
        help_text="Pinned posts stay at the top"
    )
    
    # Moderation
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_blog_posts',
        help_text="Admin who approved this post"
    )
    
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the post was approved"
    )
    
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for rejection (if rejected)"
    )
    
    rejected_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the post was rejected"
    )
    
    # Rewards
    reward_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Reward amount for approved post"
    )
    
    reward_currency = models.CharField(
        max_length=10,
        default='UGX',
        help_text="Currency code for reward"
    )
    
    reward_paid = models.BooleanField(
        default=False,
        help_text="Whether reward has been paid"
    )
    
    reward_paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When reward was paid"
    )
    
    # Engagement Metrics
    view_count = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of views"
    )
    
    like_count = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of likes"
    )
    
    comment_count = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of comments"
    )
    
    share_count = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of shares"
    )
    
    # SEO & Metadata
    slug = models.SlugField(
        max_length=255,
        unique=True,
        blank=True,
        null=True,
        help_text="URL-friendly version of the post"
    )
    
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        null=True,
        help_text="SEO meta description"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the post was created"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the post was last updated"
    )
    
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the post was published/approved"
    )
    
    # Admin Notes
    admin_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Internal notes for admins"
    )
    
    class Meta:
        verbose_name = "Blog Post"
        verbose_name_plural = "Blog Posts"
        ordering = ['-is_pinned', '-is_featured', '-published_at', '-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', '-published_at']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['is_featured', '-published_at']),
        ]
    
    def __str__(self):
        content_preview = self.content[:50] + '...' if len(self.content) > 50 else self.content
        return f"{self.user.username} - {content_preview}"
    
    def save(self, *args, **kwargs):
        """Override save to generate slug and set published_at"""
        if not self.slug:
            self.slug = f"{self.user.username}-{uuid.uuid4().hex[:8]}"
        
        # Set published_at when status changes to approved
        if self.status == 'approved' and not self.published_at:
            self.published_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def approve(self, approved_by, reward_amount=None):
        """
        Approve the blog post and optionally set reward.
        
        Args:
            approved_by: User object who approved the post
            reward_amount: Optional Decimal reward amount
        """
        self.status = 'approved'
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.published_at = timezone.now()
        
        if reward_amount is not None:
            self.reward_amount = reward_amount
        
        self.save(update_fields=[
            'status', 'approved_by', 'approved_at', 
            'published_at', 'reward_amount'
        ])
    
    def reject(self, reason=None):
        """
        Reject the blog post with optional reason.
        
        Args:
            reason: String explaining why post was rejected
        """
        self.status = 'rejected'
        self.rejected_at = timezone.now()
        
        if reason:
            self.rejection_reason = reason
        
        self.save(update_fields=['status', 'rejected_at', 'rejection_reason'])
    
    def increment_views(self):
        """Increment view count"""
        self.view_count += 1
        self.save(update_fields=['view_count'])
    
    def increment_likes(self):
        """Increment like count"""
        self.like_count += 1
        self.save(update_fields=['like_count'])
    
    def increment_comments(self):
        """Increment comment count"""
        self.comment_count += 1
        self.save(update_fields=['comment_count'])
    
    def increment_shares(self):
        """Increment share count"""
        self.share_count += 1
        self.save(update_fields=['share_count'])
    
    @property
    def image_count(self):
        """Get number of images attached to this post"""
        return self.images.count()
    
    @property
    def is_approved(self):
        """Check if post is approved"""
        return self.status == 'approved'
    
    @property
    def is_pending(self):
        """Check if post is pending approval"""
        return self.status == 'pending'
    
    @property
    def engagement_score(self):
        """Calculate engagement score"""
        return (
            self.view_count + 
            (self.like_count * 5) + 
            (self.comment_count * 10) + 
            (self.share_count * 15)
        )


class BlogImage(models.Model):
    """
    Images attached to blog posts.
    Supports multiple images per post.
    """
    
    blog = models.ForeignKey(
        'BlogPost',
        on_delete=models.CASCADE,
        related_name='images',
        help_text="Blog post this image belongs to"
    )
    
    image = models.ImageField(
        upload_to=blog_image_upload_path,
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'webp']
            )
        ],
        help_text="Blog post image (max 5MB)"
    )
    
    caption = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Optional image caption"
    )
    
    order = models.IntegerField(
        default=0,
        help_text="Display order (lower numbers appear first)"
    )
    
    # Image Metadata
    file_size = models.IntegerField(
        default=0,
        help_text="File size in bytes"
    )
    
    width = models.IntegerField(
        null=True,
        blank=True,
        help_text="Image width in pixels"
    )
    
    height = models.IntegerField(
        null=True,
        blank=True,
        help_text="Image height in pixels"
    )
    
    # Timestamps
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the image was uploaded"
    )
    
    class Meta:
        verbose_name = "Blog Image"
        verbose_name_plural = "Blog Images"
        ordering = ['order', 'uploaded_at']
    
    def __str__(self):
        return f"Image for {self.blog.user.username}'s post #{self.blog.id}"
    
    def save(self, *args, **kwargs):
        """Override save to calculate file size"""
        if self.image:
            self.file_size = self.image.size
            
            # Get image dimensions if available
            try:
                from PIL import Image
                img = Image.open(self.image)
                self.width, self.height = img.size
            except:
                pass
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Override delete to remove file from storage"""
        # Delete the file from storage
        if self.image:
            if os.path.isfile(self.image.path):
                os.remove(self.image.path)
        
        super().delete(*args, **kwargs)


class BlogComment(models.Model):
    """
    Comments on blog posts.
    Supports nested comments (replies).
    """
    
    blog = models.ForeignKey(
        'BlogPost',
        on_delete=models.CASCADE,
        related_name='comments',
        help_text="Blog post this comment belongs to"
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blog_comments',
        help_text="User who made the comment"
    )
    
    content = models.TextField(
        max_length=500,
        help_text="Comment content (max 500 characters)"
    )
    
    # Threading (for replies)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        help_text="Parent comment (for replies)"
    )
    
    # Engagement
    like_count = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of likes on this comment"
    )
    
    # Moderation
    is_deleted = models.BooleanField(
        default=False,
        help_text="Soft delete flag"
    )
    
    is_flagged = models.BooleanField(
        default=False,
        help_text="Flagged for review"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the comment was created"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the comment was last updated"
    )
    
    class Meta:
        verbose_name = "Blog Comment"
        verbose_name_plural = "Blog Comments"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['blog', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        content_preview = self.content[:30] + '...' if len(self.content) > 30 else self.content
        return f"{self.user.username}: {content_preview}"
    
    @property
    def is_reply(self):
        """Check if this comment is a reply"""
        return self.parent is not None
    
    @property
    def reply_count(self):
        """Get number of replies to this comment"""
        return self.replies.filter(is_deleted=False).count()


class BlogLike(models.Model):
    """
    Track user likes on blog posts.
    One like per user per post.
    """
    
    blog = models.ForeignKey(
        'BlogPost',
        on_delete=models.CASCADE,
        related_name='likes',
        help_text="Blog post that was liked"
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blog_likes',
        help_text="User who liked the post"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the like was created"
    )
    
    class Meta:
        verbose_name = "Blog Like"
        verbose_name_plural = "Blog Likes"
        unique_together = ['blog', 'user']
        indexes = [
            models.Index(fields=['blog', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} liked post #{self.blog.id}"


class BlogView(models.Model):
    """
    Track blog post views for analytics.
    Can track multiple views per user.
    """
    
    blog = models.ForeignKey(
        'BlogPost',
        on_delete=models.CASCADE,
        related_name='views',
        help_text="Blog post that was viewed"
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blog_views',
        help_text="User who viewed the post (if logged in)"
    )
    
    # Analytics
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of viewer"
    )
    
    user_agent = models.TextField(
        blank=True,
        null=True,
        help_text="Browser user agent"
    )
    
    device_type = models.CharField(
        max_length=20,
        choices=[
            ('mobile', 'Mobile'),
            ('tablet', 'Tablet'),
            ('desktop', 'Desktop'),
            ('unknown', 'Unknown'),
        ],
        default='unknown',
        help_text="Device type"
    )
    
    viewed_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the post was viewed"
    )
    
    class Meta:
        verbose_name = "Blog View"
        verbose_name_plural = "Blog Views"
        ordering = ['-viewed_at']
        indexes = [
            models.Index(fields=['blog', '-viewed_at']),
            models.Index(fields=['user', '-viewed_at']),
        ]
    
    def __str__(self):
        viewer = self.user.username if self.user else 'Anonymous'
        return f"{viewer} viewed post #{self.blog.id}"


class BlogReport(models.Model):
    """
    User reports for inappropriate blog posts.
    Helps with moderation.
    """
    
    REPORT_REASONS = [
        ('spam', 'Spam'),
        ('inappropriate', 'Inappropriate Content'),
        ('harassment', 'Harassment'),
        ('fake', 'Fake/Misleading'),
        ('copyright', 'Copyright Violation'),
        ('other', 'Other'),
    ]
    
    blog = models.ForeignKey(
        'BlogPost',
        on_delete=models.CASCADE,
        related_name='reports',
        help_text="Blog post being reported"
    )
    
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blog_reports_made',
        help_text="User who made the report"
    )
    
    reason = models.CharField(
        max_length=20,
        choices=REPORT_REASONS,
        help_text="Reason for report"
    )
    
    description = models.TextField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Additional details"
    )
    
    # Status
    is_resolved = models.BooleanField(
        default=False,
        help_text="Whether the report has been reviewed"
    )
    
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blog_reports_resolved',
        help_text="Admin who resolved the report"
    )
    
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the report was resolved"
    )
    
    admin_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Admin notes on the report"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the report was created"
    )
    
    class Meta:
        verbose_name = "Blog Report"
        verbose_name_plural = "Blog Reports"
        ordering = ['-created_at']
        unique_together = ['blog', 'reporter']
        indexes = [
            models.Index(fields=['blog', '-created_at']),
            models.Index(fields=['is_resolved', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.reporter.username} reported post #{self.blog.id} for {self.reason}"


class BlogReward(models.Model):
    """
    Track blog post rewards and payments.
    Links to transactions for audit trail.
    """
    
    blog = models.OneToOneField(
        'BlogPost',
        on_delete=models.CASCADE,
        related_name='reward_record',
        help_text="Blog post that received reward"
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blog_rewards',
        help_text="User who received the reward"
    )
    
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Reward amount"
    )
    
    currency = models.CharField(
        max_length=10,
        default='UGX',
        help_text="Currency code"
    )
    
    # Payment Details
    is_paid = models.BooleanField(
        default=False,
        help_text="Whether reward has been paid"
    )
    
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When reward was paid"
    )
    
    transaction = models.ForeignKey(
        'users.Transaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blog_rewards',
        help_text="Transaction record for this reward"
    )
    
    # Metadata
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blog_rewards_approved',
        help_text="Admin who approved the reward"
    )
    
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Admin notes"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When reward was created"
    )
    
    class Meta:
        verbose_name = "Blog Reward"
        verbose_name_plural = "Blog Rewards"
        ordering = ['-created_at']
    
    def __str__(self):
        status = "Paid" if self.is_paid else "Pending"
        return f"{self.user.username} - {self.currency} {self.amount} ({status})"
    
    def mark_as_paid(self, transaction=None):
        """Mark reward as paid"""
        self.is_paid = True
        self.paid_at = timezone.now()
        if transaction:
            self.transaction = transaction
        self.save(update_fields=['is_paid', 'paid_at', 'transaction'])


# ==================== MODEL SUMMARY ====================

"""
BLOG APP MODELS:

1. BlogPost - Main blog post with content and status
   - User-generated content
   - Approval workflow (pending/approved/rejected)
   - Reward system
   - Engagement metrics (views, likes, comments, shares)
   - Featured and pinned flags
   
2. BlogImage - Multiple images per blog post
   - Image upload with validation
   - File size and dimensions tracking
   - Display order
   - Auto-cleanup on delete
   
3. BlogComment - Comments and replies
   - Nested comment structure
   - Like system
   - Soft delete
   - Moderation flags
   
4. BlogLike - User likes on posts
   - One like per user per post
   - Analytics tracking
   
5. BlogView - View tracking for analytics
   - User and anonymous views
   - Device type tracking
   - IP address logging
   
6. BlogReport - User reports for moderation
   - Multiple report reasons
   - Resolution workflow
   - Admin notes
   
7. BlogReward - Reward payment tracking
   - Links to Transaction model
   - Payment status
   - Audit trail

RELATIONSHIPS:
- BlogPost -> BlogImage (one-to-many)
- BlogPost -> BlogComment (one-to-many)
- BlogPost -> BlogLike (one-to-many)
- BlogPost -> BlogView (one-to-many)
- BlogPost -> BlogReport (one-to-many)
- BlogPost -> BlogReward (one-to-one)
- BlogComment -> BlogComment (self-referencing for replies)
- BlogPost -> User (many-to-one)
- All engagement models -> User (many-to-one)

INDEXES:
- Status + published_at for listing approved posts
- User + status for user's posts
- Created_at for recent posts
- Featured + published_at for featured posts
- Blog + created_at for comments/views/likes

VALIDATIONS:
- Content: max 2000 characters
- Images: jpg/jpeg/png/gif/webp only
- Comment: max 500 characters
- Reward: non-negative decimal
- Image size: validated in view (5MB max)
"""
