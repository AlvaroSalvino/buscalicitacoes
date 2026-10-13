import logging
from collections import defaultdict

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from licitacoes.models import Licitacao

from . import matching, push
from .models import Alerta, Notificacao

logger = logging.getLogger(__name__)

MAX_ITENS_EMAIL = 20
LOTE = 500


@shared_task
def match_licitacoes(licitacao_ids):
    """
    Confronta licitações (normalmente as recém-importadas por um sync) com os
    alertas ativos e grava uma Notificacao por par novo. Idempotente: a
    constraint única (alerta, licitação) evita duplicar. Dispara e-mails dos
    alertas com notificar_email.
    """
    if not licitacao_ids:
        return {"notificacoes": 0}

    alertas = list(Alerta.objects.filter(ativo=True).select_related("usuario"))
    criadas = 0
    # Em lotes: o backfill inicial traz dezenas de milhares de ids.
    for i in range(0, len(licitacao_ids), LOTE):
        base = Licitacao.objects.filter(pk__in=licitacao_ids[i:i + LOTE])
        for alerta in alertas:
            ids = list(matching.aplicar(base, alerta.filtros).values_list("pk", flat=True))
            if not ids:
                continue
            existentes = set(
                Notificacao.objects.filter(alerta=alerta, licitacao_id__in=ids)
                .values_list("licitacao_id", flat=True)
            )
            novas = [
                Notificacao(alerta=alerta, licitacao_id=j)
                for j in ids if j not in existentes
            ]
            Notificacao.objects.bulk_create(novas, ignore_conflicts=True)
            criadas += len(novas)

    enviar_emails_pendentes.delay()
    enviar_push_pendentes.delay()
    return {"notificacoes": criadas}


@shared_task
def enviar_emails_pendentes():
    """Um e-mail resumo por usuário/alerta com as notificações ainda não enviadas."""
    pendentes = (
        Notificacao.objects.filter(
            email_enviado=False, alerta__ativo=True, alerta__notificar_email=True,
        )
        .exclude(alerta__usuario__email="")
        .select_related("alerta__usuario", "licitacao__orgao")
    )
    por_alerta = defaultdict(list)
    for n in pendentes:
        por_alerta[n.alerta].append(n)

    enviados = 0
    for alerta, notifs in por_alerta.items():
        linhas = [
            f"- {n.licitacao.objeto[:120]} ({n.licitacao.orgao.razao_social}, "
            f"{n.licitacao.uf or '-'})"
            + (f"\n  {n.licitacao.link_original}" if n.licitacao.link_original else "")
            for n in notifs[:MAX_ITENS_EMAIL]
        ]
        if len(notifs) > MAX_ITENS_EMAIL:
            linhas.append(f"... e mais {len(notifs) - MAX_ITENS_EMAIL}.")
        try:
            send_mail(
                subject=f"[Licitações] {len(notifs)} nova(s) para \"{alerta.nome}\"",
                message="\n".join(linhas),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[alerta.usuario.email],
            )
        except Exception:
            logger.exception("Falha ao enviar e-mail do alerta %s", alerta.pk)
            continue
        Notificacao.objects.filter(pk__in=[n.pk for n in notifs]).update(email_enviado=True)
        enviados += 1
    return {"emails": enviados}


@shared_task
def enviar_push_pendentes():
    """
    Uma notificação push por alerta com novidades ainda não enviadas, para
    todos os dispositivos inscritos do dono do alerta.
    """
    if not push.configurado():
        return {"push": 0, "motivo": "vapid_nao_configurado"}

    pendentes = (
        Notificacao.objects.filter(
            push_enviado=False, alerta__ativo=True, alerta__notificar_push=True,
            alerta__usuario__push_subscriptions__isnull=False,
        )
        .select_related("alerta", "licitacao__orgao")
        .distinct()
    )
    por_alerta = defaultdict(list)
    for n in pendentes:
        por_alerta[n.alerta].append(n)

    enviados = 0
    for alerta, notifs in por_alerta.items():
        total = len(notifs)
        if total == 1:
            lic = notifs[0].licitacao
            corpo = f"{lic.orgao.razao_social}: {lic.objeto[:100]}"
            url = f"/#/licitacao/{lic.pk}"
        else:
            corpo = f"{total} novas licitações encontradas."
            url = f"/#/notificacoes?alerta={alerta.pk}"
        payload = {
            "title": alerta.nome,
            "body": corpo,
            "url": url,
            "tag": f"alerta-{alerta.pk}",
        }
        entregue = False
        for sub in list(alerta.usuario.push_subscriptions.all()):
            entregue = push.enviar(sub, payload) or entregue
        # Marca como enviada mesmo sem entrega (ex: inscrição expirada), para
        # não reenviar indefinidamente; o usuário ainda vê no app.
        Notificacao.objects.filter(pk__in=[n.pk for n in notifs]).update(push_enviado=True)
        enviados += 1 if entregue else 0
    return {"push": enviados}
