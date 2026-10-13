from django.contrib import admin

from .models import Convite


@admin.register(Convite)
class ConviteAdmin(admin.ModelAdmin):
    list_display = ("email", "status", "criado_por", "criado_em", "expira_em", "usado_em")
    search_fields = ("email",)
    readonly_fields = ("token_hash", "criado_em", "usado_em", "usuario")
