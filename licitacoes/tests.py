from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from integracoes.models import Fonte
from rest_framework_simplejwt.tokens import AccessToken

from .models import Licitacao, Orgao


class LicitacaoAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user("u", "u@x.com", "Senha-forte-123")
        cls.h = {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}
        cls.fonte = Fonte.objects.create(nome="PNCP", tipo_adapter="pncp")
        cls.orgao_sp = Orgao.objects.create(
            cnpj="11.222.333/0001-81", razao_social="Prefeitura de Campinas",
            esfera="municipal", uf="SP",
        )
        cls.orgao_rj = Orgao.objects.create(
            cnpj="44.555.666/0001-00", razao_social="Hospital Federal RJ",
            esfera="federal", uf="RJ",
        )
        agora = timezone.now()
        cls.l1 = cls._criar(
            "1", cls.orgao_sp, "Aquisição de computadores", "pregao", "aberta",
            "SP", Decimal("50000"), date(2026, 9, 1), agora + timedelta(days=5),
        )
        cls.l2 = cls._criar(
            "2", cls.orgao_rj, "Serviços de limpeza hospitalar", "dispensa",
            "encerrada", "RJ", Decimal("10000"), date(2026, 8, 1),
            agora - timedelta(days=5),
        )
        cls.l3 = cls._criar(
            "3", cls.orgao_sp, "Material de limpeza", "pregao", "aberta",
            "SP", None, date(2026, 9, 15), agora + timedelta(days=1),
        )

    @classmethod
    def _criar(cls, ext, orgao, objeto, modalidade, status, uf, valor, pub, enc):
        return Licitacao.objects.create(
            orgao=orgao, fonte=cls.fonte, id_externo=ext, objeto=objeto,
            modalidade=modalidade, status=status, uf=uf, valor_estimado=valor,
            data_publicacao=pub, data_encerramento_propostas=enc,
        )

    def _ids(self, **params):
        resp = self.client.get(reverse("licitacao-list"), params, **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        return {r["id"] for r in resp.json()["results"]}

    def test_lista_paginada(self):
        resp = self.client.get(reverse("licitacao-list"), {"page_size": 2}, **self.h)
        data = resp.json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["results"]), 2)
        self.assertIsNotNone(data["next"])

    def test_ordenacao_padrao_publicacao_desc(self):
        resp = self.client.get(reverse("licitacao-list"), **self.h)
        ids = [r["id"] for r in resp.json()["results"]]
        self.assertEqual(ids, [self.l3.id, self.l1.id, self.l2.id])

    def test_filtro_uf_multiplo(self):
        self.assertEqual(self._ids(uf="sp"), {self.l1.id, self.l3.id})
        self.assertEqual(self._ids(uf="SP,RJ"), {self.l1.id, self.l2.id, self.l3.id})

    def test_filtro_modalidade_e_status(self):
        self.assertEqual(self._ids(modalidade="dispensa"), {self.l2.id})
        self.assertEqual(self._ids(status="aberta"), {self.l1.id, self.l3.id})

    def test_filtro_valor(self):
        self.assertEqual(self._ids(valor_min="20000"), {self.l1.id})
        self.assertEqual(self._ids(valor_max="20000"), {self.l2.id})

    def test_filtro_data_publicacao(self):
        self.assertEqual(
            self._ids(publicacao_de="2026-09-01", publicacao_ate="2026-09-10"),
            {self.l1.id},
        )

    def test_palavra_chave_todos_os_termos(self):
        self.assertEqual(self._ids(q="limpeza"), {self.l2.id, self.l3.id})
        self.assertEqual(self._ids(q="limpeza hospitalar"), {self.l2.id})
        self.assertEqual(self._ids(q="campinas"), {self.l1.id, self.l3.id})

    def test_abertas(self):
        self.assertEqual(self._ids(abertas="true"), {self.l1.id, self.l3.id})
        self.assertEqual(self._ids(abertas="false"), {self.l2.id})

    def test_cnpj_sem_mascara(self):
        self.assertEqual(self._ids(cnpj="44555666000100"), {self.l2.id})

    def test_ordenacao_por_valor(self):
        resp = self.client.get(reverse("licitacao-list"), {"ordering": "-valor_estimado"}, **self.h)
        self.assertEqual(resp.json()["results"][0]["id"], self.l1.id)

    def test_detalhe(self):
        resp = self.client.get(reverse("licitacao-detail", args=[self.l1.id]), **self.h)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["orgao"]["cnpj"], "11.222.333/0001-81")

    def test_somente_leitura(self):
        resp = self.client.post(reverse("licitacao-list"), {}, **self.h)
        self.assertEqual(resp.status_code, 405)

    def test_palavras_chave_qualquer_uma(self):
        # l1 "computadores", l2 "limpeza hospitalar", l3 "Material de limpeza"
        self.assertEqual(self._ids(palavras="computadores,hospitalar"), {self.l1.id, self.l2.id})
        self.assertEqual(self._ids(palavras="material de limpeza"), {self.l3.id})   # frase
        self.assertEqual(self._ids(palavras="inexistente"), set())
        self.assertEqual(self._ids(palavras="COMPUTADORES, campinas"), {self.l1.id, self.l3.id})  # orgao
        self.assertEqual(self._ids(palavras=" , ,"), {self.l1.id, self.l2.id, self.l3.id})

    def test_palavras_e_outros_filtros_combinam(self):
        self.assertEqual(self._ids(palavras="limpeza,computadores", uf="SP"), {self.l1.id, self.l3.id})

    def test_busca_ignora_acento_e_caixa(self):
        Licitacao.objects.create(
            orgao=self.orgao_sp, fonte=self.fonte, id_externo="9",
            objeto="CONTRATAÇÃO DE ASSESSORIA DE COMUNICAÇÃO INSTITUCIONAL", uf="SP",
        )
        achou = self._ids(palavras="comunicação institucional")
        self.assertEqual(len(achou), 1)
        self.assertEqual(self._ids(q="comunicacao"), achou)
        self.assertEqual(self._ids(palavras="ASSESSORIA"), achou)

    def test_q_com_virgula_e_qualquer_uma(self):
        # espaço = todas; vírgula = qualquer uma
        self.assertEqual(self._ids(q="computadores limpeza"), set())
        self.assertEqual(self._ids(q="computadores, limpeza"), {self.l1.id, self.l2.id, self.l3.id})
        self.assertEqual(self._ids(q="computadores, inexistente"), {self.l1.id})

    def test_termo_curto_so_palavra_inteira(self):
        Licitacao.objects.create(
            orgao=self.orgao_sp, fonte=self.fonte, id_externo="tv1",
            objeto="Produção de conteúdo para a TV Cidade", uf="SP",
        )
        Licitacao.objects.create(
            orgao=self.orgao_sp, fonte=self.fonte, id_externo="tv2",
            objeto="Aquisição de eletrodomésticos e equipamentos", uf="SP",  # 'tv' nao esta como palavra
        )
        achou = self._ids(palavras="tv")
        self.assertEqual(len(achou), 1)

    def test_palavra_curta_so_inteira_ou_plural(self):
        Licitacao.objects.create(
            orgao=self.orgao_sp, fonte=self.fonte, id_externo="c1",
            objeto="Aquisição de materiais para contratos administrativos", uf="SP",
        )
        Licitacao.objects.create(
            orgao=self.orgao_sp, fonte=self.fonte, id_externo="c2",
            objeto="Publicação de atos oficiais", uf="SP",
        )
        achou = self._ids(palavras="atos")  # 'contratos' NAO pode casar
        self.assertEqual(len(achou), 1)
        Licitacao.objects.create(
            orgao=self.orgao_sp, fonte=self.fonte, id_externo="c3",
            objeto="Execução de obras de drenagem", uf="SP",
        )
        self.assertEqual(len(self._ids(palavras="obra")), 1)  # plural simples

    def test_modo_somar_une_palavra_e_modalidade(self):
        # l1 pregao/'computadores' SP, l2 dispensa/'limpeza hospitalar' RJ, l3 pregao/'Material de limpeza' SP
        # todos (padrão): palavra E modalidade
        self.assertEqual(self._ids(palavras="hospitalar", modalidade="pregao"), set())
        # somar: palavra OU modalidade
        self.assertEqual(
            self._ids(palavras="hospitalar", modalidade="pregao", combinar="qualquer"),
            {self.l1.id, self.l2.id, self.l3.id},
        )
        # UF continua restringindo no modo somar
        self.assertEqual(
            self._ids(palavras="hospitalar", modalidade="pregao", combinar="qualquer", uf="SP"),
            {self.l1.id, self.l3.id},
        )
        # só palavra (sem modalidade): igual ao modo restrito
        self.assertEqual(self._ids(palavras="hospitalar", combinar="qualquer"), {self.l2.id})
        # sem critérios de interesse: nada some
        self.assertEqual(self._ids(combinar="qualquer", uf="RJ"), {self.l2.id})

    def test_modo_somar_com_q_lista(self):
        self.assertEqual(
            self._ids(q="computadores, inexistente", modalidade="dispensa", combinar="qualquer"),
            {self.l1.id, self.l2.id},
        )

    def test_exige_login(self):
        r = self.client.get(reverse("licitacao-list"))
        self.assertEqual(r.status_code, 401)
