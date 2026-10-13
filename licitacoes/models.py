from django.db import models

from .textos import texto_busca


class Orgao(models.Model):
    """Órgão público que publica licitações (federal, estadual ou municipal)."""

    class Esfera(models.TextChoices):
        FEDERAL = "federal", "Federal"
        ESTADUAL = "estadual", "Estadual"
        MUNICIPAL = "municipal", "Municipal"

    cnpj = models.CharField(
        max_length=18, unique=True, null=True, blank=True,
        help_text="Formato 00.000.000/0000-00. Pode não vir preenchido em algumas fontes.",
    )
    razao_social = models.CharField(max_length=255)
    esfera = models.CharField(max_length=20, choices=Esfera.choices)
    uf = models.CharField(max_length=2)
    municipio = models.CharField(max_length=150, blank=True, default="")

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["razao_social"]
        indexes = [
            models.Index(fields=["uf"]),
            models.Index(fields=["esfera"]),
        ]

    def __str__(self):
        return self.razao_social


class Licitacao(models.Model):
    """Uma licitação importada de uma Fonte, vinculada a um Órgão."""

    class Modalidade(models.TextChoices):
        PREGAO = "pregao", "Pregão"
        CONCORRENCIA = "concorrencia", "Concorrência"
        CONCURSO = "concurso", "Concurso"
        LEILAO = "leilao", "Leilão"
        DIALOGO_COMPETITIVO = "dialogo_competitivo", "Diálogo Competitivo"
        DISPENSA = "dispensa", "Dispensa de Licitação"
        INEXIGIBILIDADE = "inexigibilidade", "Inexigibilidade"
        CONVITE = "convite", "Convite"
        TOMADA_PRECOS = "tomada_precos", "Tomada de Preços"
        CREDENCIAMENTO = "credenciamento", "Credenciamento"
        PRE_QUALIFICACAO = "pre_qualificacao", "Pré-qualificação"
        MANIFESTACAO_INTERESSE = "manifestacao_interesse", "Manifestação de Interesse"
        OUTRA = "outra", "Outra"

    class Status(models.TextChoices):
        PUBLICADA = "publicada", "Publicada"
        ABERTA = "aberta", "Aberta para propostas"
        EM_JULGAMENTO = "em_julgamento", "Em julgamento"
        HOMOLOGADA = "homologada", "Homologada"
        SUSPENSA = "suspensa", "Suspensa"
        REVOGADA = "revogada", "Revogada"
        CANCELADA = "cancelada", "Cancelada"
        ENCERRADA = "encerrada", "Encerrada"

    orgao = models.ForeignKey(
        Orgao, related_name="licitacoes", on_delete=models.PROTECT,
    )
    # String reference evita import circular entre os apps licitacoes <-> integracoes.
    fonte = models.ForeignKey(
        "integracoes.Fonte", related_name="licitacoes", on_delete=models.PROTECT,
    )
    id_externo = models.CharField(
        max_length=100,
        help_text="Identificador do registro na fonte de origem.",
    )
    numero = models.CharField(max_length=50, blank=True, default="")
    modalidade = models.CharField(
        max_length=30, choices=Modalidade.choices, default=Modalidade.OUTRA,
    )
    objeto = models.TextField()
    valor_estimado = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
    )
    data_publicacao = models.DateField(null=True, blank=True)
    # Início do recebimento de propostas.
    data_abertura = models.DateTimeField(null=True, blank=True)
    # Fim do recebimento de propostas (base do filtro de licitações "abertas").
    data_encerramento_propostas = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PUBLICADA,
    )
    # Localização da licitação (unidade compradora). Fica na própria licitação
    # porque um órgão federal pode ter unidades em várias UFs.
    uf = models.CharField(max_length=2, blank=True, default="")
    municipio = models.CharField(max_length=150, blank=True, default="")
    link_original = models.URLField(max_length=500, blank=True, default="")

    # Objeto + nome do órgão, sem acento/caixa/pontuação. Mantido em save();
    # é o que a busca por palavra-chave consulta (o LIKE do SQLite não ignora
    # acentos nem caixa fora do ASCII).
    texto_busca = models.TextField(blank=True, default="", editable=False)

    # Permite linkar duplicatas da mesma licitação encontradas em portais
    # diferentes (ex: mesma licitação no PNCP e num portal estadual).
    licitacao_matriz = models.ForeignKey(
        "self", related_name="duplicatas", null=True, blank=True,
        on_delete=models.SET_NULL,
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_publicacao", "-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["fonte", "id_externo"],
                name="uniq_licitacao_fonte_id_externo",
            ),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["modalidade"]),
            models.Index(fields=["data_abertura"]),
            models.Index(fields=["data_encerramento_propostas"]),
            models.Index(fields=["uf"]),
        ]

    def save(self, *args, **kwargs):
        self.texto_busca = texto_busca(self.objeto, self.orgao.razao_social)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"texto_busca"}
        super().save(*args, **kwargs)

    def __str__(self):
        identificador = self.numero or self.id_externo
        return f"{identificador} - {self.orgao.razao_social}"
