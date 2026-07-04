from django.urls import path
from . import views

# Common paths bots/scanners probe for — none of these exist on a Django site,
# so any hit is unambiguously malicious.
TRAP_PATHS = [
    'wp-admin/', 'wp-login.php', 'wp-content/', 'wp-includes/',
    'xmlrpc.php', '.env', '.git/config', 'phpmyadmin/', 'phpMyAdmin/',
    'admin-login/', 'administrator/', 'config.php', 'wp-config.php',
    '.aws/credentials', 'server-status', 'vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php',
]

urlpatterns = [path(p, views.trap_view, name=f'trap_{i}') for i, p in enumerate(TRAP_PATHS)]