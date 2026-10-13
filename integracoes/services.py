"""
Camada que liga os adapters (puros) ao banco de dados.

executar_sync(fonte): roda o adapter da Fonte, faz upsert de Orgao/Licitacao
e registra tudo em SincronizacaoLog. Idempotente: rodar duas vezes sobre a
mesma janela não duplica nada (chave única fonte + id_externo).
"""
import logging
import traceback
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from licitacoes.models import Licitacao, Orgao

from .adapters import AdapterError, get_adapter
from .models import SincronizacaoLog

logger = logging.getLogger(__name__)

MAX_ERRO_CHARS = 20000


class SyncFalhou(AdapterError):
    """Nenhum item foi importado e houve erros. Task faz retry com backoff."""


def _aware(dt):
    return timezone.make_aware(dt) if dt else None


def _desde(fonte):
    """
    Início da janela incremental: último sync SUCESSO menos 1 dia de folga
    (a API filtra por data, sem hora). Syncs PARCIAL/ERRO não avançam a janela,
    então o que faltou é recoberto na execução seguinte.
    """
    ultimo = (
        fonte.logs.filter(status=SincronizacaoLog.Status.SUCESSO)
        .order_by("-iniciado_em").first()
    )
    if ultimo is None:
        return None
    return timezone.localtime(ultimo.iniciado_em).replace(tzinfo=None) - timedelta(days=1)


def salvar_licitacao(fonte, dto):
    """Upsert de Orgao + Licitacao. Retorna (licitacao, created)."""
    defaults = {
        "razao_social": dto.orgao.razao_social,
        "esfera": dto.orgao.esfera,
        "uf": dto.orgao.uf,
        "municipio": dto.orgao.municipio,
    }
    if dto.orgao.cnpj:
        orgao, criado = Orgao.objects.get_or_create(cnpj=dto.orgao.cnpj, defaults=defaults)
    else:
        # Fontes sem CNPJ (TCEs): identifica o órgão por nome + UF + município.
        # cnpj=None em get_or_create casaria com QUALQUER órgão sem CNPJ.
        orgao = Orgao.objects.filter(
            cnpj__isnull=True, razao_social=dto.orgao.razao_social,
            uf=dto.orgao.uf, municipio=dto.orgao.municipio,
        ).first()
        criado = orgao is None
        if criado:
            orgao = Orgao.objects.create(cnpj=None, **defaults)
    if not criado and orgao.razao_social != dto.orgao.razao_social:
        orgao.razao_social = dto.orgao.razao_social
        orgao.save(update_fields=["razao_social", "atualizado_em"])

    return Licitacao.objects.update_or_create(
        fonte=fonte,
        id_externo=dto.id_externo,
        defaults={
            "orgao": orgao,
            "numero": dto.numero,
            "modalidade": dto.modalidade,
            "objeto": dto.objeto,
            "valor_estimado": dto.valor_estimado,
            "data_publicacao": dto.data_publicacao,
            "data_abertura": _aware(dto.data_abertura),
            "data_encerramento_propostas": _aware(dto.data_encerramento_propostas),
            "status": dto.status,
            "link_original": dto.link_original,
            "uf": dto.uf,
            "municipio": dto.municipio,
        },
    )


def _finalizar(log, status, itens=0, erros=None):
    log.status = status
    log.finalizado_em = timezone.now()
    log.itens_importados = itens
    if erros:
        log.erro_detalhe = "\n".join(erros)[:MAX_ERRO_CHARS]
    log.save()


def executar_sync(fonte, forcar_completo=False):
    """
    Roda uma sincronização da fonte.
    `forcar_completo=True` ignora a janela incremental e refaz o backfill
    inteiro - útil para reclassificar registros após mudar o adapter (ex:
    correção de mapeamento de modalidade). Caro em requisições: use sob demanda.
    Retorna (log, ids_das_licitacoes_novas).
    Levanta SyncFalhou (retry) ou AdapterConfigError (sem retry) em caso de falha.
    """
    log = SincronizacaoLog.objects.create(fonte=fonte)
    try:
        adapter = get_adapter(fonte)
        novas_ids, atualizadas, ignoradas = [], 0, 0
        erros_item = []

        desde = None if forcar_completo else _desde(fonte)
        for raw in adapter.fetch(desde=desde):
            try:
                dto = adapter.normalize(raw)
            except Exception:
                logger.exception("normalize falhou (fonte=%s)", fonte.pk)
                ignoradas += 1
                continue
            if dto is None:
                ignoradas += 1
                continue
            try:
                with transaction.atomic():
                    licitacao, criada = salvar_licitacao(fonte, dto)
            except Exception as exc:
                logger.exception("Falha ao salvar %s (fonte=%s)", dto.id_externo, fonte.pk)
                erros_item.append(f"salvar {dto.id_externo}: {exc}")
                continue
            if criada:
                novas_ids.append(licitacao.pk)
            else:
                atualizadas += 1

        erros = list(adapter.erros) + erros_item
        importados = len(novas_ids) + atualizadas
        logger.info(
            "sync fonte=%s novas=%d atualizadas=%d ignoradas=%d erros=%d",
            fonte.pk, len(novas_ids), atualizadas, ignoradas, len(erros),
        )

        if erros and importados == 0:
            _finalizar(log, SincronizacaoLog.Status.ERRO, 0, erros)
            raise SyncFalhou(f"Fonte {fonte.nome}: nenhum item importado. {erros[0]}")
        if erros:
            _finalizar(log, SincronizacaoLog.Status.PARCIAL, importados, erros)
        else:
            _finalizar(log, SincronizacaoLog.Status.SUCESSO, importados)
        return log, novas_ids

    except Exception:
        if log.finalizado_em is None:  # falha inesperada / config inválida
            _finalizar(log, SincronizacaoLog.Status.ERRO, 0, [traceback.format_exc()])
        raise
