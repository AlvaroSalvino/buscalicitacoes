from django.db import migrations

FONTES = [
    # (nome, tipo_adapter, intervalo_sync_minutos, config)
    ("TCE-PI - Mural de Licitações (Piauí)", "tce_pi", 120, {}),
    ("TCE-MA - SINC-Contrata (Maranhão)", "tce_ma", 360, {}),
    # Os municípios enviam ao SIM com atraso mensal: sync diário basta.
    ("TCE-CE - SIM (Ceará)", "tce_ce", 1440, {"janela_inicial_dias": 180}),
]


def criar_fontes(apps, schema_editor):
    Fonte = apps.get_model("integracoes", "Fonte")
    for nome, tipo, intervalo, config in FONTES:
        if not Fonte.objects.filter(tipo_adapter=tipo).exists():
            Fonte.objects.create(
                nome=nome, tipo_adapter=tipo, ativo=True,
                intervalo_sync_minutos=intervalo, config=config,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("integracoes", "0003_rename_integracoes_fonte_i_9f0a01_idx_integracoes_fonte_i_72ff68_idx"),
    ]

    operations = [
        migrations.RunPython(criar_fontes, migrations.RunPython.noop),
    ]
