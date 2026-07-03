"""
Views for the Accounts app
File: accounts/views.py

Home/index page — moved here since this app's views.py was unused and the
actual homepage view could not be located in accounts/invitation/services/
store/users/category. If you later find the original view elsewhere, either
delete that one or point urls.py at this one instead (not both).
"""
import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from category.models import category as Category
from store.models import InvestmentProduct
from users.models import UserProfile


def get_or_create_profile(user):
    """
    Mirrors users/views.py::get_or_create_profile so this view doesn't
    depend on importing from the users app's view module directly.
    """
    try:
        return UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=user)
        profile.generate_referral_code()
        return profile


@login_required
def home(request):
    profile = get_or_create_profile(request.user)

    products   = InvestmentProduct.objects.filter(is_active=True).select_related('category')
    categories = Category.objects.all()

    products_json = json.dumps([p.as_dict() for p in products])
    categories_json = json.dumps([
        {'id': c.id, 'name': c.category_name, 'slug': c.slug}
        for c in categories
    ])

    context = {
        # ✅ user.nickname (Accounts.nickname) is the single source of truth
        # for display — this is the fix for the bug where the homepage was
        # showing the raw phone number / admin username instead of the
        # nickname entered at registration.
        'nickname':        request.user.nickname or request.user.username,
        'user':             request.user,
        'profile':          profile,
        'total_balance':    profile.recharge_balance + profile.withdrawal_balance + profile.commission_balance,
        'products_json':    products_json,
        'categories_json':  categories_json,
        # TODO: replace with your real WhatsApp channel link, or pull from settings.
        'whatsapp_link':    'https://chat.whatsapp.com/EhxvFC7VT6KLosE4Yv4ftJ',
    }
    return render(request, 'home.html', context)