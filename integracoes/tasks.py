import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .adapters import AdapterError
from .models import Fonte, SincronizacaoLog
from .services import executar_sync

logger = logging.getLogger(__name__)

# Um log EM_EXECUCAO mais velho que isso é tratado como órfão (worker caiu).
LIMITE_EXECUCAO = timedelta(hours=2)


@shared_task(
    bind=True,
    autoretry_for=(AdapterError,),  # AdapterConfigError NÃO faz retry
    retry_backoff=60,
    retry_backoff_max=1800,
    retry_jitter=True,
    max_retries=3,
)
def sync_fonte(self, fonte_id):
    """Sincroniza UMA fonte. Isolada: erro aqui não afeta as outras fontes."""
    try:
        fonte = Fonte.objects.get(pk=fonte_id)
    except Fonte.DoesNotExist:
        logger.warning("sync_fonte: fonte %s não existe", fonte_id)
        return {"status": "fonte_inexistente"}
    if not fonte.ativo:
        return {"status": "inativa"}

    em_andamento = fonte.logs.filter(
        status=SincronizacaoLog.Status.EM_EXECUCAO,
        iniciado_em__gte=timezone.now() - LIMITE_EXECUCAO,
    ).exists()
    if em_andamento:
        return {"status": "ja_em_execucao"}

    log, novas_ids = executar_sync(fonte)

    # Fase 7: matching dos alertas sobre as licitações recém-importadas.
    # Falha ao enfileirar (ex: broker fora) não deve invalidar o sync já gravado.
    if novas_ids:
        try:
            from alertas.tasks import match_licitacoes

            match_licitacoes.delay(novas_ids)
        except Exception:
            logger.exception("Falha ao enfileirar match_licitacoes (fonte=%s)", fonte_id)

    return {"status": log.status, "log_id": log.pk, "novas": len(novas_ids)}


@shared_task
def agendar_syncs():
    """
    Roda a cada minuto (Celery beat). Enfileira sync_fonte para cada fonte ativa
    cujo intervalo_sync_minutos já venceu. Se a fila estiver atrasada pode
    enfileirar duas vezes; é inofensivo (o upsert é idempotente).
    """
    agora = timezone.now()

    SincronizacaoLog.objects.filter(
        status=SincronizacaoLog.Status.EM_EXECUCAO,
        iniciado_em__lt=agora - LIMITE_EXECUCAO,
    ).update(
        status=SincronizacaoLog.Status.ERRO,
        finalizado_em=agora,
        erro_detalhe="Execução interrompida (worker parou antes de finalizar).",
    )

    disparadas = []
    for fonte in Fonte.objects.filter(ativo=True):
        ultimo = fonte.logs.order_by("-iniciado_em").first()
        vencido = (
            ultimo is None
            or ultimo.iniciado_em + timedelta(minutes=fonte.intervalo_sync_minutos) <= agora
        )
        if vencido:
            sync_fonte.delay(fonte.pk)
            disparadas.append(fonte.pk)
    return disparadas
