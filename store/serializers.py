from rest_framework import serializers
from .models import InvestmentProduct, InvestmentCategory, UserInvestment, DailyEarningLog


class InvestmentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = InvestmentCategory
        fields = ['id', 'name', 'slug', 'order']


class InvestmentProductSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField()

    class Meta:
        model  = InvestmentProduct
        fields = [
            'id', 'name', 'category_name', 'image',
            'vip_required', 'price', 'duration_days',
            'daily_earning', 'total_return', 'max_shares',
        ]


class BuyInvestmentSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    shares     = serializers.IntegerField(min_value=1)

    def validate(self, data):
        try:
            product = InvestmentProduct.objects.get(id=data['product_id'], is_active=True)
        except InvestmentProduct.DoesNotExist:
            raise serializers.ValidationError('Product not found or inactive.')

        if data['shares'] > product.max_shares:
            raise serializers.ValidationError(
                f'Maximum {product.max_shares} shares allowed for this product.'
            )
        data['product'] = product
        return data


class DailyEarningLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DailyEarningLog
        fields = ['id', 'amount', 'date', 'credited_at']


class UserInvestmentSerializer(serializers.ModelSerializer):
    product_name    = serializers.CharField(source='product.name', read_only=True)
    product_image   = serializers.SerializerMethodField()
    daily_earning   = serializers.ReadOnlyField()
    progress        = serializers.IntegerField(source='progress_percent', read_only=True)
    days_remaining  = serializers.ReadOnlyField()
    earning_logs    = DailyEarningLogSerializer(many=True, read_only=True)

    class Meta:
        model  = UserInvestment
        fields = [
            'id', 'product_name', 'product_image', 'shares',
            'amount_paid', 'start_date', 'end_date',
            'status', 'total_earned', 'last_payout',
            'daily_earning', 'progress', 'days_remaining',
            'earning_logs', 'created_at',
        ]

    def get_product_image(self, obj):
        if obj.product.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.product.image.url)
            return obj.product.image.url
        return ''