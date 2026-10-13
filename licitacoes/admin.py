from django.contrib import admin

from .models import Licitacao, Orgao


@admin.register(Orgao)
class OrgaoAdmin(admin.ModelAdmin):
    list_display = ("razao_social", "esfera", "uf", "municipio", "cnpj")
    list_filter = ("esfera", "uf")
    search_fields = ("razao_social", "cnpj", "municipio")


@admin.register(Licitacao)
class LicitacaoAdmin(admin.ModelAdmin):
    list_display = (
        "numero", "orgao", "uf", "modalidade", "status",
        "valor_estimado", "data_publicacao", "data_encerramento_propostas",
    )
    list_filter = ("status", "modalidade", "fonte", "uf")
    search_fields = ("numero", "id_externo", "objeto", "orgao__razao_social")
    autocomplete_fields = ("orgao",)
    date_hierarchy = "data_publicacao"
    raw_id_fields = ("licitacao_matriz",)
