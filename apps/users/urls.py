from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('self-exclusion/', views.self_exclusion_view, name='self_exclusion'),
    path('limits/', views.update_limits_view, name='update_limits'),
    path('api/dni-lookup/', views.dni_lookup_view, name='dni_lookup'),
]
