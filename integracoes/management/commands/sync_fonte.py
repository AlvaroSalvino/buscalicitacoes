from django.core.management.base import BaseCommand, CommandError

from integracoes.models import Fonte
from integracoes.services import executar_sync


class Command(BaseCommand):
    help = (
        "Executa a sincronização de uma Fonte de forma síncrona (sem Celery)."
    )

    def add_arguments(self, parser):
        parser.add_argument("fonte_id", type=int)
        parser.add_argument(
            "--completo", action="store_true",
            help=(
    "Ignora a janela incremental e refaz o backfill inteiro via "
                "/contratacoes/publicacao (data de publicação, não de "
                "atualização). Recomendado ao corrigir o mapeamento de campos "
                "do adapter, para reclassificar o histórico já importado. "
                "Cobre 'janela_inicial_dias' dias (padrão 3) - para "
                "reclassificar tudo, aumente esse valor na config da Fonte "
                "antes de rodar, ex: {\"janela_inicial_dias\": 200}."
            ),
        )

    def handle(self, *args, **opts):
        try:
            fonte = Fonte.objects.get(pk=opts["fonte_id"])
        except Fonte.DoesNotExist:
            raise CommandError("Fonte não encontrada.")
        log, novas = executar_sync(fonte, forcar_completo=opts["completo"])
        self.stdout.write(self.style.SUCCESS(
            f"{log.get_status_display()}: {log.itens_importados} itens "
            f"({len(novas)} novos). Log #{log.pk}"
        ))
        if log.erro_detalhe:
            self.stdout.write(self.style.WARNING(log.erro_detalhe))
