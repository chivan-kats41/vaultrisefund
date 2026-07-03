# services/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('',              views.services,      name='services'),
    path('send/',         views.send_message,  name='support_send'),
    path('poll/',         views.poll_messages, name='support_poll'),
]