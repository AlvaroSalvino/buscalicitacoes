import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('integracoes', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Orgao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cnpj', models.CharField(blank=True, help_text='Formato 00.000.000/0000-00. Pode não vir preenchido em algumas fontes.', max_length=18, null=True, unique=True)),
                ('razao_social', models.CharField(max_length=255)),
                ('esfera', models.CharField(choices=[('federal', 'Federal'), ('estadual', 'Estadual'), ('municipal', 'Municipal')], max_length=20)),
                ('uf', models.CharField(max_length=2)),
                ('municipio', models.CharField(blank=True, default='', max_length=150)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['razao_social'],
            },
        ),
        migrations.CreateModel(
            name='Licitacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('id_externo', models.CharField(help_text='Identificador do registro na fonte de origem.', max_length=100)),
                ('numero', models.CharField(blank=True, default='', max_length=50)),
                ('modalidade', models.CharField(choices=[('pregao', 'Pregão'), ('concorrencia', 'Concorrência'), ('concurso', 'Concurso'), ('leilao', 'Leilão'), ('dialogo_competitivo', 'Diálogo Competitivo'), ('dispensa', 'Dispensa de Licitação'), ('inexigibilidade', 'Inexigibilidade'), ('convite', 'Convite'), ('tomada_precos', 'Tomada de Preços'), ('outra', 'Outra')], default='outra', max_length=30)),
                ('objeto', models.TextField()),
                ('valor_estimado', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('data_publicacao', models.DateField(blank=True, null=True)),
                ('data_abertura', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('publicada', 'Publicada'), ('aberta', 'Aberta para propostas'), ('em_julgamento', 'Em julgamento'), ('homologada', 'Homologada'), ('suspensa', 'Suspensa'), ('revogada', 'Revogada'), ('cancelada', 'Cancelada'), ('encerrada', 'Encerrada')], default='publicada', max_length=20)),
                ('link_original', models.URLField(blank=True, default='', max_length=500)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('fonte', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='licitacoes', to='integracoes.fonte')),
                ('licitacao_matriz', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='duplicatas', to='licitacoes.licitacao')),
                ('orgao', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='licitacoes', to='licitacoes.orgao')),
            ],
            options={
                'ordering': ['-data_publicacao', '-criado_em'],
            },
        ),
        migrations.AddIndex(
            model_name='orgao',
            index=models.Index(fields=['uf'], name='licitacoes__uf_7a1c4b_idx'),
        ),
        migrations.AddIndex(
            model_name='orgao',
            index=models.Index(fields=['esfera'], name='licitacoes__esfera_3b8f92_idx'),
        ),
        migrations.AddIndex(
            model_name='licitacao',
            index=models.Index(fields=['status'], name='licitacoes__status_6d6a3a_idx'),
        ),
        migrations.AddIndex(
            model_name='licitacao',
            index=models.Index(fields=['modalidade'], name='licitacoes__modalid_9e4a17_idx'),
        ),
        migrations.AddIndex(
            model_name='licitacao',
            index=models.Index(fields=['data_abertura'], name='licitacoes__data_ab_2c2b1e_idx'),
        ),
        migrations.AddConstraint(
            model_name='licitacao',
            constraint=models.UniqueConstraint(fields=('fonte', 'id_externo'), name='uniq_licitacao_fonte_id_externo'),
        ),
    ]
