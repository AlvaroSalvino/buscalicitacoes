from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Convite

User = get_user_model()
SENHA = "Senha-forte-123"


def bearer(client, username, password=SENHA):
    r = client.post(reverse("token-obtain"), {"username": username, "password": password})
    return {"HTTP_AUTHORIZATION": f"Bearer {r.json()['access']}"}


class AppFechadoTests(TestCase):
    def test_nada_e_publico(self):
        for nome in ("licitacao-list", "alerta-list", "notificacao-list", "auth-me",
                     "push-public-key", "convite-list"):
            r = self.client.get(reverse(nome))
            self.assertEqual(r.status_code, 401, nome)

    def test_cadastro_sem_convite_e_recusado(self):
        r = self.client.post(reverse("auth-register"), {
            "username": "x", "password": SENHA, "token": "inventado",
        })
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(username="x").exists())

    def test_docs_da_api_exigem_staff(self):
        self.assertIn(self.client.get(reverse("schema")).status_code, (401, 403))
        User.objects.create_user("normal", "n@x.com", SENHA)
        self.client.login(username="normal", password=SENHA)
        self.assertEqual(self.client.get(reverse("schema")).status_code, 403)
        User.objects.create_superuser("adm", "a@x.com", SENHA)
        self.client.login(username="adm", password=SENHA)
        self.assertEqual(self.client.get(reverse("schema")).status_code, 200)


class ConviteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@x.com", SENHA)
        self.h = bearer(self.client, "admin")

    def _convidar(self, email="ana@x.com"):
        return self.client.post(
            reverse("convite-list"), {"email": email},
            content_type="application/json", **self.h,
        )

    def test_fluxo_completo(self):
        r = self._convidar()
        self.assertEqual(r.status_code, 201, r.content)
        dados = r.json()
        self.assertTrue(dados["email_enviado"])
        self.assertIn("/#/cadastro?token=", dados["link"])
        token = dados["link"].split("token=")[1]

        # e-mail enviado ao convidado, com o link
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ana@x.com"])
        self.assertIn(token, mail.outbox[0].body)

        # só o hash fica no banco
        convite = Convite.objects.get()
        self.assertNotEqual(convite.token_hash, token)

        # página de cadastro valida o token e mostra o e-mail
        r = self.client.get(reverse("convite-validar"), {"token": token})
        self.assertEqual(r.json(), {"email": "ana@x.com"})

        # cadastro: e-mail vem do convite (o cliente não escolhe)
        r = self.client.post(reverse("auth-register"), {
            "token": token, "username": "ana", "password": SENHA,
            "email": "outro@x.com", "first_name": "Ana",
        })
        self.assertEqual(r.status_code, 201, r.content)
        ana = User.objects.get(username="ana")
        self.assertEqual(ana.email, "ana@x.com")
        self.assertFalse(ana.is_superuser)
        self.assertFalse(ana.is_staff)

        # uso único
        r = self.client.post(reverse("auth-register"), {
            "token": token, "username": "ana2", "password": SENHA,
        })
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            self.client.get(reverse("convite-validar"), {"token": token}).status_code, 404,
        )
        # e a nova conta já entra
        h = bearer(self.client, "ana")
        me = self.client.get(reverse("auth-me"), **h).json()
        self.assertFalse(me["is_superuser"])

    def test_so_superusuario_convida(self):
        User.objects.create_user("comum", "c@x.com", SENHA)
        h = bearer(self.client, "comum")
        r = self.client.post(
            reverse("convite-list"), {"email": "a@x.com"},
            content_type="application/json", **h,
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get(reverse("convite-list"), **h).status_code, 403)
        self.assertEqual(Convite.objects.count(), 0)

    def test_email_ja_cadastrado_e_reenvio_invalida_anterior(self):
        User.objects.create_user("bia", "bia@x.com", SENHA)
        self.assertEqual(self._convidar("BIA@x.com").status_code, 400)

        t1 = self._convidar("novo@x.com").json()["link"].split("token=")[1]
        t2 = self._convidar("novo@x.com").json()["link"].split("token=")[1]
        self.assertEqual(Convite.objects.filter(email="novo@x.com").count(), 1)
        self.assertEqual(self.client.get(reverse("convite-validar"), {"token": t1}).status_code, 404)
        self.assertEqual(self.client.get(reverse("convite-validar"), {"token": t2}).status_code, 200)

    def test_expirado_e_revogado(self):
        token = self._convidar().json()["link"].split("token=")[1]
        Convite.objects.update(expira_em=timezone.now() - timedelta(minutes=1))
        r = self.client.post(reverse("auth-register"), {
            "token": token, "username": "x", "password": SENHA,
        })
        self.assertEqual(r.status_code, 400)

        c = Convite.objects.get()
        r = self.client.delete(reverse("convite-detail", args=[c.pk]), **self.h)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(Convite.objects.count(), 0)

    def test_senha_fraca_nao_consome_convite(self):
        token = self._convidar().json()["link"].split("token=")[1]
        r = self.client.post(reverse("auth-register"), {
            "token": token, "username": "ana", "password": "123",
        })
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            self.client.get(reverse("convite-validar"), {"token": token}).status_code, 200,
        )

    def test_listagem_mostra_status(self):
        self._convidar("a@x.com")
        r = self.client.get(reverse("convite-list"), **self.h)
        self.assertEqual(r.json()[0]["status"], "pendente")
        self.assertNotIn("token", r.json()[0])
        self.assertNotIn("link", r.json()[0])
