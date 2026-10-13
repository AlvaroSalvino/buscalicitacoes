"""Helpers compartilhados pelos adapters de Tribunais de Contas (TCE)."""
import re
import time
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import AdapterError


def sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# (palavra-chave, modalidade) - a primeira que casar vence.
_MODALIDADES = [
    ("inexigibilidade", "inexigibilidade"),
    ("dispensa", "dispensa"),
    ("pregao", "pregao"),
    ("tomada de preco", "tomada_precos"),
    ("concorrencia", "concorrencia"),
    ("convite", "convite"),
    ("leilao", "leilao"),
    ("concurso", "concurso"),
    ("credenciamento", "credenciamento"),
    ("dialogo competitivo", "dialogo_competitivo"),
    ("pre-qualificacao", "pre_qualificacao"),
    ("pre qualificacao", "pre_qualificacao"),
    ("manifestacao de interesse", "manifestacao_interesse"),
]


def inferir_modalidade(texto: str) -> str:
    """Mapeia o nome livre de uma modalidade para Licitacao.Modalidade."""
    t = sem_acento(texto)
    for chave, modalidade in _MODALIDADES:
        if chave in t:
            return modalidade
    return "outra"


def decimal_ou_none(valor) -> Optional[Decimal]:
    """Valor monetário válido para DecimalField(14,2); 0/negativo = não informado."""
    if valor is None or valor == "":
        return None
    try:
        d = Decimal(str(valor)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    if d <= 0 or d >= Decimal(10) ** 12:
        return None
    return d


def formatar_cnpj(valor) -> Optional[str]:
    d = re.sub(r"\D", "", str(valor or ""))
    if len(d) != 14:
        return None
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def parse_data(valor) -> Optional[date]:
    """Aceita 'YYYY-MM-DD', ISO com hora, ou 'YYYYMMDD'."""
    if not valor:
        return None
    s = str(valor).strip()
    try:
        if re.fullmatch(r"\d{8}", s):
            return datetime.strptime(s, "%Y%m%d").date()
        return datetime.fromisoformat(s.replace("Z", "")[:19]).date()
    except ValueError:
        return None


def fim_do_dia(d: Optional[date]) -> Optional[datetime]:
    """Prazo conhecido só por data: considera até o fim do dia."""
    return datetime(d.year, d.month, d.day, 23, 59, 59) if d else None


class HTTPJSONMixin:
    """GET JSON com espaçamento entre chamadas e erros no padrão AdapterError."""

    def _init_http(self, session=None, sleep=time.sleep, intervalo=0.5, timeout=60):
        self._sleep = sleep
        self._ultima_requisicao = 0.0
        self.intervalo = float(intervalo)
        self.timeout = int(timeout)
        self.session = session or self._criar_session()

    @staticmethod
    def _criar_session() -> requests.Session:
        s = requests.Session()
        retry = Retry(
            total=3, backoff_factor=2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",), respect_retry_after_header=True,
        )
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.headers.update({"accept": "application/json", "user-agent": "buscalicitacoes/1.0"})
        return s

    def _respeitar_intervalo(self):
        falta = self.intervalo - (time.monotonic() - self._ultima_requisicao)
        if falta > 0:
            self._sleep(falta)
        self._ultima_requisicao = time.monotonic()

    def _get_json(self, url: str, params: Optional[dict] = None):
        self._respeitar_intervalo()
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise AdapterError(f"Falha de rede em {url}: {exc}") from exc
        if resp.status_code == 204:
            return None
        if not resp.ok:
            raise AdapterError(f"{url} respondeu {resp.status_code}: {str(resp.text)[:200]}")
        try:
            dados = resp.json()
        except ValueError as exc:
            raise AdapterError(f"Resposta não-JSON em {url}") from exc
        if isinstance(dados, dict) and dados.get("__errors__"):
            msg = dados["__errors__"][0].get("message", "")[:200]
            raise AdapterError(f"{url} retornou erro: {msg}")
        return dados
