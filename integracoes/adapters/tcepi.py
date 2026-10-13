"""
Adapter do TCE-PI (Tribunal de Contas do Estado do Piauí) - API do Portal da
Cidadania: https://sistemas.tce.pi.gov.br/api/portaldacidadania/docs/

Fonte: Mural de Licitações (Sistema Licitações Web), com as licitações
municipais com abertura prevista. Estratégia, sempre completa (é pequena e o
upsert é idempotente - `desde` é ignorado):
  1. GET /prefeituras                                    -> lista de municípios
  2. GET /licitacoes/{municipio}                         -> datas com licitação
  3. GET /licitacoes/{municipio}/1/{AAAAMMDD}?pagina=N   -> detalhe do dia

Limitações da API: só expõe licitações MUNICIPAIS (esfera 1) com abertura
futura; a data de abertura vem sem hora (usamos o fim do dia como prazo);
não há CNPJ do órgão nem número do procedimento.

Config (Fonte.config), opcional: base_url, dias_passados (3),
qtde_por_pagina (100), intervalo_requisicoes_segundos (0.3), timeout (60).
"""
from datetime import date, datetime, timedelta
from typing import Iterator, Optional

from .base import AdapterError, BaseAdapter, LicitacaoDTO, OrgaoDTO
from .util import (
    HTTPJSONMixin, decimal_ou_none, fim_do_dia, inferir_modalidade, parse_data,
)

BASE_URL_PADRAO = "https://sistemas.tce.pi.gov.br/api/portaldacidadania"


class TCEPIAdapter(HTTPJSONMixin, BaseAdapter):
    def __init__(self, config: Optional[dict] = None, session=None, sleep=None):
        super().__init__(config)
        c = self.config
        kw = {"sleep": sleep} if sleep else {}
        self._init_http(
            session=session, intervalo=c.get("intervalo_requisicoes_segundos", 0.3),
            timeout=c.get("timeout", 60), **kw,
        )
        self.base_url = (c.get("base_url") or BASE_URL_PADRAO).rstrip("/")
        self.dias_passados = int(c.get("dias_passados", 3))
        self.qtde = min(int(c.get("qtde_por_pagina", 100)), 100)

    def _hoje(self) -> date:
        return datetime.now().date()

    def fetch(self, desde: Optional[datetime] = None) -> Iterator[dict]:
        # Falha aqui = sem lista de municípios = nada a fazer: AdapterError (retry).
        prefeituras = self._get_json(f"{self.base_url}/prefeituras") or []
        limite = self._hoje() - timedelta(days=self.dias_passados)

        for pref in prefeituras:
            pid = pref.get("id")
            try:
                datas = self._get_json(f"{self.base_url}/licitacoes/{pid}") or []
                for d in datas:
                    dia = parse_data(d.get("link") or d.get("data"))
                    if dia is None or dia < limite:
                        continue
                    yield from self._detalhe(pref, pid, dia)
            except AdapterError as exc:
                self.erros.append(f"{pref.get('nome')} ({pid}): {exc}")

    def _detalhe(self, pref, pid, dia: date) -> Iterator[dict]:
        pagina = 1
        while True:
            itens = self._get_json(
                f"{self.base_url}/licitacoes/{pid}/1/{dia:%Y%m%d}",
                {"pagina": pagina, "qtdePorPagina": self.qtde},
            ) or []
            for it in itens:
                it["_municipio"] = pref.get("nome") or ""
                it["_dia"] = dia.isoformat()
                yield it
            if len(itens) < self.qtde:
                return
            pagina += 1

    def normalize(self, raw: dict) -> Optional[LicitacaoDTO]:
        id_externo = raw.get("idLicitacaoWeb")
        objeto = (raw.get("objeto") or "").strip()
        dia = parse_data(raw.get("_dia"))
        if not id_externo or not objeto:
            return None
        municipio = raw.get("_municipio", "")
        unidade = (raw.get("unidadeOrcamentaria") or "").strip()
        aberta = dia is not None and dia >= self._hoje()
        return LicitacaoDTO(
            id_externo=str(id_externo),
            orgao=OrgaoDTO(
                cnpj=None,
                razao_social=(unidade or f"Prefeitura Municipal de {municipio}")[:255],
                esfera="municipal", uf="PI", municipio=municipio,
            ),
            objeto=objeto,
            modalidade=inferir_modalidade(raw.get("modalidade", "")),
            valor_estimado=decimal_ou_none(raw.get("previsto")),
            data_encerramento_propostas=fim_do_dia(dia),
            status="publicada" if aberta else "encerrada",
            link_original=raw.get("mural") or "",
            uf="PI", municipio=municipio,
        )
