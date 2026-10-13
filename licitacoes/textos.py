"""Normalização de texto para busca (sem acento, sem caixa, sem pontuação)."""
import re
import unicodedata

_NAO_ALNUM = re.compile(r"[^a-z0-9]+")

# Termos de até este tamanho só casam como palavra inteira (ou plural simples):
# evita 'atos' dentro de 'contratos' ou 'tv' dentro de outras palavras.
TAMANHO_PALAVRA_CURTA = 4


def normalizar(texto: str) -> str:
    """'Comunicação, Institucional!' -> 'comunicacao institucional'."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)
    )
    return _NAO_ALNUM.sub(" ", sem_acento.lower()).strip()


def texto_busca(*partes: str) -> str:
    """
    Texto indexável de uma licitação, cercado de espaços: assim ' tv ' casa só a
    palavra inteira e termos longos continuam casando por trecho (plurais,
    derivações).
    """
    return " " + normalizar(" ".join(p for p in partes if p)) + " "


def agulhas(termo_normalizado: str) -> list:
    """
    Trechos a procurar em texto_busca para um termo já normalizado.
    Curto (<= 4 letras): palavra inteira ou com 's' final (obra/obras).
    Longo: por trecho.
    """
    t = termo_normalizado
    if len(t) <= TAMANHO_PALAVRA_CURTA:
        return [f" {t} ", f" {t}s "]
    return [t]
