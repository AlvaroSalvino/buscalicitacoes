"""
Testes de service/tasks (precisam de Django):  python manage.py test integracoes
"""
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from integracoes import tasks
from integracoes.adapters.base import BaseAdapter, LicitacaoDTO, OrgaoDTO
from integracoes.models import Fonte, SincronizacaoLog
from integracoes.services import SyncFalhou, executar_sync, salvar_licitacao
from licitacoes.models import Licitacao, Orgao


def dto(id_externo="A", **over):
    base = dict(
        id_externo=id_externo,
        orgao=OrgaoDTO(cnpj="00.394.494/0001-36", razao_social="Ministério X",
                       esfera="federal", uf="AL", municipio="Maceió"),
        objeto="Aquisição de computadores",
        numero="1/2026", modalidade="pregao", valor_estimado=Decimal("100.00"),
        data_abertura=datetime(2026, 9, 20, 8, 0),
        data_encerramento_propostas=datetime(2026, 10, 5, 10, 0),
        status="aberta", link_original="https://exemplo.gov.br/1",
        uf="AL", municipio="Maceió",
    )
    base.update(over)
    return LicitacaoDTO(**base)


class AdapterFalso(BaseAdapter):
    itens = []
    erros_fatia = []
    ultimo_desde = "nao-chamado"

    def fetch(self, desde=None):
        AdapterFalso.ultimo_desde = desde
        self.erros.extend(self.erros_fatia)
        yield from self.itens

    def normalize(self, raw):
        return raw


class BaseTest(TestCase):
    def setUp(self):
        Fonte.objects.all().delete()  # remove a Fonte PNCP criada pela data migration
        self.fonte = Fonte.objects.create(nome="Falsa", tipo_adapter="pncp")
        AdapterFalso.itens, AdapterFalso.erros_fatia = [], []
        patcher = mock.patch("integracoes.services.get_adapter", lambda f: AdapterFalso(f.config))
        patcher.start()
        self.addCleanup(patcher.stop)


class SalvarLicitacaoTests(BaseTest):
    def test_idempotente(self):
        _, criada1 = salvar_licitacao(self.fonte, dto())
        _, criada2 = salvar_licitacao(self.fonte, dto(objeto="Objeto alterado"))
        self.assertTrue(criada1)
        self.assertFalse(criada2)
        self.assertEqual(Licitacao.objects.count(), 1)
        self.assertEqual(Orgao.objects.count(), 1)
        self.assertEqual(Licitacao.objects.get().objeto, "Objeto alterado")

    def test_datas_ficam_aware(self):
        lic, _ = salvar_licitacao(self.fonte, dto())
        self.assertTrue(timezone.is_aware(lic.data_encerramento_propostas))


class ExecutarSyncTests(BaseTest):
    def test_sucesso_e_segunda_execucao_sem_novas(self):
        AdapterFalso.itens = [dto("A"), dto("B")]
        log, novas = executar_sync(self.fonte)
        self.assertEqual(log.status, SincronizacaoLog.Status.SUCESSO)
        self.assertEqual((log.itens_importados, len(novas)), (2, 2))
        self.assertIsNotNone(log.finalizado_em)

        log2, novas2 = executar_sync(self.fonte)
        self.assertEqual((log2.itens_importados, len(novas2)), (2, 0))
        self.assertEqual(Licitacao.objects.count(), 2)

    def test_parcial(self):
        AdapterFalso.itens = [dto("A")]
        AdapterFalso.erros_fatia = ["modalidade=6: falhou"]
        log, _ = executar_sync(self.fonte)
        self.assertEqual(log.status, SincronizacaoLog.Status.PARCIAL)
        self.assertIn("modalidade=6", log.erro_detalhe)

    def test_erro_total_levanta_para_retry(self):
        AdapterFalso.erros_fatia = ["tudo falhou"]
        with self.assertRaises(SyncFalhou):
            executar_sync(self.fonte)
        log = self.fonte.logs.get()
        self.assertEqual(log.status, SincronizacaoLog.Status.ERRO)

    def test_janela_usa_ultimo_sucesso_e_ignora_parcial(self):
        self.assertIsNone(executar_sync(self.fonte) and AdapterFalso.ultimo_desde)  # 1ª vez: None
        AdapterFalso.erros_fatia = ["x"]
        AdapterFalso.itens = [dto("A")]
        executar_sync(self.fonte)  # PARCIAL: não avança a janela
        AdapterFalso.erros_fatia = []
        executar_sync(self.fonte)
        self.assertIsNotNone(AdapterFalso.ultimo_desde)  # já existe um SUCESSO anterior


    def test_forcar_completo_ignora_janela(self):
        executar_sync(self.fonte)  # cria um log de sucesso
        executar_sync(self.fonte, forcar_completo=True)
        self.assertIsNone(AdapterFalso.ultimo_desde)


class AgendarSyncsTests(BaseTest):
    def test_dispara_so_fontes_vencidas(self):
        recente = Fonte.objects.create(nome="Recente", tipo_adapter="pncp", intervalo_sync_minutos=60)
        SincronizacaoLog.objects.create(fonte=recente)  # iniciado agora
        inativa = Fonte.objects.create(nome="Inativa", tipo_adapter="pncp", ativo=False)

        with mock.patch.object(tasks.sync_fonte, "delay") as delay:
            disparadas = tasks.agendar_syncs()

        self.assertEqual(disparadas, [self.fonte.pk])  # sem logs => vencida
        delay.assert_called_once_with(self.fonte.pk)
        self.assertNotIn(inativa.pk, disparadas)
        self.assertNotIn(recente.pk, disparadas)

    def test_marca_logs_orfaos_como_erro(self):
        log = SincronizacaoLog.objects.create(fonte=self.fonte)
        SincronizacaoLog.objects.filter(pk=log.pk).update(
            iniciado_em=timezone.now() - timedelta(hours=3),
        )
        with mock.patch.object(tasks.sync_fonte, "delay"):
            tasks.agendar_syncs()
        log.refresh_from_db()
        self.assertEqual(log.status, SincronizacaoLog.Status.ERRO)
