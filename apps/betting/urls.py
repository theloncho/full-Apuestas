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
    path('bet/search/', views.bet_search, name='bet_search'),
    path('bet/history/json/', views.bet_history_json, name='bet_history_json'),
    path('api/bets/history/', views.bet_history_json, name='api_bet_history'),
    path('api/bets/open/', views.open_bets_json, name='api_open_bets'),
    path('bet/combined/place/', views.place_combined_bet, name='place_combined_bet'),
    path('bet/cashout-combined/<uuid:bet_id>/', views.cashout_combined_bet, name='cashout_combined_bet'),
]
