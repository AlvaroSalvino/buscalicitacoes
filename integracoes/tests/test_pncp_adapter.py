"""
Testes do PNCPAdapter. Sem Django e sem rede: usam uma sessão HTTP falsa.
Rodam com:  python -m unittest integracoes.tests.test_pncp_adapter
"""
import unittest
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from integracoes.adapters import AdapterConfigError, get_adapter
from integracoes.adapters.pncp import PNCPAdapter

AGORA = datetime(2026, 9, 27, 12, 0)


class AdapterFixo(PNCPAdapter):
    def _agora(self):
        return AGORA


class FakeResp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.text = str(body)
        self.headers = headers or {}

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._body


class FakeSession:
    """`handler(path, params) -> FakeResp`. Guarda as chamadas feitas."""

    def __init__(self, handler):
        self.handler = handler
        self.chamadas = []

    def get(self, url, params=None, timeout=None):
        path = url.split("/api/consulta/v1", 1)[1]
        self.chamadas.append((path, dict(params or {})))
        return self.handler(path, dict(params or {}))


def raw_exemplo(**over):
    base = {
        "numeroControlePNCP": "00394494000136-1-000616/2024",
        "modalidadeId": 6,
        "anoCompra": 2024,
        "sequencialCompra": 616,
        "orgaoEntidade": {
            "cnpj": "00394494000136",
            "razaoSocial": "MINISTERIO DA JUSTICA E SEGURANCA PUBLICA",
            "poderId": "E", "esferaId": "F",
        },
        "dataPublicacaoPncp": "2024-06-25T07:09:09",
        "numeroCompra": "90005",
        "unidadeOrgao": {"ufSigla": "AL", "municipioNome": "Maceió", "codigoIbge": "2704302"},
        "objetoCompra": "Aquisição de material de consumo",
        "valorTotalEstimado": 150000.5,
        "dataAberturaProposta": "2026-09-20T08:00:00",
        "dataEncerramentoProposta": "2026-10-05T10:00:00",
        "situacaoCompraId": 1,
        "linkSistemaOrigem": "https://compras.exemplo.gov.br/edital/1",
    }
    base.update(over)
    return base


def envelope(registros, restantes=0, total_paginas=1):
    return FakeResp(200, {
        "data": registros, "totalRegistros": len(registros),
        "totalPaginas": total_paginas, "numeroPagina": 1,
        "paginasRestantes": restantes, "empty": not registros,
    })


def adapter(handler, **config):
    cfg = {"modalidades": [6], "backfill_propostas_abertas": False}
    cfg.update(config)
    esperas = []
    a = AdapterFixo(cfg, session=FakeSession(handler), sleep=esperas.append)
    a.esperas = esperas
    return a


class NormalizeTests(unittest.TestCase):
    def setUp(self):
        self.a = adapter(lambda p, q: envelope([]))

    def test_campos_principais(self):
        dto = self.a.normalize(raw_exemplo())
        self.assertEqual(dto.id_externo, "00394494000136-1-000616/2024")
        self.assertEqual(dto.orgao.cnpj, "00.394.494/0001-36")
        self.assertEqual(dto.orgao.esfera, "federal")
        self.assertEqual(dto.uf, "AL")
        self.assertEqual(dto.municipio, "Maceió")
        self.assertEqual(dto.modalidade, "pregao")
        self.assertEqual(dto.numero, "90005/2024")
        self.assertEqual(dto.valor_estimado, Decimal("150000.50"))
        self.assertEqual(dto.data_publicacao, date(2024, 6, 25))
        self.assertEqual(dto.data_abertura, datetime(2026, 9, 20, 8, 0))
        self.assertEqual(dto.data_encerramento_propostas, datetime(2026, 10, 5, 10, 0))
        self.assertEqual(dto.link_original, "https://compras.exemplo.gov.br/edital/1")

    def test_sem_cnpj_ou_sem_objeto_e_ignorado(self):
        self.assertIsNone(self.a.normalize(raw_exemplo(orgaoEntidade={"razaoSocial": "X"})))
        self.assertIsNone(self.a.normalize(raw_exemplo(objetoCompra="  ")))

    def test_id_externo_fallback(self):
        dto = self.a.normalize(raw_exemplo(numeroControlePNCP=None))
        self.assertEqual(dto.id_externo, "00394494000136-1-000616/2024")

    def test_status(self):
        n = self.a.normalize
        self.assertEqual(n(raw_exemplo()).status, "aberta")
        self.assertEqual(n(raw_exemplo(dataAberturaProposta="2026-10-01T08:00:00")).status, "publicada")
        self.assertEqual(n(raw_exemplo(dataEncerramentoProposta="2026-09-01T08:00:00")).status, "encerrada")
        self.assertEqual(n(raw_exemplo(situacaoCompraId=2)).status, "revogada")
        self.assertEqual(n(raw_exemplo(situacaoCompraId=3)).status, "cancelada")
        self.assertEqual(n(raw_exemplo(situacaoCompraId=4)).status, "suspensa")
        sem_datas = raw_exemplo(dataAberturaProposta=None, dataEncerramentoProposta=None)
        self.assertEqual(n(sem_datas).status, "publicada")

    def test_modalidades(self):
        n = self.a.normalize
        self.assertEqual(n(raw_exemplo(modalidadeId=13)).modalidade, "leilao")
        self.assertEqual(n(raw_exemplo(modalidadeId=8)).modalidade, "dispensa")
        self.assertEqual(n(raw_exemplo(modalidadeId=10)).modalidade, "manifestacao_interesse")
        self.assertEqual(n(raw_exemplo(modalidadeId=11)).modalidade, "pre_qualificacao")
        self.assertEqual(n(raw_exemplo(modalidadeId=12)).modalidade, "credenciamento")
        self.assertEqual(n(raw_exemplo(modalidadeId=999)).modalidade, "outra")

    def test_link_invalido_cai_no_portal_pncp(self):
        dto = self.a.normalize(raw_exemplo(linkSistemaOrigem="sem link"))
        self.assertEqual(dto.link_original, "https://pncp.gov.br/app/editais/00394494000136/2024/616")

    def test_valor_nulo_zero_ou_fora_do_limite(self):
        self.assertIsNone(self.a.normalize(raw_exemplo(valorTotalEstimado=None)).valor_estimado)
        self.assertIsNone(self.a.normalize(raw_exemplo(valorTotalEstimado=0)).valor_estimado)
        self.assertIsNone(self.a.normalize(raw_exemplo(valorTotalEstimado=10 ** 13)).valor_estimado)

    def test_esfera_distrital_vira_estadual(self):
        org = dict(raw_exemplo()["orgaoEntidade"], esferaId="D")
        self.assertEqual(self.a.normalize(raw_exemplo(orgaoEntidade=org)).orgao.esfera, "estadual")


class FetchTests(unittest.TestCase):
    def test_paginacao_e_parametros(self):
        def handler(path, q):
            if q["pagina"] == 1:
                return envelope([raw_exemplo(numeroControlePNCP="A")], restantes=1, total_paginas=2)
            return envelope([raw_exemplo(numeroControlePNCP="B")], restantes=0, total_paginas=2)

        a = adapter(handler)
        itens = list(a.fetch(desde=datetime(2026, 9, 20, 3, 0)))
        self.assertEqual([i["numeroControlePNCP"] for i in itens], ["A", "B"])
        path, q = a.session.chamadas[0]
        self.assertEqual(path, "/contratacoes/atualizacao")  # incremental: por data de atualização
        self.assertEqual(q["dataInicial"], "20260920")
        self.assertEqual(q["dataFinal"], "20260927")
        self.assertEqual(q["codigoModalidadeContratacao"], 6)
        self.assertEqual(q["tamanhoPagina"], 50)
        self.assertEqual([c[1]["pagina"] for c in a.session.chamadas], [1, 2])
        self.assertEqual(a.erros, [])

    def test_primeira_execucao_usa_publicacao_e_janela_inicial(self):
        a = adapter(lambda p, q: FakeResp(204))
        self.assertEqual(list(a.fetch(desde=None)), [])
        path, q = a.session.chamadas[0]
        self.assertEqual(path, "/contratacoes/publicacao")  # backfill: por data de publicação
        self.assertEqual(q["dataInicial"], "20260924")  # hoje - 3 dias

    def test_forcar_completo_tambem_usa_publicacao(self):
        # forcar_completo (services.py) chama fetch(desde=None) - mesmo caminho
        # da 1ª execução, mas cobrindo a janela configurada (pode ser bem maior).
        a = adapter(lambda p, q: FakeResp(204), janela_inicial_dias=200)
        list(a.fetch(desde=None))
        path, q = a.session.chamadas[0]
        self.assertEqual(path, "/contratacoes/publicacao")
        self.assertEqual(q["dataInicial"], "20260311")  # hoje - 200 dias

    def test_204_e_lista_vazia(self):
        a = adapter(lambda p, q: FakeResp(204))
        self.assertEqual(list(a.fetch(desde=AGORA)), [])
        self.assertEqual(a.erros, [])

    def test_falha_de_uma_fatia_nao_derruba_as_outras(self):
        def handler(path, q):
            if q["codigoModalidadeContratacao"] == 6:
                return FakeResp(400, "parametro invalido")
            return envelope([raw_exemplo(numeroControlePNCP="OK")])

        a = adapter(handler, modalidades=[6, 8])
        itens = list(a.fetch(desde=AGORA))
        self.assertEqual([i["numeroControlePNCP"] for i in itens], ["OK"])
        self.assertEqual(len(a.erros), 1)
        self.assertIn("modalidade=6", a.erros[0])

    def test_erro_5xx_vira_erro_de_fatia(self):
        a = adapter(lambda p, q: FakeResp(503, "indisponivel"))
        self.assertEqual(list(a.fetch(desde=AGORA)), [])
        self.assertEqual(len(a.erros), 1)

    def test_backfill_de_propostas_abertas_so_na_primeira_execucao(self):
        def handler(path, q):
            if path == "/contratacoes/proposta":
                return envelope([raw_exemplo(numeroControlePNCP="X")])
            return FakeResp(204)

        a = adapter(handler, backfill_propostas_abertas=True, backfill_dias_a_frente=90)
        itens = list(a.fetch(desde=None))
        self.assertEqual(len(itens), 1)
        path, q = a.session.chamadas[0]
        self.assertEqual(path, "/contratacoes/proposta")
        self.assertEqual(q["dataFinal"], "20261226")  # hoje + 90 dias
        self.assertNotIn("dataInicial", q)

        b = adapter(handler, backfill_propostas_abertas=True)
        list(b.fetch(desde=AGORA))
        self.assertNotIn("/contratacoes/proposta", [c[0] for c in b.session.chamadas])

    def test_deduplica_entre_proposta_e_atualizacao(self):
        a = adapter(
            lambda p, q: envelope([raw_exemplo(numeroControlePNCP="MESMO")]),
            backfill_propostas_abertas=True,
        )
        self.assertEqual(len(list(a.fetch(desde=None))), 1)

    def test_filtro_por_uf_gera_uma_chamada_por_uf(self):
        a = adapter(lambda p, q: FakeResp(204), ufs=["pi", "MA"])
        list(a.fetch(desde=AGORA))
        self.assertEqual([c[1]["uf"] for c in a.session.chamadas], ["PI", "MA"])


class RateLimitTests(unittest.TestCase):
    def test_429_espera_e_tenta_de_novo(self):
        respostas = [FakeResp(429), FakeResp(429), envelope([raw_exemplo(numeroControlePNCP="OK")])]
        a = adapter(lambda p, q: respostas.pop(0))
        itens = list(a.fetch(desde=AGORA))
        self.assertEqual([i["numeroControlePNCP"] for i in itens], ["OK"])
        self.assertEqual(a.erros, [])
        self.assertEqual(len(a.session.chamadas), 3)
        self.assertIn(15.0, a.esperas)   # 1ª espera de 429
        self.assertIn(30.0, a.esperas)   # 2ª espera (backoff)

    def test_429_respeita_retry_after(self):
        respostas = [FakeResp(429, headers={"Retry-After": "7"}), FakeResp(204)]
        a = adapter(lambda p, q: respostas.pop(0))
        list(a.fetch(desde=AGORA))
        self.assertIn(7.0, a.esperas)

    def test_429_esgotado_vira_erro_de_fatia(self):
        a = adapter(lambda p, q: FakeResp(429), max_tentativas_429=2)
        self.assertEqual(list(a.fetch(desde=AGORA)), [])
        self.assertEqual(len(a.erros), 1)
        self.assertIn("429", a.erros[0])
        self.assertEqual(len(a.session.chamadas), 3)  # 1 + 2 novas tentativas

    def test_apos_429_o_intervalo_entre_requisicoes_aumenta(self):
        respostas = [FakeResp(429), FakeResp(204)]
        a = adapter(lambda p, q: respostas.pop(0), intervalo_requisicoes_segundos=1.0)
        list(a.fetch(desde=AGORA))
        self.assertEqual(a.intervalo, 2.0)


class ConfigTests(unittest.TestCase):
    def test_tamanho_pagina_invalido(self):
        with self.assertRaises(AdapterConfigError):
            PNCPAdapter({"tamanho_pagina": 5})
        with self.assertRaises(AdapterConfigError):
            PNCPAdapter({"tamanho_pagina": 100})

    def test_registry(self):
        self.assertIsInstance(get_adapter(SimpleNamespace(tipo_adapter="pncp", config={})), PNCPAdapter)
        with self.assertRaises(AdapterConfigError):
            get_adapter(SimpleNamespace(tipo_adapter="nao_existe", config={}))


if __name__ == "__main__":
    unittest.main()
