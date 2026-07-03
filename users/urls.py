from django.urls import path
from . import views

urlpatterns = [
    # Page views
    path('',             views.account,      name='account'),
    path('vip/',         views.vip,          name='vip'),
    path('about/',       views.about,        name='about'),
    path('mail/',        views.mail,         name='mail'),
    path('info/',        views.info,         name='info'),
    path('orders/',      views.orders,       name='orders'),
    path('balance/',     views.balance,      name='balance'),
    path('help/',        views.help,         name='help'),
    path('rewards/',     views.rewards,      name='rewards'),   # ← new

    # Financial operations
    path('recharge/',    views.recharge,     name='recharge'),
    path('withdraw/',    views.withdraw,     name='withdraw'),
    path('bank-card/',   views.bankCardInfo, name='bank'),
    path('add-card/',    views.AddCard,      name='AddCard'),
    path('bankCardInfo/', views.bankCardInfo, name='bankCardInfo'),

    # API endpoints
    path('api/wallet/get/',                        views.api_wallet_get,              name='api_wallet_get'),
    path('api/wallet/add/',                        views.api_wallet_add,              name='api_wallet_add'),
    path('api/wallet/update/',                     views.api_wallet_update,           name='api_wallet_update'),
    path('api/withdrawal/apply/',                  views.api_withdrawal_apply,        name='api_withdrawal_apply'),
    path('api/recharge/initiate/',                 views.api_recharge_initiate,       name='api_recharge_initiate'),
    path('api/user/balance/',                      views.api_user_balance,            name='api_user_balance'),
    path('api/profile/update/',                    views.api_update_profile,          name='api_update_profile'),
    path('api/password/change/',                   views.api_change_password,         name='api_change_password'),
    path('api/transactions/',                      views.api_transactions,            name='api_transactions'),
    path('api/order/<int:order_id>/detail/',       views.api_order_detail,            name='api_order_detail'),
    path('api/products/list/',                     views.api_products_list,           name='api_products_list'),
    path('api/product/purchase/',                  views.api_product_purchase,        name='api_product_purchase'),
    path('api/notifications/',                     views.api_notifications,           name='api_notifications'),
    path('api/notification/<int:notification_id>/read/', views.api_notification_mark_read, name='api_notification_mark_read'),
    path('api/vip/info/',                          views.api_vip_info,                name='api_vip_info'),
    path('webhook/payment/callback/',              views.webhook_payment_callback,    name='webhook_payment_callback'),
    # ... your existing urls ...

    path('password-reset/',         views.password_reset_request, name='password_reset_request'),
    path('password-reset/verify/',  views.password_reset_verify,  name='password_reset_verify'),
    path('password-reset/confirm/', views.password_reset_confirm, name='password_reset_confirm'),
    path('password-reset/resend/',  views.password_reset_resend,  name='password_reset_resend'),
]