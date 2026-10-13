from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import (
    AlertaViewSet, NotificacaoViewSet, PushPublicKeyView, PushSubscriptionView,
)

router = DefaultRouter()
router.register("alertas", AlertaViewSet, basename="alerta")
router.register("notificacoes", NotificacaoViewSet, basename="notificacao")

urlpatterns = [
    path("push/public-key/", PushPublicKeyView.as_view(), name="push-public-key"),
    path("push/subscriptions/", PushSubscriptionView.as_view(), name="push-subscriptions"),
] + router.urls
