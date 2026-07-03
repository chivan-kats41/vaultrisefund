from django.contrib import admin
from django.urls import path, include
from . import views
from django.conf import settings
from django.conf.urls.static import static
from users import auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),

    # Authentication
    path('register/', auth_views.register_view, name='register'),
    path('login/',    auth_views.login_view,    name='login'),
    path('logout/',   auth_views.logout_view,   name='logout'),

    path('',            views.home,             name='home'),
    path('store/',       include('store.urls')),
    path('users/',       include('users.urls')),
    path('blog/',        include('blog.urls')),
    path('invitation/',  include('invitation.urls')),
    path('rewards/',     include('users.urls')),   # ← /rewards/ maps into users urls
    path('services/', include('services.urls')),
    path('', include('accounts.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)