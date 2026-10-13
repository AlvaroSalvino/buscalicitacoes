from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('licitacoes', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='licitacao',
            name='data_encerramento_propostas',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='licitacao',
            name='uf',
            field=models.CharField(blank=True, default='', max_length=2),
        ),
        migrations.AddField(
            model_name='licitacao',
            name='municipio',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AddIndex(
            model_name='licitacao',
            index=models.Index(fields=['data_encerramento_propostas'], name='licitacoes__data_en_5e1d3c_idx'),
        ),
        migrations.AddIndex(
            model_name='licitacao',
            index=models.Index(fields=['uf'], name='licitacoes__uf_c4a9b2_idx'),
        ),
    ]
