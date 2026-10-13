import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Fonte',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=150)),
                ('tipo_adapter', models.CharField(help_text="Chave do adapter no registry (ex: 'pncp').", max_length=50)),
                ('ativo', models.BooleanField(default=True)),
                ('config', models.JSONField(blank=True, default=dict, help_text='Configuracao especifica da fonte (UF, endpoint, credenciais etc).')),
                ('intervalo_sync_minutos', models.PositiveIntegerField(default=60)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['nome'],
            },
        ),
        migrations.CreateModel(
            name='SincronizacaoLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('em_execucao', 'Em execução'), ('sucesso', 'Sucesso'), ('erro', 'Erro'), ('parcial', 'Parcial (com erros)')], default='em_execucao', max_length=20)),
                ('iniciado_em', models.DateTimeField(auto_now_add=True)),
                ('finalizado_em', models.DateTimeField(blank=True, null=True)),
                ('itens_importados', models.PositiveIntegerField(default=0)),
                ('erro_detalhe', models.TextField(blank=True, default='')),
                ('fonte', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='integracoes.fonte')),
            ],
            options={
                'ordering': ['-iniciado_em'],
            },
        ),
        migrations.AddIndex(
            model_name='sincronizacaolog',
            index=models.Index(fields=['fonte', '-iniciado_em'], name='integracoes_fonte_i_9f0a01_idx'),
        ),
    ]
