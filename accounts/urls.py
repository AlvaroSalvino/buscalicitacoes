from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ConviteDetailView, ConviteListCreateView, ConviteValidarView, LoginView,
    MeView, RegisterView,
)

urlpatterns = [
    path("auth/token/", LoginView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    # Cadastro só com convite.
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/convites/validar/", ConviteValidarView.as_view(), name="convite-validar"),
    path("auth/convites/", ConviteListCreateView.as_view(), name="convite-list"),
    path("auth/convites/<int:pk>/", ConviteDetailView.as_view(), name="convite-detail"),
]
