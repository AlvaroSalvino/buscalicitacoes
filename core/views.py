from pathlib import Path

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

STATIC_APP = Path(__file__).resolve().parent / "static" / "app"


def index(request):
    """Shell do PWA; a navegação entre telas é por hash (#/...)."""
    return render(request, "core/app.html")


def _arquivo(nome, content_type):
    return HttpResponse((STATIC_APP / nome).read_bytes(), content_type=content_type)


@never_cache
def service_worker(request):
    """O SW precisa ser servido da raiz para controlar o escopo '/'."""
    return _arquivo("sw.js", "application/javascript; charset=utf-8")


def manifest(request):
    return _arquivo("manifest.webmanifest", "application/manifest+json")
