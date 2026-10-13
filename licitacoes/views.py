from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination

from .filters import LicitacaoFilter
from .models import Licitacao
from .serializers import LicitacaoDetailSerializer, LicitacaoListSerializer


class LicitacaoPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    list=extend_schema(summary="Buscar licitações", tags=["licitacoes"]),
    retrieve=extend_schema(summary="Detalhar licitação", tags=["licitacoes"]),
)
class LicitacaoViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta somente leitura de licitações, com filtros e paginação."""

    queryset = (
        Licitacao.objects.select_related("orgao", "fonte")
        .order_by("-data_publicacao", "-id")
    )
    filter_backends = [DjangoFilterBackend]
    filterset_class = LicitacaoFilter
    pagination_class = LicitacaoPagination

    def get_serializer_class(self):
        if self.action == "retrieve":
            return LicitacaoDetailSerializer
        return LicitacaoListSerializer
