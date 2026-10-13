from drf_spectacular.utils import OpenApiParameter, extend_schema
import hashlib

from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from licitacoes.models import Licitacao
from licitacoes.serializers import LicitacaoListSerializer
from licitacoes.views import LicitacaoPagination

from . import matching
from .models import Alerta, Notificacao, PushSubscription
from .serializers import (
    AlertaSerializer, NotificacaoSerializer, PushSubscriptionSerializer,
)


@extend_schema(tags=["alertas"])
class AlertaViewSet(viewsets.ModelViewSet):
    """Filtros salvos do usuário autenticado."""

    serializer_class = AlertaSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LicitacaoPagination

    queryset = Alerta.objects.none()  # base p/ o schema; filtrado por usuário abaixo

    def get_queryset(self):
        return Alerta.objects.filter(usuario=self.request.user)

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    @extend_schema(
        summary="Licitações atuais que casam com o alerta",
        responses=LicitacaoListSerializer(many=True),
    )
    @action(detail=True, methods=["get"])
    def resultados(self, request, pk=None):
        alerta = self.get_object()
        qs = (
            matching.aplicar(Licitacao.objects.all(), alerta.filtros)
            .select_related("orgao", "fonte")
            .order_by("-data_publicacao", "-id")
        )
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(
            LicitacaoListSerializer(page, many=True).data
        )


@extend_schema(
    tags=["alertas"],
    parameters=[
        OpenApiParameter("lida", bool, description="Filtra por lidas/não lidas."),
        OpenApiParameter("alerta", int, description="ID do alerta."),
    ]
)
class NotificacaoViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Notificações geradas pelos alertas. PATCH {"lida": true} marca como lida."""

    serializer_class = NotificacaoSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LicitacaoPagination
    http_method_names = ["get", "patch", "post", "head", "options"]

    queryset = Notificacao.objects.none()  # base p/ o schema; filtrado por usuário abaixo

    def get_queryset(self):
        qs = (
            Notificacao.objects.filter(alerta__usuario=self.request.user)
            .select_related("alerta", "licitacao__orgao", "licitacao__fonte")
        )
        lida = self.request.query_params.get("lida")
        if lida is not None:
            qs = qs.filter(lida=lida.lower() in ("1", "true", "t", "yes"))
        alerta = self.request.query_params.get("alerta")
        if alerta and alerta.isdigit():
            qs = qs.filter(alerta_id=int(alerta))
        return qs

    @extend_schema(summary="Marcar todas as notificações como lidas", request=None)
    @action(detail=False, methods=["post"], url_path="marcar-todas-lidas")
    def marcar_todas_lidas(self, request):
        n = Notificacao.objects.filter(
            alerta__usuario=request.user, lida=False,
        ).update(lida=True)
        return Response({"atualizadas": n})


@extend_schema(tags=["push"], summary="Chave pública VAPID", responses={200: dict})
class PushPublicKeyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        chave = settings.VAPID_PUBLIC_KEY
        if not chave:
            return Response({"detail": "Push não configurado."}, status=503)
        return Response({"public_key": chave})


@extend_schema(tags=["push"])
class PushSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Registrar este dispositivo para push",
        request=PushSubscriptionSerializer, responses={201: None},
    )
    def post(self, request):
        ser = PushSubscriptionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        PushSubscription.objects.update_or_create(
            endpoint_hash=hashlib.sha256(d["endpoint"].encode()).hexdigest(),
            defaults={
                "usuario": request.user,
                "endpoint": d["endpoint"],
                "p256dh": d["keys"]["p256dh"],
                "auth": d["keys"]["auth"],
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
            },
        )
        return Response(status=status.HTTP_201_CREATED)

    @extend_schema(summary="Remover este dispositivo", request=PushSubscriptionSerializer, responses={204: None})
    def delete(self, request):
        endpoint = request.data.get("endpoint", "")
        PushSubscription.objects.filter(
            usuario=request.user,
            endpoint_hash=hashlib.sha256(endpoint.encode()).hexdigest(),
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
