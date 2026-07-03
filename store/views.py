import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from category.models import category as Category
from .models import InvestmentProduct, UserInvestment


@method_decorator(login_required, name='dispatch')
class StoreView(View):
    def get(self, request):
        products   = InvestmentProduct.objects.filter(is_active=True).select_related('category')
        categories = Category.objects.all()

        products_json   = json.dumps([p.as_dict() for p in products])
        categories_json = json.dumps([
            {'id': c.id, 'name': c.category_name, 'slug': c.slug}
            for c in categories
        ])
        return render(request, 'store/store.html', {
            'products_json':   products_json,
            'categories_json': categories_json,
            'categories':      categories,
        })


@method_decorator(login_required, name='dispatch')
class MyInvestmentsView(View):
    def get(self, request):
        active    = UserInvestment.objects.filter(
                        user=request.user, status='active'
                    ).select_related('product', 'product__category')
        completed = UserInvestment.objects.filter(
                        user=request.user, status='completed'
                    ).select_related('product', 'product__category')
        return render(request, 'store/my_investments.html', {
            'active':    active,
            'completed': completed,
        })