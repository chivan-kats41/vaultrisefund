import logging
from datetime import date, timedelta
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from .models import InvestmentProduct, InvestmentCategory, UserInvestment
from .serializers import (
    InvestmentProductSerializer, InvestmentCategorySerializer,
    BuyInvestmentSerializer, UserInvestmentSerializer,
)
from .tasks import distribute_commissions

logger = logging.getLogger(__name__)


class ProductListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        category_slug = request.query_params.get('category')
        qs = InvestmentProduct.objects.filter(is_active=True).select_related('category')
        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        serializer = InvestmentProductSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)


class CategoryListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cats = InvestmentCategory.objects.filter(is_active=True)
        return Response(InvestmentCategorySerializer(cats, many=True).data)


class BuyInvestmentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = BuyInvestmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        product = serializer.validated_data['product']
        shares  = serializer.validated_data['shares']
        user    = request.user
        amount  = product.price * shares

        # VIP check
        if user.vip_level < product.vip_required:
            return Response({
                'success': False,
                'error': f'Requires VIP{product.vip_required}. You are VIP{user.vip_level}.',
            }, status=403)

        with transaction.atomic():
            from accounts.models import UserProfile
            locked_user = UserProfile.objects.select_for_update().get(pk=user.pk)

            if locked_user.balance < amount:
                return Response({
                    'success': False,
                    'insufficient_balance': True,
                    'error': (
                        f'Insufficient balance. '
                        f'Need UGX {amount:,.0f}, have UGX {locked_user.balance:,.0f}.'
                    ),
                }, status=400)

            locked_user.balance -= amount
            locked_user.save(update_fields=['balance'])

            today    = date.today()
            end_date = today + timedelta(days=product.duration_days)
            inv = UserInvestment.objects.create(
                user=locked_user,
                product=product,
                shares=shares,
                amount_paid=amount,
                start_date=today,
                end_date=end_date,
            )

        distribute_commissions.delay(inv.id)

        return Response({
            'success':      True,
            'message':      f'Successfully invested in {product.name}!',
            'investment_id': inv.id,
            'amount_paid':  str(amount),
            'new_balance':  str(locked_user.balance),
            'end_date':     str(end_date),
        }, status=201)


class MyInvestmentsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_filter = request.query_params.get('status', 'active')
        qs = UserInvestment.objects.filter(
            user=request.user
        ).select_related('product', 'product__category')
        if status_filter != 'all':
            qs = qs.filter(status=status_filter)
        return Response(
            UserInvestmentSerializer(qs, many=True, context={'request': request}).data
        )


class InvestmentHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UserInvestment.objects.filter(
            user=request.user
        ).select_related('product').prefetch_related('earning_logs')
        return Response(
            UserInvestmentSerializer(qs, many=True, context={'request': request}).data
        )