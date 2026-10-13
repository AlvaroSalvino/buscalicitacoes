from django.db.models import Q
from django.utils import timezone
from django_filters import rest_framework as filters

from .models import Licitacao

MAX_PALAVRAS = 30       # palavras-chave por busca/alerta
MAX_TAMANHO_PALAVRA = 60


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """Aceita lista separada por vírgula (?uf=SP,RJ)."""


class LicitacaoFilter(filters.FilterSet):
    q = filters.CharFilter(
        method="filtrar_q",
        help_text=(
            "Palavra-chave. Cada termo (separado por espaço) precisa aparecer "
            "no objeto, número ou nome do órgão."
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

    def filtrar_q(self, queryset, name, value):
        for termo in value.split():
            queryset = queryset.filter(
                Q(objeto__icontains=termo)
                | Q(numero__icontains=termo)
                | Q(orgao__razao_social__icontains=termo)
            )
        return queryset

    def filtrar_palavras(self, queryset, name, value):
        termos = []
        for t in value:
            t = " ".join(t.split())  # normaliza espaços
            if t and t.lower() not in [x.lower() for x in termos]:
                termos.append(t)
        termos = termos[:MAX_PALAVRAS]
        if not termos:
            return queryset
        cond = Q()
        for t in termos:
            cond |= Q(objeto__icontains=t) | Q(orgao__razao_social__icontains=t)
        return queryset.filter(cond)

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
