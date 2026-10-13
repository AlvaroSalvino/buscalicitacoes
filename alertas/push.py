"""Envio de Web Push (VAPID) para as inscrições de um usuário."""
import json
import logging

from django.conf import settings
from pywebpush import WebPushException, webpush

from .models import PushSubscription

logger = logging.getLogger(__name__)


def configurado():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def enviar(subscription, payload):
    """
    Envia `payload` (dict) a uma inscrição. Retorna True se entregue ao serviço
    de push. Inscrições expiradas (404/410) são removidas.
    """
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{settings.VAPID_CLAIMS_EMAIL}"},
            ttl=60 * 60 * 24,
        )
        return True
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            PushSubscription.objects.filter(pk=subscription.pk).delete()
        else:
            logger.warning("Falha no push (sub=%s, status=%s): %s", subscription.pk, status, exc)
        return False
    except Exception:
        logger.exception("Erro inesperado no push (sub=%s)", subscription.pk)
        return False
