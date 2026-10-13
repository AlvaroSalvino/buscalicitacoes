from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from integracoes import tasks as integ_tasks
from integracoes.models import Fonte
from licitacoes.models import Licitacao, Orgao

from .models import Alerta, Notificacao, PushSubscription
from .tasks import enviar_emails_pendentes, enviar_push_pendentes, match_licitacoes

User = get_user_model()


def _auth(client, username="ana", password="Senha-forte-123"):
    resp = client.post(
        reverse("token-obtain"), {"username": username, "password": password},
    )
    return {"HTTP_AUTHORIZATION": f"Bearer {resp.json()['access']}"}


class AlertaAPITests(TestCase):
    def setUp(self):
        self.ana = User.objects.create_user("ana", "ana@x.com", "Senha-forte-123")
        self.bia = User.objects.create_user("bia", "bia@x.com", "Senha-forte-123")
        self.h = _auth(self.client, "ana")

    def test_crud_e_isolamento_entre_usuarios(self):
        r = self.client.post(
            reverse("alerta-list"),
            {"nome": "TI SP", "filtros": {"q": "notebook", "uf": ["SP", "RJ"]}},
            content_type="application/json", **self.h,
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["filtros"], {"q": "notebook", "uf": "SP,RJ"})
        alerta_id = r.json()["id"]

        outro = Alerta.objects.create(usuario=self.bia, nome="outro", filtros={"q": "x"})
        lista = self.client.get(reverse("alerta-list"), **self.h).json()
        self.assertEqual(lista["count"], 1)
        r = self.client.get(reverse("alerta-detail", args=[alerta_id]), **self.h)
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("alerta-detail", args=[outro.pk]), **self.h)
        self.assertEqual(r.status_code, 404)

    def test_filtros_invalidos(self):
        for filtros in ({}, {"inexistente": "1"}, {"valor_min": "abc"}):
            r = self.client.post(
                reverse("alerta-list"), {"nome": "x", "filtros": filtros},
                content_type="application/json", **self.h,
            )
            self.assertEqual(r.status_code, 400, filtros)

    def test_resultados_do_alerta(self):
        fonte = Fonte.objects.create(nome="PNCP", tipo_adapter="pncp")
        orgao = Orgao.objects.create(razao_social="O", esfera="municipal", uf="SP")
        Licitacao.objects.create(
            orgao=orgao, fonte=fonte, id_externo="1", objeto="notebooks", uf="SP",
        )
        Licitacao.objects.create(
            orgao=orgao, fonte=fonte, id_externo="2", objeto="merenda", uf="SP",
        )
        alerta = Alerta.objects.create(usuario=self.ana, nome="a", filtros={"q": "notebooks"})
        r = self.client.get(reverse("alerta-resultados", args=[alerta.pk]), **self.h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 1)


class MatchingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", "ana@x.com", "Senha-forte-123")
        self.fonte = Fonte.objects.create(nome="PNCP", tipo_adapter="pncp")
        self.orgao = Orgao.objects.create(
            cnpj="11.222.333/0001-81", razao_social="Prefeitura X",
            esfera="municipal", uf="SP",
        )

    def _lic(self, ext, objeto, uf="SP"):
        return Licitacao.objects.create(
            orgao=self.orgao, fonte=self.fonte, id_externo=ext, objeto=objeto,
            uf=uf, status="aberta", data_publicacao=date(2026, 9, 1),
        )

    def test_match_cria_notificacao_idempotente_e_envia_email(self):
        casa = self._lic("1", "Compra de notebooks", "SP")
        self._lic("2", "Compra de notebooks", "RJ")
        self._lic("3", "Merenda escolar", "SP")
        alerta = Alerta.objects.create(
            usuario=self.user, nome="TI", notificar_email=True,
            filtros={"q": "notebooks", "uf": "SP"},
        )
        Alerta.objects.create(
            usuario=self.user, nome="inativo", ativo=False, filtros={"q": "notebooks"},
        )
        ids = list(Licitacao.objects.values_list("pk", flat=True))

        with mock.patch("alertas.tasks.enviar_emails_pendentes.delay"),                 mock.patch("alertas.tasks.enviar_push_pendentes.delay"):
            r1 = match_licitacoes(ids)
            r2 = match_licitacoes(ids)
        self.assertEqual(r1, {"notificacoes": 1})
        self.assertEqual(r2, {"notificacoes": 0})
        self.assertEqual(
            list(Notificacao.objects.values_list("licitacao_id", flat=True)),
            [casa.pk],
        )

        self.assertEqual(enviar_emails_pendentes(), {"emails": 1})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ana@x.com"])
        self.assertEqual(enviar_emails_pendentes(), {"emails": 0})
        self.assertTrue(Notificacao.objects.get(alerta=alerta).email_enviado)

    def test_sync_fonte_dispara_matching_com_novas(self):
        with mock.patch.object(
            integ_tasks, "executar_sync",
            return_value=(mock.Mock(status="sucesso", pk=1), [10, 11]),
        ), mock.patch("alertas.tasks.match_licitacoes.delay") as delay:
            integ_tasks.sync_fonte(self.fonte.pk)
        delay.assert_called_once_with([10, 11])

    def test_falha_ao_enfileirar_nao_quebra_sync(self):
        with mock.patch.object(
            integ_tasks, "executar_sync",
            return_value=(mock.Mock(status="sucesso", pk=1), [10]),
        ), mock.patch("alertas.tasks.match_licitacoes.delay", side_effect=OSError("redis")):
            r = integ_tasks.sync_fonte(self.fonte.pk)
        self.assertEqual(r["novas"], 1)


class NotificacaoAPITests(TestCase):
    def test_listar_e_marcar_lida(self):
        user = User.objects.create_user("ana", "ana@x.com", "Senha-forte-123")
        fonte = Fonte.objects.create(nome="PNCP", tipo_adapter="pncp")
        orgao = Orgao.objects.create(razao_social="O", esfera="municipal", uf="SP")
        lic = Licitacao.objects.create(
            orgao=orgao, fonte=fonte, id_externo="1", objeto="obj",
        )
        alerta = Alerta.objects.create(usuario=user, nome="a", filtros={"q": "obj"})
        n = Notificacao.objects.create(alerta=alerta, licitacao=lic)
        h = _auth(self.client)

        r = self.client.get(reverse("notificacao-list"), {"lida": "false"}, **h)
        self.assertEqual(r.json()["count"], 1)
        r = self.client.patch(
            reverse("notificacao-detail", args=[n.pk]), {"lida": True},
            content_type="application/json", **h,
        )
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("notificacao-list"), {"lida": "false"}, **h)
        self.assertEqual(r.json()["count"], 0)
        Notificacao.objects.filter(pk=n.pk).update(lida=False)
        r = self.client.post(reverse("notificacao-marcar-todas-lidas"), **h)
        self.assertEqual(r.json(), {"atualizadas": 1})


class PushTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", "ana@x.com", "Senha-forte-123")
        self.h = _auth(self.client)
        self.fonte = Fonte.objects.create(nome="PNCP", tipo_adapter="pncp")
        self.orgao = Orgao.objects.create(razao_social="Prefeitura X", esfera="municipal", uf="SP")

    def _sub(self, endpoint="https://push.example/abc"):
        return self.client.post(
            reverse("push-subscriptions"),
            {"endpoint": endpoint, "keys": {"p256dh": "P", "auth": "A"}},
            content_type="application/json", **self.h,
        )

    def test_chave_publica(self):
        with self.settings(VAPID_PUBLIC_KEY="PUB"):
            r = self.client.get(reverse("push-public-key"), **self.h)
        self.assertEqual(r.json(), {"public_key": "PUB"})
        with self.settings(VAPID_PUBLIC_KEY=""):
            self.assertEqual(self.client.get(reverse("push-public-key"), **self.h).status_code, 503)
        self.assertEqual(self.client.get(reverse("push-public-key")).status_code, 401)

    def test_inscrever_e_remover(self):
        self.assertEqual(self._sub().status_code, 201)
        self.assertEqual(self._sub().status_code, 201)  # idempotente
        self.assertEqual(PushSubscription.objects.count(), 1)
        r = self.client.delete(
            reverse("push-subscriptions"), {"endpoint": "https://push.example/abc"},
            content_type="application/json", **self.h,
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_inscricao_exige_login_e_keys(self):
        r = self.client.post(
            reverse("push-subscriptions"), {"endpoint": "https://x.y/z", "keys": {}},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)
        r = self.client.post(
            reverse("push-subscriptions"), {"endpoint": "https://x.y/z", "keys": {}},
            content_type="application/json", **self.h,
        )
        self.assertEqual(r.status_code, 400)

    def test_envio_agrupa_por_alerta_e_nao_repete(self):
        self._sub()
        alerta = Alerta.objects.create(usuario=self.user, nome="TI", filtros={"q": "x"})
        sem_push = Alerta.objects.create(
            usuario=self.user, nome="mudo", filtros={"q": "x"}, notificar_push=False,
        )
        for i in range(2):
            lic = Licitacao.objects.create(
                orgao=self.orgao, fonte=self.fonte, id_externo=str(i), objeto="obj",
            )
            Notificacao.objects.create(alerta=alerta, licitacao=lic)
            Notificacao.objects.create(alerta=sem_push, licitacao=lic)

        with self.settings(VAPID_PUBLIC_KEY="P", VAPID_PRIVATE_KEY="K"), \
                mock.patch("alertas.push.enviar", return_value=True) as enviar:
            r1 = enviar_push_pendentes()
            r2 = enviar_push_pendentes()
        self.assertEqual(r1, {"push": 1})
        self.assertEqual(r2, {"push": 0})
        self.assertEqual(enviar.call_count, 1)
        payload = enviar.call_args.args[1]
        self.assertEqual(payload["title"], "TI")
        self.assertIn("2 novas", payload["body"])
        self.assertEqual(Notificacao.objects.filter(alerta=sem_push, push_enviado=False).count(), 2)

    def test_sem_vapid_nao_envia(self):
        with self.settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY=""):
            self.assertEqual(enviar_push_pendentes()["push"], 0)

    def test_inscricao_expirada_e_removida(self):
        from pywebpush import WebPushException
        self._sub()
        sub = PushSubscription.objects.get()
        resp = mock.Mock(status_code=410)
        with self.settings(VAPID_PRIVATE_KEY="K"), mock.patch(
            "alertas.push.webpush", side_effect=WebPushException("gone", response=resp),
        ):
            from . import push
            self.assertFalse(push.enviar(sub, {"title": "x"}))
        self.assertEqual(PushSubscription.objects.count(), 0)
