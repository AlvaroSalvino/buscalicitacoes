from django.db import migrations, models

LOTE = 5000


def preencher(apps, schema_editor):
    """
    Preenche texto_busca das licitações existentes. SQL direto em lotes
    (executemany): ~10x mais rápido que bulk_update em ORM, que gera um CASE
    gigante por lote e levava minutos com centenas de milhares de linhas.
    """
    from licitacoes.textos import texto_busca

    cursor = schema_editor.connection.cursor()
    ultimo = 0
    while True:
        cursor.execute(
            "SELECT l.id, l.objeto, o.razao_social "
            "FROM licitacoes_licitacao l JOIN licitacoes_orgao o ON o.id = l.orgao_id "
            "WHERE l.id > %s ORDER BY l.id LIMIT %s",
            [ultimo, LOTE],
        )
        linhas = cursor.fetchall()
        if not linhas:
            break
        cursor.executemany(
            "UPDATE licitacoes_licitacao SET texto_busca = %s WHERE id = %s",
            [(texto_busca(objeto, razao), pk) for pk, objeto, razao in linhas],
        )
        ultimo = linhas[-1][0]


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
