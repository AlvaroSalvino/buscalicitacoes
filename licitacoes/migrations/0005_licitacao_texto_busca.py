from django.db import migrations, models

LOTE = 2000


def preencher(apps, schema_editor):
    from licitacoes.textos import texto_busca

    Licitacao = apps.get_model("licitacoes", "Licitacao")
    ultimo = 0
    while True:
        lote = list(
            Licitacao.objects.filter(pk__gt=ultimo)
            .select_related("orgao").order_by("pk")[:LOTE]
        )
        if not lote:
            break
        for lic in lote:
            lic.texto_busca = texto_busca(lic.objeto, lic.orgao.razao_social)
        Licitacao.objects.bulk_update(lote, ["texto_busca"])
        ultimo = lote[-1].pk


class Migration(migrations.Migration):

    dependencies = [
        ("licitacoes", "0004_merge_20260928_1819"),
    ]

    operations = [
        migrations.AddField(
            model_name="licitacao",
            name="texto_busca",
            field=models.TextField(blank=True, default="", editable=False),
        ),
        migrations.RunPython(preencher, migrations.RunPython.noop),
    ]
