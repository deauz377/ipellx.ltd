from django.urls import path
from . import views_public

app_name = 'pay'

urlpatterns = [
    path('<str:token>/', views_public.pay, name='pay'),
    path('<str:token>/status/', views_public.pay_status, name='pay_status'),
]
