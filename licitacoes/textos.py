"""Normalização de texto para busca (sem acento, sem caixa, sem pontuação)."""
import re
import unicodedata

_NAO_ALNUM = re.compile(r"[^a-z0-9]+")


def normalizar(texto: str) -> str:
    """'Comunicação, Institucional!' -> 'comunicacao institucional'."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)
    )
    return _NAO_ALNUM.sub(" ", sem_acento.lower()).strip()


def texto_busca(*partes: str) -> str:
    """
    Texto indexável de uma licitação, cercado de espaços: assim ' tv ' casa só a
    palavra inteira (evita 'tv' dentro de outras palavras) e termos longos
    continuam casando por trecho (plurais, derivações).
    """
    return " " + normalizar(" ".join(p for p in partes if p)) + " "


def condicao_termo(termo_normalizado: str) -> str:
    """Trecho a procurar em texto_busca: termos curtos (<= 3) só como palavra inteira."""
    return f" {termo_normalizado} " if len(termo_normalizado) <= 3 else termo_normalizado
