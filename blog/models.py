"""
Models for the Blog App - User-Generated Content Platform
File: blog/models.py

This module handles:
- Blog post creation and management
- Multi-image upload support (required — at least 1 image per post)
- Approval workflow (pending/approved/rejected)
- Reward system for approved posts — reward amount is chosen by the admin
  at approval time, constrained to UGX 100 - UGX 500,000
- Comment system (writing restricted to admin accounts — enforced in views.py)
- Like/reaction system
- User engagement tracking
- Reward crediting + notifications on approval/rejection (this update):
  approving a post credits UserProfile.commission_balance (the commission
  wallet) with the reward amount, logs a Transaction, and creates a
  Notification the user sees in mail.html / api_notifications. Rejecting a
  post creates a Notification explaining why, with no balance change.

CREDIT_REWARD_AND_NOTIFY IS PUBLIC + IDEMPOTENT (this update):
  Previously named _credit_reward_and_notify() and only ever called from
  approve(). It's now public (credit_reward_and_notify()) and guarded by
  reward_paid, so blog/admin.py can also call it directly — e.g. from a
  "pay rewards" catch-up action for posts approved before this crediting
  system existed — without ever risking a double credit to the same post.

IMPORTANT: All User model references use settings.AUTH_USER_MODEL
"""

from django.db import models
from django.db import transaction as db_transaction
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.utils import timezone
from decimal import Decimal
import uuid
import os


# Reward bounds — the admin can only ever approve a post with a reward
# amount inside this range. Enforced in BlogPost.approve() below and again
# in the admin-only API endpoint (blog/views.py: api_blog_admin_approve),
# so it can't be bypassed from either code path.
MIN_REWARD_AMOUNT = Decimal('100.00')
MAX_REWARD_AMOUNT = Decimal('500000.00')


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
    - At least one image attachment REQUIRED (enforced in the publish view,
      not at the DB level, since BlogImage is a separate related model)
    - Approval workflow
    - Reward system — amount is entirely the admin's choice, within
      UGX 100 - UGX 500,000, set only through BlogPost.approve()
    - Engagement metrics
    - On approval: reward is credited to the author's commission wallet
      (UserProfile.commission_balance) and a Notification + Transaction
      record are created. On rejection: a Notification explaining the
      rejection is created (no balance change).
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
        help_text=(
            "Reward amount for approved post. Stays 0.00 while pending — "
            "only set by an admin at approval time, and always constrained "
            "to UGX 100 - UGX 500,000 (see BlogPost.approve())."
        )
    )

    reward_currency = models.CharField(
        max_length=10,
        default='UGX',
        help_text="Currency code for reward"
    )

    reward_paid = models.BooleanField(
        default=False,
        help_text=(
            "Whether reward has been credited to the user's commission "
            "wallet. Set True automatically inside credit_reward_and_notify() "
            "the moment the credit succeeds. Also acts as the idempotency "
            "guard preventing the same post's reward from being credited "
            "twice, no matter how many times approve()/credit_reward_and_notify() "
            "get called on it (e.g. from admin actions)."
        )
    )

    reward_paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When reward was credited"
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

    def approve(self, approved_by, reward_amount):
        """
        Approve the blog post, set its reward, and credit the author.

        The reward amount is REQUIRED and is entirely the admin's choice —
        it is never derived from the post's content, images, or author. It
        must fall within UGX 100 - UGX 500,000 (inclusive). Anything outside
        that range raises ValueError and the post is NOT approved, so a bad
        value can never slip through from either the admin API, the Django
        admin change form, or a direct call in code/shell.

        On success this also, atomically:
          - Credits UserProfile.commission_balance by reward_amount
            (the "commission wallet" — this is what shows up in the user's
            total account balance on the account page).
          - Creates a Transaction record (type='blog_reward') for the
            audit trail / balance.html history.
          - Creates a Notification telling the user their post was
            approved and how much they earned.

        If the credit/notify step fails for any reason, the whole thing
        rolls back — the post is never left "approved" without its reward
        actually reaching the user's wallet.

        Safe to call more than once on the same post: credit_reward_and_notify()
        is guarded by reward_paid, so a second call will update status/
        approved_by/etc. again but will NOT credit the wallet a second time.

        Args:
            approved_by:   User object who approved the post (must be staff)
            reward_amount: Decimal (or value convertible to Decimal) between
                           100 and 500000
        """
        reward_amount = Decimal(str(reward_amount))

        if reward_amount < MIN_REWARD_AMOUNT or reward_amount > MAX_REWARD_AMOUNT:
            raise ValueError(
                f'Reward amount must be between UGX {MIN_REWARD_AMOUNT:,.0f} '
                f'and UGX {MAX_REWARD_AMOUNT:,.0f}'
            )

        with db_transaction.atomic():
            self.status = 'approved'
            self.approved_by = approved_by
            self.approved_at = timezone.now()
            self.published_at = timezone.now()
            self.reward_amount = reward_amount

            self.save(update_fields=[
                'status', 'approved_by', 'approved_at',
                'published_at', 'reward_amount'
            ])

            self.credit_reward_and_notify(reward_amount)

    def credit_reward_and_notify(self, reward_amount):
        """
        Credit reward_amount to the author's commission wallet and notify
        them.

        Called from approve(), and also safe to call directly — e.g. from
        blog/admin.py's "pay rewards" catch-up action for posts that were
        approved before this crediting system existed, or from a shell/
        management command.

        IDEMPOTENT: if this post has already been paid (reward_paid=True),
        this is a no-op and returns None immediately — the wallet can never
        be credited twice for the same post no matter how many times or
        from how many different code paths this gets called.

        Local import of users.models avoids any app-loading-order /
        circular-import issues between the blog and users apps.

        Returns:
            The created Transaction, or None if the post was already paid.
        """
        if self.reward_paid:
            return None

        from users.models import UserProfile, Transaction, Notification

        # get_or_create as a safety net — every real user should already
        # have a UserProfile via the post_save signal on the User model,
        # but this mirrors the defensive pattern used elsewhere in the
        # codebase (e.g. users.views.get_or_create_profile).
        profile, _ = UserProfile.objects.get_or_create(user=self.user)

        balance_before = profile.commission_balance
        profile.commission_balance += reward_amount
        profile.total_earnings = (profile.total_earnings or Decimal('0.00')) + reward_amount
        profile.save(update_fields=['commission_balance', 'total_earnings'])

        transaction = Transaction.objects.create(
            user=self.user,
            transaction_number=(
                f"TXN{timezone.now().strftime('%Y%m%d%H%M%S')}"
                f"{uuid.uuid4().hex[:6].upper()}"
            ),
            transaction_type='blog_reward',
            amount=reward_amount,
            balance_type='commission_balance',
            balance_before=balance_before,
            balance_after=profile.commission_balance,
            description=f'Reward for approved blog post #{self.id}',
            reference_id=f'BLOG{self.id}',
            status='completed',
        )

        self.reward_paid = True
        self.reward_paid_at = timezone.now()
        self.save(update_fields=['reward_paid', 'reward_paid_at'])

        Notification.objects.create(
            user=self.user,
            title='Blog Post Approved! 🎉',
            message=(
                f'Your blog post has been approved! You earned '
                f'{self.reward_currency} {reward_amount:,.2f}, credited to '
                f'your commission wallet.'
            ),
            notification_type='blog_approved',
            is_important=True,
        )

        return transaction

    def reject(self, reason=None):
        """
        Reject the blog post with optional reason, and notify the author.

        Args:
            reason: String explaining why post was rejected
        """
        self.status = 'rejected'
        self.rejected_at = timezone.now()

        if reason:
            self.rejection_reason = reason

        self.save(update_fields=['status', 'rejected_at', 'rejection_reason'])

        # Local import — see credit_reward_and_notify() for why.
        from users.models import Notification

        message = 'Your blog post was not approved.'
        if reason:
            message += f' Reason: {reason}'

        Notification.objects.create(
            user=self.user,
            title='Blog Post Rejected',
            message=message,
            notification_type='blog_rejected',
        )

    def increment_views(self):
        """Increment view count"""
        self.view_count += 1
        self.save(update_fields=['view_count'])

    def increment_likes(self):
        """Increment like count"""
        self.like_count += 1
        self.save(update_fields=['like_count'])

    def decrement_likes(self):
        """Decrement like count, never going below zero"""
        if self.like_count > 0:
            self.like_count -= 1
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
    Every post must have AT LEAST ONE of these — enforced in
    blog/views.py: api_blog_publish, not at the database level (since this
    is a separate related model, a DB-level "at least one" constraint isn't
    practical in Django without a signal/trigger).
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

    Comments are restricted to admin accounts only (is_staff or
    is_superuser). This restriction is enforced in blog/views.py:
    api_blog_comment, NOT at the model level, since the model has no
    reliable way to know "who is making this request" — only the view has
    access to request.user at creation time.

    Supports nested comments (replies), though in practice — since only
    admins can comment — replies would also only ever come from admins.
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
        help_text="Admin user who made the comment"
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
    Any logged-in user (not just admins) can like a post. One like per
    user per post, enforced by unique_together below.
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

    NOTE: as of this update, the actual crediting of reward money happens
    directly inside BlogPost.credit_reward_and_notify() (straight to
    UserProfile.commission_balance + a users.Transaction row), and is
    guarded against double-crediting by BlogPost.reward_paid. This model
    is kept for optional extra bookkeeping/reporting if you want a
    dedicated "blog rewards" table separate from the general Transaction
    ledger (see blog/admin.py: BlogRewardAdmin.process_payments, which
    links a BlogReward row to whichever Transaction actually did the
    crediting), but it is not required for the credit to reach the user.
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