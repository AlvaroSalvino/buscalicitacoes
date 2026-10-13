import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'buscalicitacoes.settings')

app = Celery('buscalicitacoes')

# Usa as configs do settings.py com prefixo CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Descobre tasks.py automaticamente em cada app instalado
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
