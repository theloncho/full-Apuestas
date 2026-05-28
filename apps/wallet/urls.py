from django.urls import path
from . import views

app_name = 'wallet'

urlpatterns = [
    path('', views.wallet_view, name='wallet'),
    path('deposit/', views.deposit_view, name='deposit'),
    path('withdraw/', views.withdraw_view, name='withdraw'),
    path('balance/', views.balance_api, name='balance'),
]
