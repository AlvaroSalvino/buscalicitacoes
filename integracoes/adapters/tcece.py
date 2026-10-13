"""
Adapter do TCE-CE (Tribunal de Contas do Estado do Ceará) - API SIM.
Swagger: https://api-dados-abertos.tce.ce.gov.br/sim/

Endpoint: /processos_administrativos_contratacoes (Processos Administrativos
para Contratações - LCO), um município por chamada (`codigo_municipio`),
filtrado pela data de AUTUAÇÃO (formato AAAAMMDD), paginado com
$count (máx. 1000) e $start_index. Lista de municípios: /municipios.

Os municípios enviam os dados ao SIM com atraso (mensal), então o incremental
volta `folga_dias` (padrão 45) antes de `desde`. A 1ª sincronização cobre
`janela_inicial_dias` (padrão 180).

Observações do dado:
  * Não há nome do órgão: usamos "Prefeitura Municipal de X" (órgão = município).
  * `modalidade_licitacao` é código (6 = pregão, 3 = concorrência, 9 = sem
    licitação: dispensa 'D' / inexigibilidade 'I' em modalidade_processo_
    administrativo). Mapeamento INFERIDO dos dados; o prefixo do número
    (PE, CP, DE, INEX, CR...) tem prioridade quando existe.
  * Registros com `numero_id_contratacao_pncp` já estão no PNCP e são ignorados.

Config (Fonte.config), opcional: base_url, janela_inicial_dias (180),
folga_dias (45), intervalo_requisicoes_segundos (0.5), timeout (120).
"""
import hashlib
import re
from datetime import datetime, timedelta
from typing import Iterator, Optional

from .base import AdapterError, BaseAdapter, LicitacaoDTO, OrgaoDTO
from .util import HTTPJSONMixin, decimal_ou_none, parse_data

BASE_URL_PADRAO = "https://api-dados-abertos.tce.ce.gov.br/sim"
POR_PAGINA = 1000

_PREFIXOS = [  # prefixo do número do processo -> modalidade
    (re.compile(r"^(PE|PP|PRE|PREG)", re.I), "pregao"),
    (re.compile(r"^(CP|CC|CONC|TP)", re.I), "concorrencia"),
    (re.compile(r"^(INEX)", re.I), "inexigibilidade"),
    (re.compile(r"^(DE|DL|DISP)", re.I), "dispensa"),
    (re.compile(r"^(CR|CRED)", re.I), "credenciamento"),
    (re.compile(r"^(LEIL)", re.I), "leilao"),
]
_POR_CODIGO = {"6": "pregao", "3": "concorrencia"}
_POR_PROCESSO = {"D": "dispensa", "I": "inexigibilidade"}


def modalidade_ce(numero, codigo, processo) -> str:
    n = (numero or "").strip()
    for rx, mod in _PREFIXOS:
        if rx.match(n):
            return mod
    proc = (processo or "").strip()
    if proc in _POR_PROCESSO:
        return _POR_PROCESSO[proc]
    return _POR_CODIGO.get((codigo or "").strip(), "outra")


class TCECEAdapter(HTTPJSONMixin, BaseAdapter):
    def __init__(self, config: Optional[dict] = None, session=None, sleep=None):
        super().__init__(config)
        c = self.config
        kw = {"sleep": sleep} if sleep else {}
        self._init_http(
            session=session, intervalo=c.get("intervalo_requisicoes_segundos", 0.5),
            timeout=c.get("timeout", 120), **kw,
        )
        self.base_url = (c.get("base_url") or BASE_URL_PADRAO).rstrip("/")
        self.janela = int(c.get("janela_inicial_dias", 180))
        self.folga = int(c.get("folga_dias", 45))

    def _hoje(self):
        return datetime.now().date()

    def fetch(self, desde: Optional[datetime] = None) -> Iterator[dict]:
        hoje = self._hoje()
        if desde:
            inicio = desde.date() - timedelta(days=self.folga)
        else:
            inicio = hoje - timedelta(days=self.janela)

        resp = self._get_json(f"{self.base_url}/municipios", {"$count": POR_PAGINA}) or {}
        municipios = [
            m for m in resp.get("elements", [])
            if (m.get("nome_municipio") or "").strip().upper() != "T.C.M."
        ]
        for mun in municipios:
            cod = mun["codigo_municipio"]
            idx = 0
            try:
                while True:
                    dados = self._get_json(
                        f"{self.base_url}/processos_administrativos_contratacoes",
                        {
                            "codigo_municipio": cod,
                            "data_inicio": f"{inicio:%Y%m%d}",
                            "data_fim": f"{hoje:%Y%m%d}",
                            "$count": POR_PAGINA, "$start_index": idx,
                        },
                    ) or {}
                    elementos = dados.get("elements") or []
                    for el in elementos:
                        el["_municipio"] = (mun.get("nome_municipio") or "").title()
                        yield el
                    if len(elementos) < POR_PAGINA:
                        break
                    idx += POR_PAGINA
            except AdapterError as exc:
                self.erros.append(f"{mun.get('nome_municipio')} ({cod}): {exc}")

    def normalize(self, raw: dict) -> Optional[LicitacaoDTO]:
        objeto = (raw.get("descricao_objeto_licitacao") or "").strip()
        numero = (raw.get("numero_licitacao") or "").strip()
        cod = raw.get("codigo_municipio")
        autuacao = parse_data(raw.get("data_realizacao_autuacao_licitacao"))
        if not (objeto and numero and cod and autuacao):
            return None
        if re.sub(r"\D", "", raw.get("numero_id_contratacao_pncp") or ""):
            return None  # já vem do PNCP

        # Sem identificador próprio: município + número + autuação + hash do
        # objeto (diferencia unidades gestoras com o mesmo número).
        h = hashlib.sha1(objeto.encode("utf-8")).hexdigest()[:8]
        id_externo = f"{cod}-{numero}-{autuacao:%Y%m%d}-{h}"[:100]

        abertura = parse_data(raw.get("data_realizacao_licitacao"))
        abertura_dt = None
        if abertura:
            hh, mm = 23, 59  # hora desconhecida: vale o dia inteiro
            m = re.fullmatch(r"(\d{1,2}):(\d{2})", (raw.get("hora_licitacao") or "").strip())
            if m and int(m[1]) < 24 and int(m[2]) < 60:
                hh, mm = int(m[1]), int(m[2])
            abertura_dt = datetime(abertura.year, abertura.month, abertura.day, hh, mm)

        if parse_data(raw.get("data_homologacao")):
            status = "homologada"
        elif abertura_dt and abertura_dt < datetime.now():
            status = "encerrada"
        else:
            status = "publicada"

        municipio = raw.get("_municipio") or ""
        url = (raw.get("descricao_url_plataforma_contratacao") or "").strip()
        return LicitacaoDTO(
            id_externo=id_externo,
            orgao=OrgaoDTO(
                cnpj=None,
                razao_social=f"Prefeitura Municipal de {municipio}"[:255],
                esfera="municipal", uf="CE", municipio=municipio,
            ),
            objeto=objeto,
            numero=numero[:50],
            modalidade=modalidade_ce(
                numero, raw.get("modalidade_licitacao"),
                raw.get("modalidade_processo_administrativo"),
            ),
            valor_estimado=decimal_ou_none(raw.get("valor_orcado_estimado")),
            data_publicacao=parse_data(raw.get("data_emissao_edital")) or autuacao,
            data_abertura=abertura_dt,
            data_encerramento_propostas=abertura_dt,
            status=status,
            link_original=url if url.lower().startswith("http") else "",
            uf="CE", municipio=municipio,
        )
