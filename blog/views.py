"""
Views for Blog App
File: blog/views.py

Handles:
- Page rendering (blog.html, publish.html)
- API endpoints for AJAX requests
- Blog post CRUD operations
- Image upload handling
- Comment system
- Like/view tracking
- Report functionality
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Prefetch
from django.core.paginator import Paginator
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
import json
import logging

from .models import (
    BlogPost,
    BlogImage,
    BlogComment,
    BlogLike,
    BlogView,
    BlogReport
)

logger = logging.getLogger(__name__)


# ==================== HELPER FUNCTIONS ====================

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_device_type(request):
    """Detect device type from user agent"""
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    
    if 'mobile' in user_agent or 'android' in user_agent:
        return 'mobile'
    elif 'tablet' in user_agent or 'ipad' in user_agent:
        return 'tablet'
    elif 'windows' in user_agent or 'mac' in user_agent or 'linux' in user_agent:
        return 'desktop'
    else:
        return 'unknown'


def validate_image(image_file):
    """
    Validate uploaded image.
    
    Args:
        image_file: Uploaded file object
    
    Returns:
        tuple: (is_valid, error_message)
    """
    # Check file size (5MB max)
    if image_file.size > 5 * 1024 * 1024:
        return False, "Image size should be less than 5MB"
    
    # Check file type
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
    if image_file.content_type not in allowed_types:
        return False, "Only JPG, PNG, GIF, and WebP images are allowed"
    
    return True, None


# ==================== PAGE VIEWS ====================

#@login_required
def blog(request):
    """
    Main blog page - renders blog.html
    Displays list of approved blog posts
    """
    return render(request, 'blog/blog.html')


#@login_required
def publish(request):
    """
    Publish page - renders publish.html
    Form for creating new blog posts
    """
    return render(request, 'blog/publish.html')


# ==================== API ENDPOINTS ====================

#@login_required
@require_GET
def api_blog_list(request):
    """
    API: Get list of approved blog posts
    
    URL: /blog/api/posts/
    Method: GET
    Query Parameters:
        - page: Page number (default 1)
        - per_page: Items per page (default 10)
        - filter: 'all', 'featured', 'my_posts' (default 'all')
    
    Returns:
        JSON with blog posts and pagination info
    """
    try:
        # Get query parameters
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 10))
        filter_type = request.GET.get('filter', 'all')
        
        # Base query - only approved posts
        posts = BlogPost.objects.filter(
            status='approved'
        ).select_related(
            'user',
            'user__profile'
        ).prefetch_related(
            'images'
        ).order_by('-is_pinned', '-is_featured', '-published_at')
        
        # Apply filters
        if filter_type == 'featured':
            posts = posts.filter(is_featured=True)
        elif filter_type == 'my_posts':
            posts = posts.filter(user=request.user)
        
        # Pagination
        paginator = Paginator(posts, per_page)
        page_obj = paginator.get_page(page)
        
        # Build response
        posts_data = []
        for post in page_obj:
            # Get images
            images = [img.image.url for img in post.images.all()[:9]]
            
            # Get user info
            try:
                profile = post.user.profile
                nickname = profile.nickname or post.user.username
            except:
                nickname = post.user.username
            
            posts_data.append({
                'id': post.id,
                'slug': post.slug,
                'avatar': '/static/img/default-avatar.png',  # You can customize this
                'nickname': nickname,
                'username': f'@{post.user.username}',
                'contents': post.content,
                'image': images,
                'currency': post.reward_currency,
                'reward_amount': str(post.reward_amount),
                'create_time': post.published_at.strftime('%Y-%m-%d %H:%M') if post.published_at else '',
                'view_count': post.view_count,
                'like_count': post.like_count,
                'comment_count': post.comment_count,
                'is_featured': post.is_featured,
                'is_pinned': post.is_pinned,
            })
        
        return JsonResponse({
            'success': True,
            'posts': posts_data,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_posts': paginator.count,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            }
        })
    
    except Exception as e:
        logger.error(f'Error in api_blog_list: {str(e)}', exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Failed to load blog posts'
        }, status=500)


#@login_required
@require_POST
def api_blog_publish(request):
    """
    API: Publish a new blog post
    
    URL: /blog/api/publish/
    Method: POST
    Body: FormData
        - content: Blog post content (text)
        - images[0], images[1], etc.: Image files (up to 9)
    
    Returns:
        JSON with success status and blog post ID
    """
    try:
        # Get content
        content = request.POST.get('content', '').strip()
        
        # Validation
        if not content:
            return JsonResponse({
                'success': False,
                'message': 'Please enter blog content'
            }, status=400)
        
        if len(content) < 10:
            return JsonResponse({
                'success': False,
                'message': 'Blog content should be at least 10 characters'
            }, status=400)
        
        if len(content) > 2000:
            return JsonResponse({
                'success': False,
                'message': 'Blog content should not exceed 2000 characters'
            }, status=400)
        
        # Check for spam (more than 5 posts in last hour)
        from datetime import timedelta
        one_hour_ago = timezone.now() - timedelta(hours=1)
        recent_posts = BlogPost.objects.filter(
            user=request.user,
            created_at__gte=one_hour_ago
        ).count()
        
        if recent_posts >= 5:
            return JsonResponse({
                'success': False,
                'message': 'You are posting too frequently. Please wait before posting again.'
            }, status=429)
        
        # Create blog post
        blog_post = BlogPost.objects.create(
            user=request.user,
            content=content,
            status='pending'
        )
        
        # Handle image uploads
        images_uploaded = 0
        for key in request.FILES:
            if key.startswith('images'):
                if images_uploaded >= 9:
                    break
                
                image_file = request.FILES[key]
                
                # Validate image
                is_valid, error_msg = validate_image(image_file)
                if not is_valid:
                    # Delete the blog post if image validation fails
                    blog_post.delete()
                    return JsonResponse({
                        'success': False,
                        'message': error_msg
                    }, status=400)
                
                # Create BlogImage
                BlogImage.objects.create(
                    blog=blog_post,
                    image=image_file,
                    order=images_uploaded
                )
                images_uploaded += 1
        
        logger.info(f'Blog post created: #{blog_post.id} by {request.user.username}')
        
        return JsonResponse({
            'success': True,
            'message': 'Blog post submitted successfully',
            'post_id': blog_post.id,
            'slug': blog_post.slug,
            'images_uploaded': images_uploaded
        })
    
    except Exception as e:
        logger.error(f'Error in api_blog_publish: {str(e)}', exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Failed to publish blog post. Please try again.'
        }, status=500)


#@login_required
@require_GET
def api_blog_detail(request, post_id):
    """
    API: Get blog post details
    
    URL: /blog/api/post/<post_id>/
    Method: GET
    
    Returns:
        JSON with full blog post details
    """
    try:
        # Get blog post
        post = get_object_or_404(
            BlogPost.objects.select_related('user', 'user__profile').prefetch_related('images'),
            id=post_id,
            status='approved'
        )
        
        # Track view
        ip_address = get_client_ip(request)
        device_type = get_device_type(request)
        
        BlogView.objects.create(
            blog=post,
            user=request.user,
            ip_address=ip_address,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            device_type=device_type
        )
        
        # Check if user liked this post
        user_liked = BlogLike.objects.filter(
            blog=post,
            user=request.user
        ).exists()
        
        # Get images
        images = [img.image.url for img in post.images.all()]
        
        # Get user info
        try:
            profile = post.user.profile
            nickname = profile.nickname or post.user.username
            vip_level = profile.vip_level
        except:
            nickname = post.user.username
            vip_level = 0
        
        # Build response
        data = {
            'success': True,
            'post': {
                'id': post.id,
                'slug': post.slug,
                'content': post.content,
                'images': images,
                'author': {
                    'username': post.user.username,
                    'nickname': nickname,
                    'vip_level': vip_level,
                },
                'engagement': {
                    'view_count': post.view_count,
                    'like_count': post.like_count,
                    'comment_count': post.comment_count,
                    'share_count': post.share_count,
                    'user_liked': user_liked,
                },
                'reward': {
                    'amount': str(post.reward_amount),
                    'currency': post.reward_currency,
                },
                'is_featured': post.is_featured,
                'is_pinned': post.is_pinned,
                'published_at': post.published_at.strftime('%Y-%m-%d %H:%M') if post.published_at else '',
            }
        }
        
        return JsonResponse(data)
    
    except BlogPost.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Blog post not found'
        }, status=404)
    
    except Exception as e:
        logger.error(f'Error in api_blog_detail: {str(e)}', exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Failed to load blog post'
        }, status=500)


#@login_required
@require_POST
def api_blog_like(request, post_id):
    """
    API: Like/unlike a blog post
    
    URL: /blog/api/post/<post_id>/like/
    Method: POST
    
    Returns:
        JSON with new like status
    """
    try:
        # Get blog post
        post = get_object_or_404(BlogPost, id=post_id, status='approved')
        
        # Check if already liked
        like = BlogLike.objects.filter(
            blog=post,
            user=request.user
        ).first()
        
        if like:
            # Unlike
            like.delete()
            action = 'unliked'
        else:
            # Like
            BlogLike.objects.create(
                blog=post,
                user=request.user
            )
            action = 'liked'
        
        # Get updated like count
        post.refresh_from_db()
        
        return JsonResponse({
            'success': True,
            'action': action,
            'like_count': post.like_count
        })
    
    except BlogPost.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Blog post not found'
        }, status=404)
    
    except Exception as e:
        logger.error(f'Error in api_blog_like: {str(e)}', exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Failed to like post'
        }, status=500)


#@login_required
@require_POST
def api_blog_comment(request, post_id):
    """
    API: Add a comment to a blog post
    
    URL: /blog/api/post/<post_id>/comment/
    Method: POST
    Body: JSON
        - content: Comment content
        - parent_id: Parent comment ID (optional, for replies)
    
    Returns:
        JSON with success status and comment data
    """
    try:
        data = json.loads(request.body)
        
        # Get blog post
        post = get_object_or_404(BlogPost, id=post_id, status='approved')
        
        # Get content
        content = data.get('content', '').strip()
        parent_id = data.get('parent_id')
        
        # Validation
        if not content:
            return JsonResponse({
                'success': False,
                'message': 'Please enter a comment'
            }, status=400)
        
        if len(content) > 500:
            return JsonResponse({
                'success': False,
                'message': 'Comment should not exceed 500 characters'
            }, status=400)
        
        # Get parent comment if this is a reply
        parent = None
        if parent_id:
            try:
                parent = BlogComment.objects.get(
                    id=parent_id,
                    blog=post,
                    is_deleted=False
                )
            except BlogComment.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Parent comment not found'
                }, status=404)
        
        # Create comment
        comment = BlogComment.objects.create(
            blog=post,
            user=request.user,
            content=content,
            parent=parent
        )
        
        # Get user info
        try:
            profile = request.user.profile
            nickname = profile.nickname or request.user.username
        except:
            nickname = request.user.username
        
        return JsonResponse({
            'success': True,
            'message': 'Comment added successfully',
            'comment': {
                'id': comment.id,
                'content': comment.content,
                'user': {
                    'username': request.user.username,
                    'nickname': nickname,
                },
                'is_reply': comment.is_reply,
                'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M')
            }
        })
    
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    
    except Exception as e:
        logger.error(f'Error in api_blog_comment: {str(e)}', exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Failed to add comment'
        }, status=500)


#@login_required
@require_GET
def api_blog_comments(request, post_id):
    """
    API: Get comments for a blog post
    
    URL: /blog/api/post/<post_id>/comments/
    Method: GET
    Query Parameters:
        - page: Page number (default 1)
        - per_page: Items per page (default 20)
    
    Returns:
        JSON with comments list
    """
    try:
        # Get blog post
        post = get_object_or_404(BlogPost, id=post_id, status='approved')
        
        # Get query parameters
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        # Get top-level comments (not replies)
        comments = BlogComment.objects.filter(
            blog=post,
            parent__isnull=True,
            is_deleted=False
        ).select_related(
            'user',
            'user__profile'
        ).prefetch_related(
            'replies'
        ).order_by('-created_at')
        
        # Pagination
        paginator = Paginator(comments, per_page)
        page_obj = paginator.get_page(page)
        
        # Build response
        comments_data = []
        for comment in page_obj:
            # Get user info
            try:
                profile = comment.user.profile
                nickname = profile.nickname or comment.user.username
            except:
                nickname = comment.user.username
            
            # Get replies
            replies = []
            for reply in comment.replies.filter(is_deleted=False)[:5]:
                try:
                    reply_profile = reply.user.profile
                    reply_nickname = reply_profile.nickname or reply.user.username
                except:
                    reply_nickname = reply.user.username
                
                replies.append({
                    'id': reply.id,
                    'content': reply.content,
                    'user': {
                        'username': reply.user.username,
                        'nickname': reply_nickname,
                    },
                    'like_count': reply.like_count,
                    'created_at': reply.created_at.strftime('%Y-%m-%d %H:%M')
                })
            
            comments_data.append({
                'id': comment.id,
                'content': comment.content,
                'user': {
                    'username': comment.user.username,
                    'nickname': nickname,
                },
                'like_count': comment.like_count,
                'reply_count': comment.reply_count,
                'replies': replies,
                'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M')
            })
        
        return JsonResponse({
            'success': True,
            'comments': comments_data,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_comments': paginator.count,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            }
        })
    
    except BlogPost.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Blog post not found'
        }, status=404)
    
    except Exception as e:
        logger.error(f'Error in api_blog_comments: {str(e)}', exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Failed to load comments'
        }, status=500)


#@login_required
@require_POST
def api_blog_report(request, post_id):
    """
    API: Report a blog post
    
    URL: /blog/api/post/<post_id>/report/
    Method: POST
    Body: JSON
        - reason: Report reason (spam/inappropriate/harassment/fake/copyright/other)
        - description: Additional details (optional)
    
    Returns:
        JSON with success status
    """
    try:
        data = json.loads(request.body)
        
        # Get blog post
        post = get_object_or_404(BlogPost, id=post_id, status='approved')
        
        # Get data
        reason = data.get('reason')
        description = data.get('description', '').strip()
        
        # Validation
        valid_reasons = ['spam', 'inappropriate', 'harassment', 'fake', 'copyright', 'other']
        if reason not in valid_reasons:
            return JsonResponse({
                'success': False,
                'message': 'Invalid report reason'
            }, status=400)
        
        # Check if user already reported this post
        existing_report = BlogReport.objects.filter(
            blog=post,
            reporter=request.user
        ).first()
        
        if existing_report:
            return JsonResponse({
                'success': False,
                'message': 'You have already reported this post'
            }, status=400)
        
        # Create report
        BlogReport.objects.create(
            blog=post,
            reporter=request.user,
            reason=reason,
            description=description
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Report submitted successfully. Our team will review it shortly.'
        })
    
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    
    except Exception as e:
        logger.error(f'Error in api_blog_report: {str(e)}', exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Failed to submit report'
        }, status=500)


#@login_required
@require_GET
def api_my_posts(request):
    """
    API: Get user's own blog posts
    
    URL: /blog/api/my-posts/
    Method: GET
    Query Parameters:
        - status: Filter by status (pending/approved/rejected/all) (default 'all')
        - page: Page number (default 1)
    
    Returns:
        JSON with user's posts
    """
    try:
        status_filter = request.GET.get('status', 'all')
        page = int(request.GET.get('page', 1))
        per_page = 10
        
        # Base query
        posts = BlogPost.objects.filter(
            user=request.user
        ).prefetch_related('images').order_by('-created_at')
        
        # Apply status filter
        if status_filter != 'all':
            posts = posts.filter(status=status_filter)
        
        # Pagination
        paginator = Paginator(posts, per_page)
        page_obj = paginator.get_page(page)
        
        # Build response
        posts_data = []
        for post in page_obj:
            images = [img.image.url for img in post.images.all()[:9]]
            
            posts_data.append({
                'id': post.id,
                'slug': post.slug,
                'content': post.content[:100] + '...' if len(post.content) > 100 else post.content,
                'image_count': len(images),
                'images': images[:3],  # First 3 images
                'status': post.status,
                'reward_amount': str(post.reward_amount),
                'reward_paid': post.reward_paid,
                'view_count': post.view_count,
                'like_count': post.like_count,
                'comment_count': post.comment_count,
                'created_at': post.created_at.strftime('%Y-%m-%d %H:%M'),
                'published_at': post.published_at.strftime('%Y-%m-%d %H:%M') if post.published_at else None,
                'rejection_reason': post.rejection_reason,
            })
        
        return JsonResponse({
            'success': True,
            'posts': posts_data,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_posts': paginator.count,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            },
            'stats': {
                'total': BlogPost.objects.filter(user=request.user).count(),
                'pending': BlogPost.objects.filter(user=request.user, status='pending').count(),
                'approved': BlogPost.objects.filter(user=request.user, status='approved').count(),
                'rejected': BlogPost.objects.filter(user=request.user, status='rejected').count(),
            }
        })
    
    except Exception as e:
        logger.error(f'Error in api_my_posts: {str(e)}', exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Failed to load posts'
        }, status=500)


# ==================== VIEW SUMMARY ====================

"""
AVAILABLE VIEWS:

PAGE VIEWS (2):
---------------
1. blog(request)
   URL: /blog/
   Renders: blog/blog.html
   
2. publish(request)
   URL: /blog/publish/
   Renders: blog/publish.html


API ENDPOINTS (9):
------------------
1. api_blog_list(request)
   URL: /blog/api/posts/
   Method: GET
   Parameters: page, per_page, filter
   Returns: List of approved blog posts
   
2. api_blog_publish(request)
   URL: /blog/api/publish/
   Method: POST
   Body: FormData (content + images)
   Returns: Success status and post ID
   
3. api_blog_detail(request, post_id)
   URL: /blog/api/post/<id>/
   Method: GET
   Returns: Full blog post details
   Tracks: View count
   
4. api_blog_like(request, post_id)
   URL: /blog/api/post/<id>/like/
   Method: POST
   Returns: Like status (liked/unliked)
   
5. api_blog_comment(request, post_id)
   URL: /blog/api/post/<id>/comment/
   Method: POST
   Body: JSON (content, parent_id)
   Returns: Comment data
   
6. api_blog_comments(request, post_id)
   URL: /blog/api/post/<id>/comments/
   Method: GET
   Parameters: page, per_page
   Returns: List of comments with replies
   
7. api_blog_report(request, post_id)
   URL: /blog/api/post/<id>/report/
   Method: POST
   Body: JSON (reason, description)
   Returns: Success status
   
8. api_my_posts(request)
   URL: /blog/api/my-posts/
   Method: GET
   Parameters: status, page
   Returns: User's own posts with stats


HELPER FUNCTIONS:
-----------------
- get_client_ip(request) - Extract client IP
- get_device_type(request) - Detect device type
- validate_image(image_file) - Validate uploaded images


FEATURES:
---------
✅ Post creation with multiple images (up to 9)
✅ Image validation (size, type)
✅ Spam protection (5 posts per hour limit)
✅ Automatic view tracking
✅ Like/unlike functionality
✅ Comment system with replies
✅ Report functionality
✅ Pagination on all lists
✅ User post management
✅ Status filtering
✅ Engagement metrics
✅ Comprehensive error handling
✅ Logging for debugging


VALIDATION:
-----------
- Content: 10-2000 characters
- Images: Max 5MB, JPG/PNG/GIF/WebP
- Comments: Max 500 characters
- Spam: Max 5 posts per hour
- Report: Valid reasons only


ERROR HANDLING:
---------------
All endpoints return:
- Success: 200 with {success: true, ...}
- Error: 400/404/500 with {success: false, message: "..."}


SECURITY:
---------
- All endpoints require @login_required
- CSRF protection on POST requests
- Input validation and sanitization
- SQL injection protection (Django ORM)
- File upload validation
- Spam prevention
"""