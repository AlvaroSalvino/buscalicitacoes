"""
Testes dos adapters de TCE (PI, MA, CE). Sem Django e sem rede:
    python -m unittest integracoes.tests.test_tce_adapters
"""
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal

from integracoes.adapters import ADAPTERS
from integracoes.adapters.tcece import TCECEAdapter, modalidade_ce
from integracoes.adapters.tcema import TCEMAAdapter
from integracoes.adapters.tcepi import TCEPIAdapter
from integracoes.adapters.util import inferir_modalidade, parse_data

HOJE = datetime.now().date()


class FakeResp:
    def __init__(self, body=None, status=200):
        self.status_code = status
        self._body = body
        self.text = str(body)
        self.ok = status < 400

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, handler):
        self.handler = handler
        self.chamadas = []

    def get(self, url, params=None, timeout=None):
        self.chamadas.append((url, dict(params or {})))
        return self.handler(url, dict(params or {}))


def nosleep(_):
    pass


class UtilTests(unittest.TestCase):
    def test_modalidade(self):
        self.assertEqual(inferir_modalidade("Pregão Eletrônico"), "pregao")
        self.assertEqual(inferir_modalidade("Aviso de Dispensa"), "dispensa")
        self.assertEqual(inferir_modalidade("Dispensa Eletrônica de Licitação"), "dispensa")
        self.assertEqual(inferir_modalidade("Concorrência pública"), "concorrencia")
        self.assertEqual(inferir_modalidade("Procedimento da Lei 13.303/2016"), "outra")

    def test_parse_data(self):
        self.assertEqual(parse_data("20261014"), date(2026, 10, 14))
        self.assertEqual(parse_data("2026-10-14T00:00:00.000Z"), date(2026, 10, 14))
        self.assertIsNone(parse_data("lixo"))

    def test_registry(self):
        for chave in ("tce_pi", "tce_ma", "tce_ce"):
            self.assertIn(chave, ADAPTERS)


class TCEPITests(unittest.TestCase):
    def _adapter(self, handler):
        return TCEPIAdapter({"intervalo_requisicoes_segundos": 0}, session=FakeSession(handler), sleep=nosleep)

    def test_fetch_e_normalize(self):
        amanha = HOJE + timedelta(days=1)
        ontem = HOJE - timedelta(days=30)

        def handler(url, params):
            if url.endswith("/prefeituras"):
                return FakeResp([{"id": 118, "nome": "Altos"}, {"id": 5, "nome": "Vazia"}])
            if url.endswith("/licitacoes/118"):
                return FakeResp([
                    {"link": f"{amanha:%Y%m%d}", "previsto": 10},
                    {"link": f"{ontem:%Y%m%d}", "previsto": 5},  # fora da janela
                ])
            if url.endswith("/licitacoes/5"):
                return FakeResp([])
            if url.endswith(f"/licitacoes/118/1/{amanha:%Y%m%d}"):
                return FakeResp([{
                    "previsto": 130710.18, "modalidade": "Aviso de Dispensa",
                    "mural": "https://sistemas.tce.pi.gov.br/muralic/detalhelicitacao.xhtml?id=1",
                    "objeto": "CONSTRUÇÃO DE AUDITÓRIO", "unidadeOrcamentaria": "CAMARA DE ALTOS",
                    "idLicitacaoWeb": 1175162,
                }])
            raise AssertionError(f"chamada inesperada {url}")

        ad = self._adapter(handler)
        itens = list(ad.fetch())
        self.assertEqual(len(itens), 1)
        dto = ad.normalize(itens[0])
        self.assertEqual(dto.id_externo, "1175162")
        self.assertEqual(dto.orgao.razao_social, "CAMARA DE ALTOS")
        self.assertIsNone(dto.orgao.cnpj)
        self.assertEqual((dto.uf, dto.municipio), ("PI", "Altos"))
        self.assertEqual(dto.modalidade, "dispensa")
        self.assertEqual(dto.valor_estimado, Decimal("130710.18"))
        self.assertEqual(dto.status, "publicada")
        self.assertEqual(dto.data_encerramento_propostas.date(), amanha)
        self.assertEqual(ad.erros, [])

    def test_erro_em_um_municipio_nao_derruba_os_outros(self):
        amanha = HOJE + timedelta(days=1)

        def handler(url, params):
            if url.endswith("/prefeituras"):
                return FakeResp([{"id": 1, "nome": "A"}, {"id": 2, "nome": "B"}])
            if url.endswith("/licitacoes/1"):
                return FakeResp("erro", status=500)
            if url.endswith("/licitacoes/2"):
                return FakeResp([{"link": f"{amanha:%Y%m%d}"}])
            return FakeResp([{"objeto": "x", "idLicitacaoWeb": 9, "modalidade": "Pregão"}])

        ad = self._adapter(handler)
        self.assertEqual(len(list(ad.fetch())), 1)
        self.assertEqual(len(ad.erros), 1)

    def test_item_sem_id_ou_objeto_e_ignorado(self):
        ad = self._adapter(lambda u, p: FakeResp([]))
        self.assertIsNone(ad.normalize({"_municipio": "A", "_dia": "2026-10-14", "objeto": "x"}))
        self.assertIsNone(ad.normalize({"_municipio": "A", "_dia": "2026-10-14", "idLicitacaoWeb": 1}))


class TCEMATests(unittest.TestCase):
    def _item(self, **over):
        base = {
            "id": "abc-123", "cnpjProcedimento": "06029235000192",
            "numeroProcedimento": 25, "anoProcedimento": 2026,
            "nomeTipoProcedimento": "Pregão Eletrônico", "objeto": "Aquisição de merenda",
            "dataPublicacao": "2026-09-01", "dataSessao": (HOJE + timedelta(days=5)).isoformat(),
            "valor": 1000.5, "nomeEnteProcedimento": "Bacabal",
            "nomeEntidadeProcedimento": "SAAE", "link_documento": "https://drive.google.com/x",
            "dataEnvio": "2026-09-02T10:00:00", "idContratacaoPncp": None,
        }
        base.update(over)
        return base

    def test_normalize_municipal(self):
        ad = TCEMAAdapter(session=FakeSession(lambda u, p: None), sleep=nosleep)
        dto = ad.normalize(self._item())
        self.assertEqual(dto.id_externo, "abc-123")
        self.assertEqual(dto.orgao.cnpj, "06.029.235/0001-92")
        self.assertEqual((dto.orgao.esfera, dto.uf, dto.municipio), ("municipal", "MA", "Bacabal"))
        self.assertEqual(dto.numero, "25/2026")
        self.assertEqual(dto.modalidade, "pregao")
        self.assertEqual(dto.status, "publicada")

    def test_estadual_e_encerrada(self):
        ad = TCEMAAdapter(session=FakeSession(lambda u, p: None), sleep=nosleep)
        dto = ad.normalize(self._item(nomeEnteProcedimento="Estado do Maranhão", dataSessao="2020-01-01"))
        self.assertEqual((dto.orgao.esfera, dto.municipio), ("estadual", ""))
        self.assertEqual(dto.status, "encerrada")

    def test_ignora_o_que_ja_esta_no_pncp(self):
        ad = TCEMAAdapter(session=FakeSession(lambda u, p: None), sleep=nosleep)
        self.assertIsNone(ad.normalize(self._item(idContratacaoPncp="06376974000150-1-000066/2025")))
        self.assertIsNotNone(ad.normalize(self._item(idContratacaoPncp="PE 05.2026")))

    def test_pagina_e_incremental(self):
        paginas = {
            0: [self._item(id="a", dataEnvio="2026-10-01T00:00:00"),
                self._item(id="b", dataEnvio="2020-01-01T00:00:00")],
            1: [self._item(id="c", dataEnvio="2026-10-02T00:00:00")],
        }

        def handler(url, params):
            return FakeResp({"content": paginas[params["page"]], "totalPages": 2})

        sess = FakeSession(handler)
        ad = TCEMAAdapter({"intervalo_requisicoes_segundos": 0}, session=sess, sleep=nosleep)
        self.assertEqual([i["id"] for i in ad.fetch()], ["a", "b", "c"])
        ad = TCEMAAdapter({"intervalo_requisicoes_segundos": 0}, session=sess, sleep=nosleep)
        ids = [i["id"] for i in ad.fetch(desde=datetime(2026, 9, 20))]
        self.assertEqual(ids, ["a", "c"])


class TCECETests(unittest.TestCase):
    def _el(self, **over):
        base = {
            "codigo_municipio": "010", "data_realizacao_autuacao_licitacao": "2026-09-10T00:00:00",
            "numero_licitacao": "PE 001/2026", "hora_licitacao": "09:30",
            "data_emissao_edital": None, "modalidade_licitacao": "6",
            "modalidade_processo_administrativo": "N",
            "descricao_objeto_licitacao": "AQUISIÇÃO DE UNIFORMES", "valor_orcado_estimado": 19321.0,
            "data_realizacao_licitacao": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT00:00:00"),
            "data_homologacao": None, "numero_id_contratacao_pncp": "                         ",
            "descricao_url_plataforma_contratacao": "", "_municipio": "Amontada",
        }
        base.update(over)
        return base

    def test_normalize(self):
        ad = TCECEAdapter(session=FakeSession(lambda u, p: None), sleep=nosleep)
        dto = ad.normalize(self._el())
        self.assertTrue(dto.id_externo.startswith("010-PE 001/2026-20260910-"))
        self.assertEqual(dto.orgao.razao_social, "Prefeitura Municipal de Amontada")
        self.assertEqual((dto.uf, dto.municipio, dto.modalidade), ("CE", "Amontada", "pregao"))
        self.assertEqual(dto.data_abertura.hour, 9)
        self.assertEqual(dto.status, "publicada")
        self.assertEqual(dto.valor_estimado, Decimal("19321.00"))

    def test_modalidades(self):
        self.assertEqual(modalidade_ce("DE 001/2025", "9", "D"), "dispensa")
        self.assertEqual(modalidade_ce("INEX 001/2025", "9", "I"), "inexigibilidade")
        self.assertEqual(modalidade_ce("250201202508", "3", "N"), "concorrencia")
        self.assertEqual(modalidade_ce("080101202503", "6", "N"), "pregao")
        self.assertEqual(modalidade_ce("090101202502", "9", "I"), "inexigibilidade")
        self.assertEqual(modalidade_ce("X1", "9", "N"), "outra")

    def test_homologada_e_pncp(self):
        ad = TCECEAdapter(session=FakeSession(lambda u, p: None), sleep=nosleep)
        self.assertEqual(ad.normalize(self._el(data_homologacao="2026-09-20T00:00:00")).status, "homologada")
        self.assertIsNone(ad.normalize(self._el(numero_id_contratacao_pncp="0658255500017510000032025")))

    def test_fetch_pagina_e_janela(self):
        def handler(url, params):
            if url.endswith("/municipios"):
                return FakeResp({"elements": [
                    {"codigo_municipio": "001", "nome_municipio": "T.C.M."},
                    {"codigo_municipio": "010", "nome_municipio": "AMONTADA"},
                    {"codigo_municipio": "020", "nome_municipio": "QUEBRADA"},
                ]})
            if params["codigo_municipio"] == "020":
                return FakeResp({"__errors__": [{"message": "boom"}]}, status=500)
            n = 1000 if params["$start_index"] == 0 else 2
            return FakeResp({"elements": [self._el() for _ in range(n)]})

        sess = FakeSession(handler)
        ad = TCECEAdapter({"intervalo_requisicoes_segundos": 0, "janela_inicial_dias": 30},
                          session=sess, sleep=nosleep)
        itens = list(ad.fetch())
        self.assertEqual(len(itens), 1002)
        self.assertEqual(itens[0]["_municipio"], "Amontada")
        self.assertEqual(len(ad.erros), 1)  # QUEBRADA
        consultas = [p for u, p in sess.chamadas if "processos" in u and p["codigo_municipio"] == "010"]
        self.assertEqual(consultas[0]["data_inicio"], f"{HOJE - timedelta(days=30):%Y%m%d}")
        self.assertEqual(consultas[0]["data_fim"], f"{HOJE:%Y%m%d}")
        # T.C.M. nunca é consultado
        self.assertFalse(any(p.get("codigo_municipio") == "001" for _, p in sess.chamadas))

    def test_incremental_volta_a_folga(self):
        def handler(url, params):
            if url.endswith("/municipios"):
                return FakeResp({"elements": [{"codigo_municipio": "010", "nome_municipio": "A"}]})
            return FakeResp({"elements": []})

        sess = FakeSession(handler)
        ad = TCECEAdapter({"intervalo_requisicoes_segundos": 0, "folga_dias": 45}, session=sess, sleep=nosleep)
        list(ad.fetch(desde=datetime(2026, 10, 1)))
        consulta = [p for u, p in sess.chamadas if "processos" in u][0]
        self.assertEqual(consulta["data_inicio"], "20250817".replace("2025", "2026"))


if __name__ == "__main__":
    unittest.main()
