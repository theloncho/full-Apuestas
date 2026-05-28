from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    # Vistas web
    path('', include('apps.betting.urls')),
    path('users/', include(('apps.users.urls', 'users'), namespace='users')),
    path('wallet/', include(('apps.wallet.urls', 'wallet'), namespace='wallet')),
    path('dashboard/', include(('apps.dashboard.urls', 'dashboard'), namespace='dashboard')),
    # API REST
    path('api/', include(('apps.betting.api_urls', 'betting-api'), namespace='betting-api')),
    path('api/wallet/', include(('apps.wallet.api_urls', 'wallet-api'), namespace='wallet-api')),
    # OpenAPI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
