from django.db import models


class Fonte(models.Model):
    """
    Uma fonte de dados de licitações (PNCP, portal estadual, municipal etc).

    `tipo_adapter` é a chave usada no registry de adapters em código
    (ex: ADAPTERS = {"pncp": PNCPAdapter, ...}) - não é um enum fixo aqui
    porque novos adapters sao adicionados no codigo, e o registry e a
    fonte da verdade sobre quais chaves existem.
    """

    nome = models.CharField(max_length=150)
    tipo_adapter = models.CharField(
        max_length=50,
        help_text="Chave do adapter no registry (ex: 'pncp').",
    )
    ativo = models.BooleanField(default=True)
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuracao especifica da fonte (UF, endpoint, credenciais etc).",
    )
    intervalo_sync_minutos = models.PositiveIntegerField(default=60)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        status = "ativa" if self.ativo else "inativa"
        return f"{self.nome} ({self.tipo_adapter}, {status})"


class SincronizacaoLog(models.Model):
    """Registro de uma execucao de sync de uma Fonte, para observabilidade."""

    class Status(models.TextChoices):
        EM_EXECUCAO = "em_execucao", "Em execução"
        SUCESSO = "sucesso", "Sucesso"
        ERRO = "erro", "Erro"
        PARCIAL = "parcial", "Parcial (com erros)"

    fonte = models.ForeignKey(
        Fonte, related_name="logs", on_delete=models.CASCADE,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.EM_EXECUCAO,
    )
    iniciado_em = models.DateTimeField(auto_now_add=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    itens_importados = models.PositiveIntegerField(default=0)
    erro_detalhe = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-iniciado_em"]
        indexes = [
            models.Index(fields=["fonte", "-iniciado_em"]),
        ]

    def __str__(self):
        return f"{self.fonte.nome} - {self.iniciado_em:%Y-%m-%d %H:%M} ({self.status})"
