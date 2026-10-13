from django.test import TestCase

from integracoes.adapters.base import LicitacaoDTO, OrgaoDTO
from integracoes.models import Fonte
from integracoes.services import salvar_licitacao
from licitacoes.models import Orgao


def _dto(ext, razao, municipio):
    return LicitacaoDTO(
        id_externo=ext,
        orgao=OrgaoDTO(cnpj=None, razao_social=razao, esfera="municipal", uf="PI", municipio=municipio),
        objeto="objeto", uf="PI", municipio=municipio,
    )


class OrgaoSemCnpjTests(TestCase):
    def setUp(self):
        self.fonte = Fonte.objects.create(nome="TCE-PI", tipo_adapter="tce_pi")

    def test_orgaos_sem_cnpj_nao_sao_fundidos(self):
        l1, _ = salvar_licitacao(self.fonte, _dto("1", "CAMARA DE ALTOS", "Altos"))
        l2, _ = salvar_licitacao(self.fonte, _dto("2", "PREFEITURA DE ALTOS", "Altos"))
        l3, _ = salvar_licitacao(self.fonte, _dto("3", "CAMARA DE ALTOS", "Altos"))
        self.assertNotEqual(l1.orgao_id, l2.orgao_id)
        self.assertEqual(l1.orgao_id, l3.orgao_id)
        self.assertEqual(Orgao.objects.filter(cnpj__isnull=True).count(), 2)

    def test_fontes_tce_criadas_pela_migracao(self):
        tipos = set(Fonte.objects.values_list("tipo_adapter", flat=True))
        self.assertTrue({"tce_ma", "tce_ce"} <= tipos)
