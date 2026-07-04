from django.urls import path
from . import views

urlpatterns = [
    # Page views
    path('', views.blog, name='blog'),
    path('publish/', views.publish, name='publish'),
    
    # API endpoints
    path('api/posts/', views.api_blog_list, name='api_blog_list'),
    path('api/publish/', views.api_blog_publish, name='api_blog_publish'),
    path('api/post/<int:post_id>/', views.api_blog_detail, name='api_blog_detail'),
    path('api/post/<int:post_id>/like/', views.api_blog_like, name='api_blog_like'),
    path('api/post/<int:post_id>/comment/', views.api_blog_comment, name='api_blog_comment'),
    path('api/post/<int:post_id>/comments/', views.api_blog_comments, name='api_blog_comments'),
    path('api/post/<int:post_id>/report/', views.api_blog_report, name='api_blog_report'),
    path('api/my-posts/', views.api_my_posts, name='api_my_posts'),

    # ✅ Admin-only endpoints (added for this update)
    path('api/post/<int:post_id>/approve/', views.api_blog_admin_approve, name='api_blog_admin_approve'),
    path('api/post/<int:post_id>/reject/', views.api_blog_admin_reject, name='api_blog_admin_reject'),
]