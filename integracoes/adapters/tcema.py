"""
Adapter do TCE-MA (Tribunal de Contas do Estado do Maranhão) - SINC-Contrata.
Swagger: https://tce-api.apps.tcema.tc.br/swagger-ui/index.html

GET /sinccontrata/procedimentolicitatorio?page=N&size=1000 (sem autenticação).
A API não filtra por data nem ordena; o adapter percorre todas as páginas
(~52 mil registros / ~52 requisições) e, no incremental, descarta no cliente o
que foi enviado (`dataEnvio`) antes de `desde` (menos a folga).

Registros que já têm `idContratacaoPncp` no formato do PNCP
(CNPJ-1-SEQ/ANO) são ignorados: entram pela fonte PNCP.

Config (Fonte.config), opcional: base_url, tamanho_pagina (1000),
intervalo_requisicoes_segundos (0.5), timeout (90), folga_dias (7).
"""
import re
from datetime import datetime, timedelta
from typing import Iterator, Optional

from .base import AdapterError, BaseAdapter, LicitacaoDTO, OrgaoDTO
from .util import (
    HTTPJSONMixin, decimal_ou_none, fim_do_dia, formatar_cnpj,
    inferir_modalidade, parse_data,
)

BASE_URL_PADRAO = "https://tce-api.apps.tcema.tc.br"
RE_ID_PNCP = re.compile(r"^\d{14}-\d+-\d+/\d{4}$")
ESTADO = "estado do maranh"


class TCEMAAdapter(HTTPJSONMixin, BaseAdapter):
    def __init__(self, config: Optional[dict] = None, session=None, sleep=None):
        super().__init__(config)
        c = self.config
        kw = {"sleep": sleep} if sleep else {}
        self._init_http(
            session=session, intervalo=c.get("intervalo_requisicoes_segundos", 0.5),
            timeout=c.get("timeout", 90), **kw,
        )
        self.base_url = (c.get("base_url") or BASE_URL_PADRAO).rstrip("/")
        self.tamanho = min(int(c.get("tamanho_pagina", 1000)), 1000)
        self.folga = timedelta(days=int(c.get("folga_dias", 7)))

    def fetch(self, desde: Optional[datetime] = None) -> Iterator[dict]:
        corte = (desde - self.folga).isoformat() if desde else None
        pagina, total = 0, None
        while total is None or pagina < total:
            try:
                dados = self._get_json(
                    f"{self.base_url}/sinccontrata/procedimentolicitatorio",
                    {"page": pagina, "size": self.tamanho},
                )
            except AdapterError as exc:
                self.erros.append(f"página {pagina}: {exc}")
                if total is None:  # nem a 1ª página veio: não há como seguir
                    return
                pagina += 1
                continue
            if not isinstance(dados, dict):
                return
            total = int(dados.get("totalPages") or 0)
            for item in dados.get("content") or []:
                if corte and (item.get("dataEnvio") or "") < corte:
                    continue
                yield item
            pagina += 1

    def normalize(self, raw: dict) -> Optional[LicitacaoDTO]:
        id_externo = raw.get("id")
        objeto = (raw.get("objeto") or "").strip()
        if not id_externo or not objeto:
            return None
        if RE_ID_PNCP.match((raw.get("idContratacaoPncp") or "").strip()):
            return None  # já vem do PNCP

        ente = (raw.get("nomeEnteProcedimento") or "").strip()
        estadual = ente.lower().startswith(ESTADO) or not ente
        municipio = "" if estadual else ente
        razao = (raw.get("nomeEntidadeProcedimento") or ente or "Órgão não informado").strip()

        sessao = parse_data(raw.get("dataSessao"))
        publicacao = parse_data(raw.get("dataPublicacao"))
        hoje = datetime.now().date()
        if sessao:
            aberta = sessao >= hoje
        else:
            aberta = bool(publicacao) and (hoje - publicacao).days <= 90

        numero = ""
        if raw.get("numeroProcedimento") is not None:
            numero = f"{raw['numeroProcedimento']}/{raw.get('anoProcedimento') or ''}".rstrip("/")
        link = raw.get("link_documento") or ""
        return LicitacaoDTO(
            id_externo=str(id_externo),
            orgao=OrgaoDTO(
                cnpj=formatar_cnpj(raw.get("cnpjProcedimento")),
                razao_social=razao[:255],
                esfera="estadual" if estadual else "municipal",
                uf="MA", municipio=municipio,
            ),
            objeto=objeto,
            numero=numero[:50],
            modalidade=inferir_modalidade(raw.get("nomeTipoProcedimento", "")),
            valor_estimado=decimal_ou_none(raw.get("valor")),
            data_publicacao=publicacao,
            data_encerramento_propostas=fim_do_dia(sessao),
            status="publicada" if aberta else "encerrada",
            link_original=link if link.startswith("http") else "",
            uf="MA", municipio=municipio,
        )
