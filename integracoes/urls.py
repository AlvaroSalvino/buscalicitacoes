from django.urls import path

from .views import FonteStatusView, FonteSincronizarView

urlpatterns = [
    path("fontes/status/", FonteStatusView.as_view(), name="fonte-status"),
    path("fontes/<int:pk>/sincronizar/", FonteSincronizarView.as_view(), name="fonte-sincronizar"),
]
