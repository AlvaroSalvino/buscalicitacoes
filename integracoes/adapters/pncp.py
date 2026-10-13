"""
Adapter do PNCP (Portal Nacional de Contratações Públicas) - API de consulta.

Docs: https://pncp.gov.br/api/consulta/swagger-ui/index.html

Particularidades da API que este adapter respeita:
  * Datas no formato yyyyMMdd; `pagina` obrigatória e começa em 1.
  * `tamanhoPagina` entre 10 e 50 nas contratações.
  * /contratacoes/atualizacao e /publicacao EXIGEM codigoModalidadeContratacao:
    não existe "todas as modalidades" numa chamada, então iteramos os códigos.
  * /contratacoes/proposta só aceita dataFinal (sem dataInicial).
  * Sem resultados a API devolve 204 (sem corpo), não 200 com lista vazia.
  * 400/422 são erros do cliente: sem retry.

Estratégia de sync:
  * Incremental (desde != None): /contratacoes/atualizacao desde o último
    sync bem-sucedido - pega tanto licitações novas quanto alteradas
    (suspensas, revogadas, encerradas etc). Esse endpoint filtra por DATA DE
    ATUALIZAÇÃO: se um registro antigo não foi tocado pelo órgão, ele não
    aparece aqui, mesmo com uma janela larga.
  * Backfill (desde is None: 1ª sincronização OU forcar_completo=True):
    /contratacoes/publicacao, que filtra por DATA DE PUBICAÇÃO real - cobre
    tudo que foi publicado na janela, independente de ter sido atualizado
    depois. É o endpoint certo para popular ou reclassificar o histórico.
    Além disso, faz backfill via /contratacoes/proposta para trazer o que
    está com proposta ABERTA hoje, mesmo que publicado antes da janela.

Config (Fonte.config), todos opcionais:
  base_url, modalidades [int], ufs [str], janela_inicial_dias (3),
  tamanho_pagina (50), timeout (30), max_paginas (2000),
  backfill_propostas_abertas (true), backfill_dias_a_frente (90),
  timezone ("America/Sao_Paulo"),
  intervalo_requisicoes_segundos (1.0), max_tentativas_429 (5)

Rate limit: o PNCP responde 429 quando há requisições demais. O adapter espaça
as chamadas, respeita Retry-After (ou espera 15s/30s/60s/120s...) e, após um
429, dobra o espaçamento pelo resto da execução (até 8s).
"""
import re
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import (
    AdapterConfigError, AdapterError, BaseAdapter, LicitacaoDTO, OrgaoDTO,
)

BASE_URL_PADRAO = "https://pncp.gov.br/api/consulta/v1"

# Tabela de domínio "Modalidade de Contratação" do PNCP -> Licitacao.Modalidade
MODALIDADES_PNCP = {
    1: "leilao",               # Leilão - Eletrônico
    2: "dialogo_competitivo",
    3: "concurso",
    4: "concorrencia",         # Concorrência - Eletrônica
    5: "concorrencia",         # Concorrência - Presencial
    6: "pregao",               # Pregão - Eletrônico
    7: "pregao",               # Pregão - Presencial
    8: "dispensa",
    9: "inexigibilidade",
    10: "manifestacao_interesse",
    11: "pre_qualificacao",
    12: "credenciamento",
    13: "leilao",              # Leilão - Presencial
}
MODALIDADES_PADRAO = sorted(MODALIDADES_PNCP)

# esferaId do PNCP: F=Federal, E=Estadual, M=Municipal, D=Distrital.
# Distrital é tratado como estadual (o model só tem 3 esferas).
ESFERAS_PNCP = {"F": "federal", "E": "estadual", "D": "estadual", "M": "municipal"}
ESFERA_FALLBACK = "municipal"  # maioria absoluta dos órgãos no PNCP

# situacaoCompraId do PNCP -> status fixo. Os demais casos (1 = divulgada)
# são derivados das datas de recebimento de propostas.
SITUACOES_FIXAS = {2: "revogada", 3: "cancelada", 4: "suspensa"}  # 3 = anulada


def formatar_cnpj(digitos: str) -> str:
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    return digitos


def _so_digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _decimal(valor) -> Optional[Decimal]:
    if valor is None:
        return None
    try:
        d = Decimal(str(valor)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    # DecimalField(max_digits=14, decimal_places=2) => < 10**12
    if d < 0 or d >= Decimal(10) ** 12:
        return None
    if d == 0:
        # Na prática o PNCP usa 0 para "valor não informado/sigiloso", não
        # para licitações genuinamente gratuitas (raras). Tratar como
        # "desconhecido" evita que entrem em alertas de "valor até X".
        return None
    return d


class PNCPAdapter(BaseAdapter):
    def __init__(
        self, config: Optional[dict] = None,
        session: Optional[requests.Session] = None, sleep=time.sleep,
    ):
        super().__init__(config)
        self._sleep = sleep
        self._ultima_requisicao = 0.0
        c = self.config
        self.base_url = (c.get("base_url") or BASE_URL_PADRAO).rstrip("/")
        self.modalidades = list(c.get("modalidades") or MODALIDADES_PADRAO)
        self.ufs = [u.upper() for u in (c.get("ufs") or [])]
        self.janela_inicial_dias = int(c.get("janela_inicial_dias", 3))
        self.timeout = int(c.get("timeout", 30))
        self.max_paginas = int(c.get("max_paginas", 2000))
        self.backfill = bool(c.get("backfill_propostas_abertas", True))
        self.backfill_dias = int(c.get("backfill_dias_a_frente", 90))
        self.tz = ZoneInfo(c.get("timezone", "America/Sao_Paulo"))
        self.intervalo = float(c.get("intervalo_requisicoes_segundos", 1.0))
        self.max_tentativas_429 = int(c.get("max_tentativas_429", 5))

        self.tamanho_pagina = int(c.get("tamanho_pagina", 50))
        if not 10 <= self.tamanho_pagina <= 50:
            raise AdapterConfigError("tamanho_pagina do PNCP deve estar entre 10 e 50.")

        self.session = session or self._criar_session()

    # ------------------------------------------------------------------ HTTP

    @staticmethod
    def _criar_session() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3, backoff_factor=2,
            status_forcelist=(500, 502, 503, 504),  # 429 é tratado em _get
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers.update({"accept": "application/json"})
        return session

    def _respeitar_intervalo(self):
        falta = self.intervalo - (time.monotonic() - self._ultima_requisicao)
        if falta > 0:
            self._sleep(falta)
        self._ultima_requisicao = time.monotonic()

    def _espera_429(self, resp, tentativa: int) -> float:
        retry_after = (getattr(resp, "headers", None) or {}).get("Retry-After", "")
        if str(retry_after).isdigit():
            return min(float(retry_after), 300.0)
        return min(15.0 * 2 ** (tentativa - 1), 120.0)

    def _get(self, path: str, params: dict) -> Optional[dict]:
        url = f"{self.base_url}{path}"
        tentativas_429 = 0
        while True:
            self._respeitar_intervalo()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                raise AdapterError(f"Falha de rede em {path}: {exc}") from exc

            if resp.status_code == 429:
                tentativas_429 += 1
                # Fica mais devagar pelo resto da execução.
                self.intervalo = min(max(self.intervalo, 0.5) * 2, 8.0)
                if tentativas_429 > self.max_tentativas_429:
                    raise AdapterError(
                        f"PNCP limitou a taxa (429) em {path} após "
                        f"{self.max_tentativas_429} esperas."
                    )
                self._sleep(self._espera_429(resp, tentativas_429))
                continue
            break

        if resp.status_code == 204:
            return None
        if resp.status_code in (400, 422):
            # Erro do cliente: repetir a mesma chamada não adianta.
            raise AdapterConfigError(
                f"PNCP rejeitou a consulta ({resp.status_code}) em {path} "
                f"params={params}: {resp.text[:300]}"
            )
        if not resp.ok:
            raise AdapterError(f"PNCP respondeu {resp.status_code} em {path}")
        try:
            return resp.json()
        except ValueError as exc:
            raise AdapterError(f"Resposta não-JSON do PNCP em {path}") from exc

    def _paginar(self, path: str, params: dict) -> Iterator[dict]:
        pagina = 1
        while True:
            if pagina > self.max_paginas:
                raise AdapterError(f"Limite de {self.max_paginas} páginas excedido em {path}")
            envelope = self._get(
                path, {**params, "pagina": pagina, "tamanhoPagina": self.tamanho_pagina},
            )
            if not envelope:
                return
            registros = envelope.get("data") or []
            yield from registros

            restantes = envelope.get("paginasRestantes")
            if restantes is None:
                total = envelope.get("totalPaginas") or 0
                tem_mais = pagina < total
            else:
                tem_mais = restantes > 0
            if not registros or not tem_mais:
                return
            pagina += 1

    # ----------------------------------------------------------------- fetch

    def _agora(self) -> datetime:
        """Agora, ingênuo, no fuso da fonte (Brasília)."""
        return datetime.now(self.tz).replace(tzinfo=None)

    def fetch(self, desde: Optional[datetime] = None) -> Iterator[dict]:
        hoje = self._agora().date()
        vistos: set[str] = set()
        ufs = self.ufs or [None]

        def emitir(registros, rotulo):
            try:
                for raw in registros:
                    chave = raw.get("numeroControlePNCP") or repr(
                        (raw.get("orgaoEntidade", {}).get("cnpj"),
                         raw.get("anoCompra"), raw.get("sequencialCompra"))
                    )
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    yield raw
            except (AdapterError, AdapterConfigError) as exc:
                # Isola a falha na fatia: as demais continuam.
                self.erros.append(f"{rotulo}: {exc}")

        # 1) Backfill do que está com proposta aberta (só na 1ª sincronização)
        if desde is None and self.backfill:
            data_final = hoje + timedelta(days=self.backfill_dias)
            for uf in ufs:
                params = {"dataFinal": data_final.strftime("%Y%m%d")}
                if uf:
                    params["uf"] = uf
                yield from emitir(
                    self._paginar("/contratacoes/proposta", params),
                    f"proposta uf={uf or '*'}",
                )

        # 2) Fatiado por modalidade (e UF). Backfill usa data de PUBLICAÇÃO
        #    (recupera o histórico de verdade); incremental usa data de
        #    ATUALIZAÇÃO (pega mudanças em registros já existentes).
        if desde is None:
            path = "/contratacoes/publicacao"
            inicio = hoje - timedelta(days=self.janela_inicial_dias)
            rotulo_base = "publicacao"
        else:
            path = "/contratacoes/atualizacao"
            inicio = desde.date()
            rotulo_base = "atualizacao"

        for modalidade in self.modalidades:
            for uf in ufs:
                params = {
                    "dataInicial": inicio.strftime("%Y%m%d"),
                    "dataFinal": hoje.strftime("%Y%m%d"),
                    "codigoModalidadeContratacao": modalidade,
                }
                if uf:
                    params["uf"] = uf
                yield from emitir(
                    self._paginar(path, params),
                    f"{rotulo_base} modalidade={modalidade} uf={uf or '*'}",
                )

    # ------------------------------------------------------------- normalize

    def _parse_datetime(self, valor) -> Optional[datetime]:
        if not valor:
            return None
        try:
            dt = datetime.fromisoformat(str(valor))
        except ValueError:
            return None
        if dt.tzinfo is not None:
            dt = dt.astimezone(self.tz).replace(tzinfo=None)
        return dt

    def _status(self, raw: dict, abertura, encerramento) -> str:
        fixo = SITUACOES_FIXAS.get(raw.get("situacaoCompraId"))
        if fixo:
            return fixo
        agora = self._agora()
        if encerramento and agora > encerramento:
            return "encerrada"
        if abertura and agora < abertura:
            return "publicada"
        if abertura or encerramento:
            return "aberta"
        return "publicada"

    def normalize(self, raw: dict) -> Optional[LicitacaoDTO]:
        org = raw.get("orgaoEntidade") or {}
        unidade = raw.get("unidadeOrgao") or {}

        cnpj = _so_digitos(org.get("cnpj"))
        if len(cnpj) != 14:
            return None  # sem CNPJ não há como identificar o órgão

        ano, seq = raw.get("anoCompra"), raw.get("sequencialCompra")
        id_externo = raw.get("numeroControlePNCP")
        if not id_externo:
            if not (ano and seq):
                return None
            id_externo = f"{cnpj}-1-{int(seq):06d}/{ano}"

        objeto = (raw.get("objetoCompra") or "").strip()
        if not objeto:
            return None

        uf = (unidade.get("ufSigla") or "").upper()[:2]
        municipio = (unidade.get("municipioNome") or "")[:150]

        orgao = OrgaoDTO(
            cnpj=formatar_cnpj(cnpj),
            razao_social=(org.get("razaoSocial") or "Órgão não informado")[:255],
            esfera=ESFERAS_PNCP.get(str(org.get("esferaId") or "").upper(), ESFERA_FALLBACK),
            uf=uf,
            municipio=municipio,
        )

        abertura = self._parse_datetime(raw.get("dataAberturaProposta"))
        encerramento = self._parse_datetime(raw.get("dataEncerramentoProposta"))
        publicacao = self._parse_datetime(raw.get("dataPublicacaoPncp"))

        numero = str(raw.get("numeroCompra") or "").strip()
        if numero and ano:
            numero = f"{numero}/{ano}"

        portal = f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}" if (ano and seq) else ""
        origem = (raw.get("linkSistemaOrigem") or "").strip()
        if origem.lower().startswith(("http://", "https://")) and len(origem) <= 500:
            link = origem
        else:
            link = portal

        return LicitacaoDTO(
            id_externo=str(id_externo)[:100],
            orgao=orgao,
            objeto=objeto,
            numero=numero[:50],
            modalidade=MODALIDADES_PNCP.get(raw.get("modalidadeId"), "outra"),
            valor_estimado=_decimal(raw.get("valorTotalEstimado")),
            data_publicacao=publicacao.date() if publicacao else None,
            data_abertura=abertura,
            data_encerramento_propostas=encerramento,
            status=self._status(raw, abertura, encerramento),
            link_original=link,
            uf=uf,
            municipio=municipio,
        )
