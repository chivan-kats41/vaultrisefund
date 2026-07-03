"""
Signal Handlers for Blog App
File: blog/signals.py

This module automatically handles:
1. Sending notifications when blog posts are approved/rejected
2. Creating reward records for approved posts
3. Updating engagement metrics
4. Notifying users of comments on their posts
5. Tracking view counts
6. Handling reward payments

IMPORTANT: Add to blog/apps.py:
    def ready(self):
        import blog.signals
"""

from django.db.models.signals import post_save, pre_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
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
from users.models import Transaction, Notification, UserProfile

# Get the User model correctly
User = get_user_model()


# ==================== BLOG POST SIGNALS ====================

@receiver(post_save, sender=BlogPost)
def handle_blog_post_status_change(sender, instance, created, **kwargs):
    """
    Handle blog post creation and status changes.
    
    Actions:
    - Send notification when post is submitted
    - Send notification when post is approved
    - Send notification when post is rejected
    - Create reward record when approved
    """
    post = instance
    
    if created:
        # New post submitted - notify admins
        admin_users = User.objects.filter(
            is_staff=True,
            is_active=True
        )
        
        for admin in admin_users[:5]:  # Notify first 5 admins
            try:
                Notification.objects.create(
                    user=admin,
                    title="New Blog Post Submitted 📝",
                    message=f"{post.user.username} submitted a new blog post for review.",
                    notification_type='system'
                )
            except Exception as e:
                print(f"Error creating admin notification: {e}")
        
        # Notify user that post is pending
        try:
            Notification.objects.create(
                user=post.user,
                title="Blog Post Submitted ✅",
                message="Your blog post has been submitted and is awaiting approval. You'll be notified once it's reviewed.",
                notification_type='system'
            )
        except Exception as e:
            print(f"Error creating user notification: {e}")
    
    else:
        # Status changed - check if approved or rejected
        # We need to check the previous status from database
        # This is a workaround since we can't easily get the old instance in post_save
        
        # Check if status changed to approved
        if post.status == 'approved' and post.approved_at:
            # Check if this is a recent approval (within last 2 seconds)
            from datetime import timedelta
            if post.approved_at >= timezone.now() - timedelta(seconds=2):
                # Notify user
                try:
                    Notification.objects.create(
                        user=post.user,
                        title="Blog Post Approved! 🎉",
                        message=f"Congratulations! Your blog post has been approved and is now visible to everyone!",
                        notification_type='system',
                        is_important=True
                    )
                except Exception as e:
                    print(f"Error creating approval notification: {e}")
                
                # Create reward record if reward amount is set
                if post.reward_amount > 0:
                    try:
                        BlogReward.objects.get_or_create(
                            blog=post,
                            defaults={
                                'user': post.user,
                                'amount': post.reward_amount,
                                'currency': post.reward_currency,
                                'approved_by': post.approved_by,
                                'is_paid': False
                            }
                        )
                    except Exception as e:
                        print(f"Error creating reward record: {e}")
        
        # Check if status changed to rejected
        elif post.status == 'rejected' and post.rejected_at:
            # Check if this is a recent rejection (within last 2 seconds)
            from datetime import timedelta
            if post.rejected_at >= timezone.now() - timedelta(seconds=2):
                # Notify user
                reason = post.rejection_reason or "Your post did not meet our community guidelines."
                try:
                    Notification.objects.create(
                        user=post.user,
                        title="Blog Post Rejected ❌",
                        message=f"Your blog post was not approved. Reason: {reason}",
                        notification_type='system'
                    )
                except Exception as e:
                    print(f"Error creating rejection notification: {e}")


@receiver(post_save, sender=BlogPost)
def auto_generate_slug(sender, instance, created, **kwargs):
    """
    Automatically generate slug if not provided.
    """
    if created and not instance.slug:
        import uuid
        instance.slug = f"{instance.user.username}-{uuid.uuid4().hex[:8]}"
        instance.save(update_fields=['slug'])


# ==================== BLOG COMMENT SIGNALS ====================

@receiver(post_save, sender=BlogComment)
def handle_new_comment(sender, instance, created, **kwargs):
    """
    Handle new comments.
    
    Actions:
    - Increment comment count on blog post
    - Notify blog post author
    - Notify parent comment author (if reply)
    """
    if not created:
        return
    
    comment = instance
    blog = comment.blog
    
    # Increment comment count on blog post
    try:
        blog.comment_count += 1
        blog.save(update_fields=['comment_count'])
    except Exception as e:
        print(f"Error updating comment count: {e}")
    
    # Notify blog post author (unless commenting on own post)
    if comment.user != blog.user:
        try:
            Notification.objects.create(
                user=blog.user,
                title="New Comment on Your Post 💬",
                message=f"{comment.user.username} commented on your blog post: \"{comment.content[:50]}...\"",
                notification_type='system'
            )
        except Exception as e:
            print(f"Error creating comment notification: {e}")
    
    # If this is a reply, notify parent comment author
    if comment.parent and comment.user != comment.parent.user:
        try:
            Notification.objects.create(
                user=comment.parent.user,
                title="New Reply to Your Comment 💬",
                message=f"{comment.user.username} replied to your comment: \"{comment.content[:50]}...\"",
                notification_type='system'
            )
        except Exception as e:
            print(f"Error creating reply notification: {e}")


@receiver(post_delete, sender=BlogComment)
def handle_comment_deletion(sender, instance, **kwargs):
    """
    Handle comment deletion.
    
    Actions:
    - Decrement comment count on blog post
    """
    comment = instance
    blog = comment.blog
    
    try:
        if blog.comment_count > 0:
            blog.comment_count -= 1
            blog.save(update_fields=['comment_count'])
    except Exception as e:
        print(f"Error updating comment count on deletion: {e}")


# ==================== BLOG LIKE SIGNALS ====================

@receiver(post_save, sender=BlogLike)
def handle_new_like(sender, instance, created, **kwargs):
    """
    Handle new likes.
    
    Actions:
    - Increment like count on blog post
    - Notify blog post author
    """
    if not created:
        return
    
    like = instance
    blog = like.blog
    
    # Increment like count
    try:
        blog.like_count += 1
        blog.save(update_fields=['like_count'])
    except Exception as e:
        print(f"Error updating like count: {e}")
    
    # Notify blog post author (unless liking own post)
    if like.user != blog.user:
        # Don't spam with like notifications - only notify for milestones
        if blog.like_count in [1, 5, 10, 25, 50, 100, 500, 1000]:
            try:
                Notification.objects.create(
                    user=blog.user,
                    title=f"Milestone: {blog.like_count} Likes! 👍",
                    message=f"Your blog post reached {blog.like_count} likes!",
                    notification_type='system',
                    is_important=(blog.like_count >= 100)
                )
            except Exception as e:
                print(f"Error creating like notification: {e}")


@receiver(post_delete, sender=BlogLike)
def handle_like_deletion(sender, instance, **kwargs):
    """
    Handle like removal (unlike).
    
    Actions:
    - Decrement like count on blog post
    """
    like = instance
    blog = like.blog
    
    try:
        if blog.like_count > 0:
            blog.like_count -= 1
            blog.save(update_fields=['like_count'])
    except Exception as e:
        print(f"Error updating like count on deletion: {e}")


# ==================== BLOG VIEW SIGNALS ====================

@receiver(post_save, sender=BlogView)
def handle_new_view(sender, instance, created, **kwargs):
    """
    Handle new views.
    
    Actions:
    - Increment view count on blog post
    - Notify author on view milestones
    """
    if not created:
        return
    
    view = instance
    blog = view.blog
    
    # Increment view count
    try:
        blog.view_count += 1
        blog.save(update_fields=['view_count'])
    except Exception as e:
        print(f"Error updating view count: {e}")
    
    # Notify on view milestones
    if blog.view_count in [10, 50, 100, 500, 1000, 5000, 10000]:
        try:
            Notification.objects.create(
                user=blog.user,
                title=f"Milestone: {blog.view_count} Views! 👁️",
                message=f"Your blog post reached {blog.view_count} views!",
                notification_type='system',
                is_important=(blog.view_count >= 1000)
            )
        except Exception as e:
            print(f"Error creating view milestone notification: {e}")


# ==================== BLOG REPORT SIGNALS ====================

@receiver(post_save, sender=BlogReport)
def handle_new_report(sender, instance, created, **kwargs):
    """
    Handle new reports.
    
    Actions:
    - Notify admins of new report
    - Flag post if multiple reports
    """
    if not created:
        return
    
    report = instance
    blog = report.blog
    
    # Notify admins
    admin_users = User.objects.filter(
        is_staff=True,
        is_active=True
    )
    
    for admin in admin_users[:5]:  # Notify first 5 admins
        try:
            Notification.objects.create(
                user=admin,
                title="Blog Post Reported 🚩",
                message=f"Post #{blog.id} by {blog.user.username} was reported for: {report.get_reason_display()}",
                notification_type='system',
                is_important=True
            )
        except Exception as e:
            print(f"Error creating report notification: {e}")
    
    # Auto-flag or reject if too many reports
    report_count = BlogReport.objects.filter(
        blog=blog,
        is_resolved=False
    ).count()
    
    if report_count >= 3:
        # Auto-reject post with multiple reports
        try:
            blog.reject(reason=f"Multiple user reports ({report_count} reports)")
            
            # Notify post author
            Notification.objects.create(
                user=blog.user,
                title="Blog Post Removed ⚠️",
                message=f"Your blog post was removed due to multiple user reports.",
                notification_type='system',
                is_important=True
            )
        except Exception as e:
            print(f"Error auto-rejecting reported post: {e}")


# ==================== BLOG REWARD SIGNALS ====================

@receiver(post_save, sender=BlogReward)
def handle_reward_payment(sender, instance, created, **kwargs):
    """
    Handle reward payments.
    
    Actions:
    - Credit user balance when reward is marked as paid
    - Create transaction record
    - Send notification to user
    """
    if created:
        return
    
    reward = instance
    
    # Check if reward was just marked as paid
    # Only process if is_paid is True and paid_at is recent
    if reward.is_paid and reward.paid_at:
        from datetime import timedelta
        if reward.paid_at >= timezone.now() - timedelta(seconds=2):
            # Reward was just paid
            user = reward.user
            amount = reward.amount
            
            try:
                # Credit user balance
                profile = user.profile
                profile.commission_balance += amount
                profile.save(update_fields=['commission_balance'])
                
                # Create transaction if not already exists
                if not reward.transaction:
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
                    
                    reward.transaction = transaction
                    reward.save(update_fields=['transaction'])
                
                # Update blog post
                blog = reward.blog
                blog.reward_paid = True
                blog.reward_paid_at = timezone.now()
                blog.save(update_fields=['reward_paid', 'reward_paid_at'])
                
                # Send notification
                Notification.objects.create(
                    user=user,
                    title="Blog Reward Received! 💰",
                    message=f"You've received {reward.currency} {amount:,.0f} reward for your blog post!",
                    notification_type='referral',
                    is_important=True
                )
                
                print(f"✓ Blog reward paid: {user.username} received {reward.currency} {amount}")
                
            except Exception as e:
                print(f"✗ Error processing reward payment: {e}")


# ==================== BLOG IMAGE SIGNALS ====================

@receiver(post_delete, sender=BlogImage)
def cleanup_blog_image_file(sender, instance, **kwargs):
    """
    Delete image file from storage when BlogImage is deleted.
    """
    import os
    
    if instance.image:
        try:
            if os.path.isfile(instance.image.path):
                os.remove(instance.image.path)
                print(f"✓ Deleted image file: {instance.image.path}")
        except Exception as e:
            print(f"✗ Error deleting image file: {e}")


# ==================== HELPER FUNCTIONS ====================

def notify_admins(title, message, is_important=False):
    """
    Send notification to all active admin users.
    
    Args:
        title: Notification title
        message: Notification message
        is_important: Whether notification is important
    """
    admin_users = User.objects.filter(
        is_staff=True,
        is_active=True
    )
    
    for admin in admin_users[:10]:  # Limit to first 10 admins
        try:
            Notification.objects.create(
                user=admin,
                title=title,
                message=message,
                notification_type='system',
                is_important=is_important
            )
        except Exception as e:
            print(f"Error notifying admin {admin.username}: {e}")


def check_spam_user(user):
    """
    Check if user is spamming blog posts.
    
    Args:
        user: User instance
    
    Returns:
        bool: True if user is likely spamming
    """
    from datetime import timedelta
    
    # Check posts in last hour
    one_hour_ago = timezone.now() - timedelta(hours=1)
    recent_posts = BlogPost.objects.filter(
        user=user,
        created_at__gte=one_hour_ago
    ).count()
    
    # More than 5 posts in an hour is suspicious
    return recent_posts > 5


def calculate_reward_amount(blog_post):
    """
    Calculate appropriate reward amount based on post quality.
    
    Args:
        blog_post: BlogPost instance
    
    Returns:
        Decimal: Suggested reward amount
    """
    base_reward = Decimal('5000.00')
    
    # Bonus for images
    image_count = blog_post.image_count
    if image_count > 0:
        base_reward += Decimal('1000.00') * min(image_count, 3)
    
    # Bonus for content length
    content_length = len(blog_post.content)
    if content_length > 500:
        base_reward += Decimal('2000.00')
    elif content_length > 200:
        base_reward += Decimal('1000.00')
    
    # Cap maximum reward
    max_reward = Decimal('50000.00')
    return min(base_reward, max_reward)


def get_engagement_rank(blog_post):
    """
    Get engagement rank for a blog post.
    
    Args:
        blog_post: BlogPost instance
    
    Returns:
        str: Rank ('low', 'medium', 'high', 'viral')
    """
    score = blog_post.engagement_score
    
    if score >= 1000:
        return 'viral'
    elif score >= 500:
        return 'high'
    elif score >= 100:
        return 'medium'
    else:
        return 'low'


# ==================== POST-SAVE OPTIMIZATION ====================

@receiver(post_save, sender=BlogPost)
def update_user_blog_stats(sender, instance, created, **kwargs):
    """
    Update user's blog statistics in their profile.
    """
    if created:
        try:
            profile = instance.user.profile
            
            # Could add custom fields to UserProfile if needed:
            # profile.total_blog_posts += 1
            # profile.save(update_fields=['total_blog_posts'])
            
        except Exception as e:
            print(f"Error updating user blog stats: {e}")


# ==================== SIGNAL SUMMARY ====================

"""
REGISTERED SIGNALS:

1. post_save(BlogPost) -> handle_blog_post_status_change
   - Notify admins on new post
   - Notify user on submission
   - Notify user on approval/rejection
   - Create reward record on approval

2. post_save(BlogPost) -> auto_generate_slug
   - Auto-generate slug if not provided

3. post_save(BlogPost) -> update_user_blog_stats
   - Update user statistics

4. post_save(BlogComment) -> handle_new_comment
   - Increment comment count
   - Notify post author
   - Notify parent comment author (replies)

5. post_delete(BlogComment) -> handle_comment_deletion
   - Decrement comment count

6. post_save(BlogLike) -> handle_new_like
   - Increment like count
   - Notify on milestones (1, 5, 10, 25, 50, 100, 500, 1000)

7. post_delete(BlogLike) -> handle_like_deletion
   - Decrement like count

8. post_save(BlogView) -> handle_new_view
   - Increment view count
   - Notify on milestones (10, 50, 100, 500, 1000, 5000, 10000)

9. post_save(BlogReport) -> handle_new_report
   - Notify admins
   - Auto-reject post with 3+ reports

10. post_save(BlogReward) -> handle_reward_payment
    - Credit user balance
    - Create transaction
    - Send notification
    - Update blog post

11. post_delete(BlogImage) -> cleanup_blog_image_file
    - Delete image file from storage

HELPER FUNCTIONS:

- notify_admins(title, message, is_important)
  Send notification to all admins

- check_spam_user(user)
  Check if user is spamming posts

- calculate_reward_amount(blog_post)
  Calculate suggested reward based on quality

- get_engagement_rank(blog_post)
  Get engagement rank (low/medium/high/viral)

NOTIFICATION TRIGGERS:

User Notifications:
- Post submitted (pending approval)
- Post approved
- Post rejected
- New comment on post
- New reply to comment
- Like milestones (1, 5, 10, 25, 50, 100, 500, 1000)
- View milestones (10, 50, 100, 500, 1000, 5000, 10000)
- Reward received
- Post removed (multiple reports)

Admin Notifications:
- New post submitted
- Post reported
- Auto-rejection (3+ reports)

AUTOMATIC ACTIONS:

- Generate slug on post creation
- Create reward record on approval
- Increment/decrement engagement counts
- Auto-reject posts with 3+ reports
- Credit balance on reward payment
- Create transaction records
- Clean up image files on deletion

IMPORTANT:
Make sure to import signals in blog/apps.py:

    from django.apps import AppConfig
    
    class BlogConfig(AppConfig):
        default_auto_field = 'django.db.models.BigAutoField'
        name = 'blog'
        
        def ready(self):
            import blog.signals
"""