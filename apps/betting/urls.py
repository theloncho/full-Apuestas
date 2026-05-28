from django.urls import path
from . import views

app_name = 'betting'

urlpatterns = [
    path('', views.event_list, name='event_list'),
    path('event/<int:event_id>/', views.event_detail, name='event_detail'),
    path('bet/form/<int:selection_id>/', views.place_bet_form, name='place_bet_form'),
    path('bet/place/', views.place_bet, name='place_bet'),
    path('bet/history/', views.bet_history, name='bet_history'),
    path('bet/cashout/<uuid:bet_id>/', views.cashout_bet, name='cashout_bet'),
]
