import logging
from datetime import date, timedelta
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from category.models import category as Category
from store.models import InvestmentProduct, UserInvestment
from .serializers import (
    InvestmentProductSerializer,
    InvestmentCategorySerializer,
    BuyInvestmentSerializer,
    UserInvestmentSerializer,
)
from .tasks import distribute_commissions

logger = logging.getLogger(__name__)


def get_profile(request):
    from users.models import UserProfile
    return UserProfile.objects.get(user=request.user)


class ProductListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        category_slug = request.query_params.get('category')
        qs = InvestmentProduct.objects.filter(is_active=True).select_related('category')
        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        return Response(
            InvestmentProductSerializer(qs, many=True, context={'request': request}).data
        )


class CategoryListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cats = Category.objects.all()
        return Response(InvestmentCategorySerializer(cats, many=True).data)


class BuyInvestmentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = BuyInvestmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        product = serializer.validated_data['product']
        shares  = serializer.validated_data['shares']

        try:
            profile = get_profile(request)
        except Exception:
            return Response({'success': False, 'error': 'User profile not found.'}, status=404)

        if profile.vip_level < product.vip_required:
            return Response({
                'success': False,
                'error': (
                    f'This product requires VIP{product.vip_required}. '
                    f'You are VIP{profile.vip_level}.'
                ),
            }, status=403)

        amount = product.price * shares

        with transaction.atomic():
            from users.models import UserProfile
            lp = UserProfile.objects.select_for_update().get(pk=profile.pk)

            # ✅ Check combined recharge + withdrawal balance
            total_available = lp.recharge_balance + lp.withdrawal_balance
            if total_available < amount:
                return Response({
                    'success':             False,
                    'insufficient_balance': True,
                    'error': (
                        f'Insufficient balance. '
                        f'Need UGX {amount:,.0f}, '
                        f'have UGX {total_available:,.0f}.'
                    ),
                }, status=400)

            # ✅ Deduct recharge_balance first, then withdrawal_balance
            if lp.recharge_balance >= amount:
                lp.recharge_balance -= amount
            else:
                remainder = amount - lp.recharge_balance
                lp.recharge_balance    = 0
                lp.withdrawal_balance -= remainder

            lp.save(update_fields=['recharge_balance', 'withdrawal_balance'])

            today    = date.today()
            end_date = today + timedelta(days=product.duration_days)
            inv = UserInvestment.objects.create(
                user        = lp,
                product     = product,
                shares      = shares,
                amount_paid = amount,
                start_date  = today,
                end_date    = end_date,
            )

        distribute_commissions.delay(inv.id)

        logger.info(
            f"Investment: user={request.user.username}, "
            f"product={product.name}, shares={shares}, amount={amount}"
        )

        new_balance = lp.recharge_balance + lp.withdrawal_balance
        return Response({
            'success':       True,
            'message':       f'Successfully invested in {product.name}!',
            'investment_id': inv.id,
            'amount_paid':   str(amount),
            'new_balance':   str(new_balance),
            'end_date':      str(end_date),
        }, status=201)


class MyInvestmentsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = get_profile(request)
        except Exception:
            return Response({'error': 'User profile not found.'}, status=404)

        status_filter = request.query_params.get('status', 'active')
        qs = UserInvestment.objects.filter(
            user=profile
        ).select_related('product', 'product__category')

        if status_filter != 'all':
            qs = qs.filter(status=status_filter)

        return Response(
            UserInvestmentSerializer(qs, many=True, context={'request': request}).data
        )


class InvestmentHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = get_profile(request)
        except Exception:
            return Response({'error': 'User profile not found.'}, status=404)

        qs = UserInvestment.objects.filter(
            user=profile
        ).select_related('product').prefetch_related('earning_logs')

        return Response(
            UserInvestmentSerializer(qs, many=True, context={'request': request}).data
        )