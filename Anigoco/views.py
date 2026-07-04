from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from store.models import InvestmentProduct
import json
from django.core.serializers.json import DjangoJSONEncoder
from decimal import Decimal


@login_required
def home(request):
    user = request.user

    # --- User profile & balance ---
    try:
        profile = user.profile  # users.models.UserProfile via OneToOne
    except Exception:
        profile = None

    if profile:
        total_balance = (
            (profile.recharge_balance or Decimal('0.00')) +
            (profile.withdrawal_balance or Decimal('0.00')) +
            (profile.commission_balance or Decimal('0.00'))
        )
        nickname  = profile.nickname or user.username
        vip_level = profile.vip_level
    else:
        total_balance = Decimal('0.00')
        nickname      = user.username
        vip_level     = 0

    # --- Products ---
    all_products = (
        InvestmentProduct.objects
        .select_related('category')
        .filter(is_active=True)
    )

    # Build category list from products themselves — no separate model import needed.
    # Resilient to either InvestmentCategory.name or the legacy category.category_name,
    # in case the FK still resolves to the old category app on some environments.
    seen_categories = {}
    for p in all_products:
        if p.category_id and p.category_id not in seen_categories:
            cat = p.category
            cat_name = getattr(cat, 'name', None) or getattr(cat, 'category_name', None) or str(cat)
            cat_slug = getattr(cat, 'slug', None) or ''
            seen_categories[p.category_id] = {
                'name': cat_name,
                'slug': cat_slug,
            }

    context = {
        'username':      user.username,
        'nickname':      nickname,
        'vip_level':     vip_level,
        'total_balance': total_balance,

        # ✅ Pass the actual profile object too — not just fields pulled
        # out of it — so the template can reference things like
        # profile.avatar directly (matching every other page: account(),
        # rewards(), info(), etc. all do this already). Without this, the
        # header avatar had to fall back to the user.profile.avatar
        # reverse-relation trick in the template just to work at all.
        'profile': profile,

        # ✅ One-time "you just logged in" flag for the channel-join popup.
        # request.session.pop() both reads AND removes the key in one step,
        # so this only evaluates True on the request immediately after
        # login_view sets it — a page refresh afterwards won't re-trigger
        # the popup, since the flag is already gone from the session.
        'show_welcome_popup': request.session.pop('just_logged_in', False),

        'products_json': json.dumps(
            [p.as_dict() for p in all_products],
            cls=DjangoJSONEncoder
        ),
        'categories_json': json.dumps(
            [
                {'id': k, 'name': v['name'], 'slug': v['slug']}
                for k, v in seen_categories.items()
            ],
            cls=DjangoJSONEncoder
        ),
    }

    return render(request, 'home.html', context)