import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Convite(models.Model):
    """
    Convite de cadastro. O app é fechado: só um superusuário cria convites e
    só quem tem o link (token) consegue criar conta. Guardamos apenas o hash
    do token; o link em texto só existe no e-mail e na resposta da criação.
    """

    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="convites_enviados",
        on_delete=models.CASCADE,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField()
    usado_em = models.DateTimeField(null=True, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="convite_origem",
        null=True, blank=True, on_delete=models.SET_NULL,
    )

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.email} ({self.status})"

    @classmethod
    def criar(cls, email, criado_por):
        """Retorna (convite, token_em_texto)."""
        token = secrets.token_urlsafe(32)
        dias = getattr(settings, "CONVITE_VALIDADE_DIAS", 7)
        convite = cls.objects.create(
            email=email.strip().lower(), criado_por=criado_por,
            token_hash=hash_token(token),
            expira_em=timezone.now() + timedelta(days=dias),
        )
        return convite, token

    @classmethod
    def pendente_por_token(cls, token):
        if not token:
            return None
        return cls.objects.filter(
            token_hash=hash_token(token), usado_em__isnull=True,
            expira_em__gt=timezone.now(),
        ).first()

    @property
    def status(self):
        if self.usado_em:
            return "usado"
        if self.expira_em <= timezone.now():
            return "expirado"
        return "pendente"
