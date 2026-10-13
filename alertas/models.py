from django.conf import settings
from django.db import models


class Alerta(models.Model):
    """
    Filtro salvo de um usuário. `filtros` guarda os mesmos parâmetros aceitos
    por GET /api/licitacoes/ (ex: {"q": "notebook", "uf": "SP,RJ",
    "valor_max": "100000"}), para que busca e alerta usem a mesma lógica
    (licitacoes.filters.LicitacaoFilter).
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="alertas", on_delete=models.CASCADE,
    )
    nome = models.CharField(max_length=150)
    filtros = models.JSONField(default=dict)
    ativo = models.BooleanField(default=True)
    notificar_email = models.BooleanField(default=False)
    notificar_push = models.BooleanField(
        default=True, help_text="Notificação push nos dispositivos do usuário.",
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["ativo"])]

    def __str__(self):
        return f"{self.nome} ({self.usuario})"


class Notificacao(models.Model):
    """Licitação que casou com um Alerta. Uma por par (alerta, licitação)."""

    alerta = models.ForeignKey(
        Alerta, related_name="notificacoes", on_delete=models.CASCADE,
    )
    licitacao = models.ForeignKey(
        "licitacoes.Licitacao", related_name="notificacoes", on_delete=models.CASCADE,
    )
    lida = models.BooleanField(default=False)
    email_enviado = models.BooleanField(default=False)
    push_enviado = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["alerta", "licitacao"], name="uniq_notificacao_alerta_licitacao",
            ),
        ]

    def __str__(self):
        return f"{self.alerta_id} -> {self.licitacao_id}"


class PushSubscription(models.Model):
    """Dispositivo/navegador de um usuário inscrito em Web Push."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="push_subscriptions",
        on_delete=models.CASCADE,
    )
    endpoint = models.TextField()
    # sha256(endpoint): índice único curto (compatível com MySQL).
    endpoint_hash = models.CharField(max_length=64, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario} ({self.endpoint[:40]}...)"
