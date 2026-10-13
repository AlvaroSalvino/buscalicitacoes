from django.test import TestCase
from django.urls import reverse


class PWATests(TestCase):
    def test_shell_referencia_manifest_e_assets(self):
        r = self.client.get(reverse("app"))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('rel="manifest"', body)
        self.assertIn("/static/app/app.js", body)
        self.assertIn('name="theme-color"', body)

    def test_manifest(self):
        r = self.client.get(reverse("pwa-manifest"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/manifest+json")
        data = r.json()
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["theme_color"], "#1e3a6b")
        self.assertTrue(any(i["purpose"] == "maskable" for i in data["icons"]))

    def test_service_worker_na_raiz_sem_cache(self):
        r = self.client.get(reverse("pwa-sw"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r["Content-Type"])
        self.assertIn("no-cache", r["Cache-Control"])
        self.assertIn(b"addEventListener", r.content)
