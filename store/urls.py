# store/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.StoreView.as_view(), name='store'),
    path('my-investments/', views.MyInvestmentsView.as_view(), name='my_investments'),
]