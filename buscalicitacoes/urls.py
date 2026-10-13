from django.contrib import admin
from django.urls import include, path
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser
from drf_spectacular.views import (
    SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView,
)

from core import views as core_views

_DOCS = {
    'authentication_classes': [SessionAuthentication],
    'permission_classes': [IsAdminUser],
}

urlpatterns = [
    path('', core_views.index, name='app'),
    path('sw.js', core_views.service_worker, name='pwa-sw'),
    path('manifest.webmanifest', core_views.manifest, name='pwa-manifest'),
    path('admin/', admin.site.urls),
    path('api/', include('licitacoes.urls')),
    path('api/', include('accounts.urls')),
    path('api/', include('alertas.urls')),
    # Documentação da API: só para quem está logado no /admin/ (staff).
    path('api/schema/', SpectacularAPIView.as_view(**_DOCS), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema', **_DOCS), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema', **_DOCS), name='redoc'),
]
