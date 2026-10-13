from django.db import migrations


def criar_fonte_pncp(apps, schema_editor):
    Fonte = apps.get_model('integracoes', 'Fonte')
    if not Fonte.objects.filter(tipo_adapter='pncp').exists():
        Fonte.objects.create(
            nome='PNCP - Portal Nacional de Contratações Públicas',
            tipo_adapter='pncp',
            ativo=True,
            intervalo_sync_minutos=60,
            config={},  # usa os padrões do adapter; veja integracoes/adapters/pncp.py
        )


class Migration(migrations.Migration):

    dependencies = [
        ('integracoes', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(criar_fonte_pncp, migrations.RunPython.noop),
    ]
