from django.db.models import Q
from django.utils import timezone
from django_filters import rest_framework as filters

from .models import Licitacao
from .textos import condicao_termo, normalizar

MAX_PALAVRAS = 30       # palavras-chave por busca/alerta
MAX_TAMANHO_PALAVRA = 60


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """Aceita lista separada por vírgula (?uf=SP,RJ)."""


class LicitacaoFilter(filters.FilterSet):
    q = filters.CharFilter(
        method="filtrar_q",
        help_text=(
            "Palavra-chave, sem diferenciar acento/maiúsculas. Separada por "
            "espaço: TODAS as palavras precisam aparecer. Separada por vírgula: "
            "QUALQUER uma das alternativas (ex: 'tv, marketing digital, vídeo')."
        ),
    )
    palavras = CharInFilter(
        method="filtrar_palavras",
        help_text=(
            "Várias palavras-chave separadas por vírgula. Casa se QUALQUER uma "
            "aparecer no objeto ou no nome do órgão. Um termo com espaços é "
            "tratado como frase (ex: 'material de limpeza,notebook')."
        ),
    )
    uf = CharInFilter(method="filtrar_uf", help_text="UF(s), ex: SP,RJ.")
    municipio = filters.CharFilter(lookup_expr="icontains")
    modalidade = CharInFilter(
        field_name="modalidade", lookup_expr="in",
        help_text="Modalidade(s), ex: pregao,dispensa.",
    )
    status = CharInFilter(
        field_name="status", lookup_expr="in",
        help_text="Status, ex: aberta,publicada.",
    )
    orgao = filters.CharFilter(
        field_name="orgao__razao_social", lookup_expr="icontains",
        help_text="Parte do nome do órgão.",
    )
    cnpj = filters.CharFilter(method="filtrar_cnpj", help_text="CNPJ do órgão.")
    fonte = filters.NumberFilter(field_name="fonte_id")

    valor_min = filters.NumberFilter(field_name="valor_estimado", lookup_expr="gte")
    valor_max = filters.NumberFilter(field_name="valor_estimado", lookup_expr="lte")

    publicacao_de = filters.DateFilter(field_name="data_publicacao", lookup_expr="gte")
    publicacao_ate = filters.DateFilter(field_name="data_publicacao", lookup_expr="lte")
    encerramento_de = filters.DateTimeFilter(
        field_name="data_encerramento_propostas", lookup_expr="gte",
    )
    encerramento_ate = filters.DateTimeFilter(
        field_name="data_encerramento_propostas", lookup_expr="lte",
    )
    abertura_de = filters.DateTimeFilter(field_name="data_abertura", lookup_expr="gte")
    abertura_ate = filters.DateTimeFilter(field_name="data_abertura", lookup_expr="lte")

    abertas = filters.BooleanFilter(
        method="filtrar_abertas",
        help_text=(
            "true = recebendo propostas agora (status aberta/publicada e "
            "encerramento no futuro ou não informado)."
        ),
    )

    ordering = filters.OrderingFilter(
        fields=(
            ("data_publicacao", "data_publicacao"),
            ("valor_estimado", "valor_estimado"),
            ("data_abertura", "data_abertura"),
            ("data_encerramento_propostas", "data_encerramento_propostas"),
        ),
        help_text="Prefixe com '-' para ordem decrescente.",
    )

    class Meta:
        model = Licitacao
        fields = []

    @staticmethod
    def _qualquer(queryset, termos):
        """OR entre os termos (já separados); cada um é normalizado (sem acento/caixa)."""
        vistos, cond = [], Q()
        for t in termos:
            n = normalizar(t)
            if not n or n in vistos:
                continue
            vistos.append(n)
            if len(vistos) > MAX_PALAVRAS:
                break
            cond |= Q(texto_busca__icontains=condicao_termo(n))
        return queryset.filter(cond) if vistos else queryset

    def filtrar_q(self, queryset, name, value):
        # Com vírgula: lista de alternativas (qualquer uma). Sem vírgula: todas as
        # palavras precisam aparecer (espaço = E), no objeto, número ou órgão.
        if "," in value:
            return self._qualquer(queryset, value.split(","))
        for termo in value.split():
            n = normalizar(termo)
            if not n:
                continue
            queryset = queryset.filter(
                Q(texto_busca__icontains=condicao_termo(n)) | Q(numero__icontains=termo)
            )
        return queryset

    def filtrar_palavras(self, queryset, name, value):
        return self._qualquer(queryset, value)

    def filtrar_uf(self, queryset, name, value):
        return queryset.filter(uf__in=[u.strip().upper() for u in value if u.strip()])

    def filtrar_cnpj(self, queryset, name, value):
        digitos = "".join(c for c in value if c.isdigit())
        if len(digitos) != 14:
            return queryset.filter(orgao__cnpj=value)
        mascarado = (
            f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/"
            f"{digitos[8:12]}-{digitos[12:]}"
        )
        return queryset.filter(orgao__cnpj__in=[value, digitos, mascarado])

    def filtrar_abertas(self, queryset, name, value):
        if value is None:
            return queryset
        agora = timezone.now()
        abertas = Q(status__in=[Licitacao.Status.ABERTA, Licitacao.Status.PUBLICADA]) & (
            Q(data_encerramento_propostas__gte=agora)
            | Q(data_encerramento_propostas__isnull=True)
        )
        return queryset.filter(abertas) if value else queryset.exclude(abertas)
