from django.contrib import admin

from .models import Alerta, Notificacao


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ("nome", "usuario", "ativo", "notificar_email", "criado_em")
    list_filter = ("ativo", "notificar_email")
    search_fields = ("nome", "usuario__username", "usuario__email")


@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ("alerta", "licitacao", "lida", "email_enviado", "criado_em")
    list_filter = ("lida", "email_enviado")
    raw_id_fields = ("alerta", "licitacao")
