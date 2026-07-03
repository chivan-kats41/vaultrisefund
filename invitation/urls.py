from django.urls import path
from . import views
from .api_views import (
    ProductListAPIView, CategoryListAPIView,
    BuyInvestmentAPIView, MyInvestmentsAPIView,
    InvestmentHistoryAPIView,
)

urlpatterns = [
    # Page views
    path('',              views.team,  name='team'),
    path('teamMembers', views.level, name='team-members'),
    path('teamLevels',   views.level, name='teamLevels'),
    # Invitation API
    path('api/stats/',              views.get_invitation_stats,   name='invitation-stats'),
    path('api/members/',            views.get_team_members,       name='team-members-api'),
    path('api/commission-summary/', views.get_commission_summary, name='commission-summary'),

    # Investment API
    path('api/products/',           ProductListAPIView.as_view(),      name='product-list'),
    path('api/categories/',         CategoryListAPIView.as_view(),     name='category-list'),
    path('api/products/buy/',       BuyInvestmentAPIView.as_view(),    name='buy-investment'),
    path('api/my-investments/',     MyInvestmentsAPIView.as_view(),    name='my-investments'),
    path('api/investment-history/', InvestmentHistoryAPIView.as_view(),name='investment-history'),
]