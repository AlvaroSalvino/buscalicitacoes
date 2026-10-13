from django.db import migrations, models


def zerar_valor_nao_informado(apps, schema_editor):
    Licitacao = apps.get_model('licitacoes', 'Licitacao')
    Licitacao.objects.filter(valor_estimado=0).update(valor_estimado=None)


class Migration(migrations.Migration):

    dependencies = [
        ('licitacoes', '0002_licitacao_localizacao_encerramento'),
    ]

    operations = [
        migrations.AlterField(
            model_name='licitacao',
            name='modalidade',
            field=models.CharField(
                choices=[
                    ('pregao', 'Pregão'),
                    ('concorrencia', 'Concorrência'),
                    ('concurso', 'Concurso'),
                    ('leilao', 'Leilão'),
                    ('dialogo_competitivo', 'Diálogo Competitivo'),
                    ('dispensa', 'Dispensa de Licitação'),
                    ('inexigibilidade', 'Inexigibilidade'),
                    ('convite', 'Convite'),
                    ('tomada_precos', 'Tomada de Preços'),
                    ('credenciamento', 'Credenciamento'),
                    ('pre_qualificacao', 'Pré-qualificação'),
                    ('manifestacao_interesse', 'Manifestação de Interesse'),
                    ('outra', 'Outra'),
                ],
                default='outra',
                max_length=30,
            ),
        ),
        migrations.RunPython(zerar_valor_nao_informado, migrations.RunPython.noop),
    ]
