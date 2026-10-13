from rest_framework.routers import DefaultRouter

from .views import LicitacaoViewSet

router = DefaultRouter()
router.register("licitacoes", LicitacaoViewSet, basename="licitacao")

urlpatterns = router.urls
