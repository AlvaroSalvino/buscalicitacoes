from pathlib import Path

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

STATIC_APP = Path(__file__).resolve().parent / "static" / "app"


def _versao_assets():
    """
    Muda a cada deploy (mtime dos arquivos do app). Entra na URL de app.js/app.css
    para furar o cache do service worker: sem isso, a 1ª abertura após um deploy
    ainda mostraria a versão antiga.
    """
    arquivos = [STATIC_APP / n for n in ("app.js", "app.css", "sw.js")]
    return int(max((a.stat().st_mtime for a in arquivos if a.exists()), default=0))


@never_cache
def index(request):
    """Shell do PWA; a navegação entre telas é por hash (#/...)."""
    return render(request, "core/app.html", {"asset_version": _versao_assets()})


def _arquivo(nome, content_type):
    return HttpResponse((STATIC_APP / nome).read_bytes(), content_type=content_type)


@never_cache
def service_worker(request):
    """O SW precisa ser servido da raiz para controlar o escopo '/'."""
    return _arquivo("sw.js", "application/javascript; charset=utf-8")


def manifest(request):
    return _arquivo("manifest.webmanifest", "application/manifest+json")
