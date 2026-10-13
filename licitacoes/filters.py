from django.db.models import Q
from django.utils import timezone
from django_filters import rest_framework as filters

from .models import Licitacao
from .textos import agulhas, normalizar

MAX_PALAVRAS = 60       # palavras-chave por busca/alerta
MAX_TAMANHO_PALAVRA = 60

# Em combinar=qualquer, estes filtros "somam" (OU entre si); os demais
# (UF, situação, prazo, valor, datas...) continuam restringindo (E).
FILTROS_DE_INTERESSE = ("q", "palavras", "modalidade", "orgao")


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """Aceita lista separada por vírgula (?uf=SP,RJ)."""


def _q_agulhas(termo_normalizado):
    cond = Q()
    for a in agulhas(termo_normalizado):
        cond |= Q(texto_busca__icontains=a)
    return cond


def q_qualquer(termos):
    """OR entre os termos (cada um normalizado: sem acento/caixa). None se vazio."""
    vistos, cond = [], Q()
    for t in termos:
        n = normalizar(t)
        if not n or n in vistos:
            continue
        vistos.append(n)
        if len(vistos) > MAX_PALAVRAS:
            break
        cond |= _q_agulhas(n)
    return cond if vistos else None


def q_todas(texto):
    """E entre as palavras (separadas por espaço), no objeto/órgão ou no número."""
    cond = None
    for termo in texto.split():
        n = normalizar(termo)
        if not n:
            continue
        c = _q_agulhas(n) | Q(numero__icontains=termo)
        cond = c if cond is None else cond & c
    return cond


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

    combinar = filters.ChoiceFilter(
        choices=[("todos", "Todos os filtros"), ("qualquer", "Somar critérios")],
        method="nao_filtra",
        help_text=(
            "todos (padrão): a licitação precisa atender a TODOS os filtros. "
            "qualquer: os critérios de interesse (q, palavras, modalidade, orgao) "
            "SOMAM-se (basta casar com um deles); UF, status, abertas, datas e "
            "valores continuam restringindo."
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

    # ---- modo "somar": OU entre os critérios de interesse ----
    def filter_queryset(self, queryset):
        dados = self.form.cleaned_data
        if dados.get("combinar") != "qualquer":
            return super().filter_queryset(queryset)

        soma = Q()
        tem_criterio = False
        for nome, valor in dados.items():
            if nome == "combinar":
                continue
            if nome in FILTROS_DE_INTERESSE:
                cond = self._condicao_interesse(nome, valor)
                if cond is not None:
                    soma |= cond
                    tem_criterio = True
                continue
            queryset = self.filters[nome].filter(queryset, valor)
        return queryset.filter(soma) if tem_criterio else queryset

    @staticmethod
    def _condicao_interesse(nome, valor):
        if not valor:
            return None
        if nome == "q":
            return q_qualquer(valor.split(",")) if "," in valor else q_todas(valor)
        if nome == "palavras":
            return q_qualquer(valor)
        if nome == "modalidade":
            return Q(modalidade__in=[v.strip() for v in valor if v.strip()]) if valor else None
        if nome == "orgao":
            return Q(orgao__razao_social__icontains=valor)
        return None

    # ---- métodos dos filtros (modo "todos") ----
    def nao_filtra(self, queryset, name, value):
        return queryset

    def filtrar_q(self, queryset, name, value):
        # Com vírgula: lista de alternativas (qualquer uma). Sem vírgula: todas as
        # palavras precisam aparecer (espaço = E), no objeto, número ou órgão.
        cond = q_qualquer(value.split(",")) if "," in value else q_todas(value)
        return queryset.filter(cond) if cond is not None else queryset

    def filtrar_palavras(self, queryset, name, value):
        cond = q_qualquer(value)
        return queryset.filter(cond) if cond is not None else queryset

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
