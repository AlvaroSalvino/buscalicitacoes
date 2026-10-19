from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsSuperuser

from .models import Fonte, SincronizacaoLog
from .tasks import sync_fonte


def _iso(dt):
    return dt.isoformat() if dt else None


def _atrasada(fonte, ultimo_sucesso, agora):
    """Fonte ativa sem sucesso há mais de 3 intervalos (mínimo 6 h)."""
    if not fonte.ativo:
        return False
    limite = max(timedelta(minutes=fonte.intervalo_sync_minutos * 3), timedelta(hours=6))
    referencia = ultimo_sucesso.iniciado_em if ultimo_sucesso else fonte.criado_em
    return agora - referencia > limite


@extend_schema(tags=["fontes"], summary="Situação da atualização automática (superusuário)",
               responses={200: dict})
class FonteStatusView(APIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        agora = timezone.now()
        totais = dict(
            Fonte.objects.annotate(n=Count("licitacoes")).values_list("id", "n")
        )
        itens = []
        for f in Fonte.objects.order_by("id"):
            logs = f.logs.order_by("-iniciado_em")
            ultimo = logs.first()
            sucesso = logs.filter(status=SincronizacaoLog.Status.SUCESSO).first()
            proxima = None
            if f.ativo and ultimo:
                proxima = ultimo.iniciado_em + timedelta(minutes=f.intervalo_sync_minutos)
            itens.append({
                "id": f.id, "nome": f.nome, "tipo": f.tipo_adapter, "ativo": f.ativo,
                "intervalo_minutos": f.intervalo_sync_minutos,
                "total_licitacoes": totais.get(f.id, 0),
                "ultimo": None if not ultimo else {
                    "status": ultimo.status,
                    "iniciado_em": _iso(ultimo.iniciado_em),
                    "finalizado_em": _iso(ultimo.finalizado_em),
                    "itens": ultimo.itens_importados,
                    "erro": (ultimo.erro_detalhe or "")[:300],
                },
                "ultimo_sucesso": _iso(sucesso.iniciado_em) if sucesso else None,
                "proxima_em": _iso(proxima),
                "atrasada": _atrasada(f, sucesso, agora),
            })
        return Response(itens)


@extend_schema(tags=["fontes"], summary="Sincronizar uma fonte agora (superusuário)",
               request=None, responses={202: dict})
class FonteSincronizarView(APIView):
    permission_classes = [IsSuperuser]

    def post(self, request, pk):
        fonte = Fonte.objects.filter(pk=pk).first()
        if fonte is None:
            return Response({"detail": "Fonte não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        try:
            sync_fonte.delay(fonte.pk)
        except Exception:
            return Response(
                {"detail": "Não foi possível enfileirar: o Redis/Celery está indisponível."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Sincronização enfileirada."}, status=status.HTTP_202_ACCEPTED)
