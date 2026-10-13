"""Aplica os filtros salvos de um Alerta sobre um queryset de Licitacao."""
from licitacoes.filters import LicitacaoFilter
from licitacoes.models import Licitacao

# `ordering` não faz sentido em um alerta.
CHAVES_PERMITIDAS = set(LicitacaoFilter.base_filters) - {"ordering"}


def normalizar(filtros):
    """Listas viram 'a,b' (formato da query string); valores vazios caem fora."""
    saida = {}
    for chave, valor in (filtros or {}).items():
        if isinstance(valor, (list, tuple)):
            valor = ",".join(str(v) for v in valor)
        if valor is None or str(valor).strip() == "":
            continue
        saida[chave] = str(valor) if not isinstance(valor, bool) else str(valor).lower()
    return saida


def validar(filtros):
    """Retorna (filtros_normalizados, erros: dict)."""
    dados = normalizar(filtros)
    desconhecidos = sorted(set(dados) - CHAVES_PERMITIDAS)
    if desconhecidos:
        return dados, {"filtros": [f"Filtros desconhecidos: {', '.join(desconhecidos)}."]}
    fs = LicitacaoFilter(data=dados, queryset=Licitacao.objects.none())
    if not fs.is_valid():
        return dados, {"filtros": [f"{k}: {' '.join(v)}" for k, v in fs.errors.items()]}
    if not dados:
        return dados, {"filtros": ["Informe ao menos um filtro."]}
    return dados, {}


def aplicar(queryset, filtros):
    fs = LicitacaoFilter(data=normalizar(filtros), queryset=queryset)
    if not fs.is_valid():
        return queryset.none()
    return fs.qs
