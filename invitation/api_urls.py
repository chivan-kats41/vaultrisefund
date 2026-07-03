from django.urls import path
from .api_views import (
    ProductListAPIView, CategoryListAPIView,
    BuyInvestmentAPIView, MyInvestmentsAPIView,
    InvestmentHistoryAPIView,
)

urlpatterns = [
    path('', ProductListAPIView.as_view(), name='api-products'),
    path('categories/', CategoryListAPIView.as_view(), name='api-categories'),
    path('buy/', BuyInvestmentAPIView.as_view(), name='api-buy'),
    path('my/', MyInvestmentsAPIView.as_view(), name='api-my-investments'),
    path('history/', InvestmentHistoryAPIView.as_view(), name='api-investment-history'),
]