"""Atualização automática: agenda do beat, tarefas diárias e painel de status."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from buscalicitacoes.celery import app as celery_app
from django.conf import settings
from integracoes import tasks
from integracoes.models import Fonte, SincronizacaoLog
from licitacoes.models import Licitacao, Orgao

User = get_user_model()


class AgendaTests(TestCase):
    def test_toda_tarefa_agendada_existe(self):
        celery_app.loader.import_default_modules()
        for nome, cfg in settings.CELERY_BEAT_SCHEDULE.items():
            self.assertIn(cfg["task"], celery_app.tasks, nome)

    def test_fila_propria_para_nao_colidir_no_redis_compartilhado(self):
        self.assertEqual(celery_app.conf.task_default_queue, settings.CELERY_TASK_DEFAULT_QUEUE)
        self.assertTrue(
            celery_app.conf.broker_transport_options.get("global_keyprefix")
        )


class TarefasDiariasTests(TestCase):
    def setUp(self):
        self.fonte = Fonte.objects.create(nome="PNCP", tipo_adapter="pncp", intervalo_sync_minutos=60)
        self.orgao = Orgao.objects.create(razao_social="O", esfera="municipal", uf="PI")
        self.agora = timezone.now()

    def _lic(self, ext, status, encerramento):
        return Licitacao.objects.create(
            orgao=self.orgao, fonte=self.fonte, id_externo=ext, objeto="obj",
            status=status, data_encerramento_propostas=encerramento,
        )

    def test_encerrar_vencidas(self):
        vencida = self._lic("1", "aberta", self.agora - timedelta(days=1))
        vencida2 = self._lic("2", "publicada", self.agora - timedelta(hours=1))
        futura = self._lic("3", "aberta", self.agora + timedelta(days=2))
        sem_prazo = self._lic("4", "publicada", None)
        suspensa = self._lic("5", "suspensa", self.agora - timedelta(days=5))

        self.assertEqual(tasks.encerrar_vencidas(), {"encerradas": 2})
        for lic, esperado in [(vencida, "encerrada"), (vencida2, "encerrada"), (futura, "aberta"),
                              (sem_prazo, "publicada"), (suspensa, "suspensa")]:
            lic.refresh_from_db()
            self.assertEqual(lic.status, esperado, lic.id_externo)

    def test_limpar_logs_preserva_ultimo_sucesso_e_em_execucao(self):
        antigo = self.agora - timedelta(days=200)

        def log(status, quando):
            obj = SincronizacaoLog.objects.create(fonte=self.fonte, status=status)
            SincronizacaoLog.objects.filter(pk=obj.pk).update(iniciado_em=quando)
            return obj

        l_erro = log("erro", antigo)
        l_suc_velho = log("sucesso", antigo - timedelta(days=5))
        l_suc_ultimo = log("sucesso", antigo)            # último sucesso da fonte: fica
        l_rodando = log("em_execucao", antigo)
        l_recente = log("erro", self.agora - timedelta(days=1))

        res = tasks.limpar_logs_antigos()
        self.assertEqual(res, {"apagados": 2})
        restam = set(SincronizacaoLog.objects.values_list("pk", flat=True))
        self.assertEqual(restam, {l_suc_ultimo.pk, l_rodando.pk, l_recente.pk})
        self.assertNotIn(l_erro.pk, restam)
        self.assertNotIn(l_suc_velho.pk, restam)


class PainelStatusTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("adm", "a@x.com", "Senha-forte-123")
        self.comum = User.objects.create_user("u", "u@x.com", "Senha-forte-123")
        self.fonte = Fonte.objects.create(nome="PNCP", tipo_adapter="pncp", intervalo_sync_minutos=60)

    @staticmethod
    def _h(user):
        return {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}

    def test_somente_superusuario(self):
        url = reverse("fonte-status")
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, **self._h(self.comum)).status_code, 403)
        self.assertEqual(self.client.get(url, **self._h(self.admin)).status_code, 200)
        r = self.client.post(reverse("fonte-sincronizar", args=[self.fonte.pk]), **self._h(self.comum))
        self.assertEqual(r.status_code, 403)

    def _minha(self):
        r = self.client.get(reverse("fonte-status"), **self._h(self.admin)).json()
        return next(f for f in r if f["id"] == self.fonte.pk)   # a migração já cria outras fontes

    def test_status_em_dia_e_atrasada(self):
        # sem nenhum sync e fonte recém-criada: ainda não está atrasada
        d = self._minha()
        self.assertFalse(d["atrasada"])
        self.assertIsNone(d["ultimo"])

        log = SincronizacaoLog.objects.create(
            fonte=self.fonte, status="sucesso", itens_importados=42,
            finalizado_em=timezone.now(),
        )
        d = self._minha()
        self.assertFalse(d["atrasada"])
        self.assertEqual(d["ultimo"]["itens"], 42)
        self.assertIsNotNone(d["proxima_em"])

        # último sucesso há 2 dias (limite = max(3×60 min, 6 h) = 6 h)
        SincronizacaoLog.objects.filter(pk=log.pk).update(
            iniciado_em=timezone.now() - timedelta(days=2),
        )
        self.assertTrue(self._minha()["atrasada"])

        # fonte pausada nunca é "atrasada"
        Fonte.objects.filter(pk=self.fonte.pk).update(ativo=False)
        self.assertFalse(self._minha()["atrasada"])

    def test_sincronizar_agora_enfileira(self):
        with mock.patch("integracoes.views.sync_fonte.delay") as delay:
            r = self.client.post(reverse("fonte-sincronizar", args=[self.fonte.pk]), **self._h(self.admin))
        self.assertEqual(r.status_code, 202)
        delay.assert_called_once_with(self.fonte.pk)

    def test_sincronizar_sem_broker_devolve_503(self):
        with mock.patch("integracoes.views.sync_fonte.delay", side_effect=OSError("redis")):
            r = self.client.post(reverse("fonte-sincronizar", args=[self.fonte.pk]), **self._h(self.admin))
        self.assertEqual(r.status_code, 503)
        r = self.client.post(reverse("fonte-sincronizar", args=[9999]), **self._h(self.admin))
        self.assertEqual(r.status_code, 404)
