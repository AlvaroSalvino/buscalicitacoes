import base64

from cryptography.hazmat.primitives import serialization
from django.core.management.base import BaseCommand
from py_vapid import Vapid


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Gera um par de chaves VAPID para Web Push (copie para o .env)."

    def handle(self, *args, **opts):
        v = Vapid()
        v.generate_keys()
        privada = v.private_key.private_numbers().private_value.to_bytes(32, "big")
        publica = v.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint,
        )
        self.stdout.write(f"VAPID_PUBLIC_KEY={_b64(publica)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={_b64(privada)}")
        self.stdout.write("VAPID_CLAIMS_EMAIL=voce@exemplo.com")
