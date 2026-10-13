from django.contrib import admin

from .models import Fonte, SincronizacaoLog


class SincronizacaoLogInline(admin.TabularInline):
    model = SincronizacaoLog
    extra = 0
    fields = ("status", "iniciado_em", "finalizado_em", "itens_importados")
    readonly_fields = fields
    can_delete = False
    show_change_link = True
    ordering = ("-iniciado_em",)


@admin.action(description="Sincronizar agora (enfileira task no Celery)")
def sincronizar_agora(modeladmin, request, queryset):
    from .tasks import sync_fonte

    for fonte in queryset:
        sync_fonte.delay(fonte.pk)
    modeladmin.message_user(request, f"{queryset.count()} sincronização(ões) enfileirada(s).")


@admin.register(Fonte)
class FonteAdmin(admin.ModelAdmin):
    actions = [sincronizar_agora]
    list_display = ("nome", "tipo_adapter", "ativo", "intervalo_sync_minutos", "atualizado_em")
    list_filter = ("ativo", "tipo_adapter")
    search_fields = ("nome", "tipo_adapter")
    inlines = [SincronizacaoLogInline]


@admin.register(SincronizacaoLog)
class SincronizacaoLogAdmin(admin.ModelAdmin):
    list_display = ("fonte", "status", "iniciado_em", "finalizado_em", "itens_importados")
    list_filter = ("status", "fonte")
    search_fields = ("fonte__nome",)
    date_hierarchy = "iniciado_em"

    # Logs são gerados pelas tasks de sync, não pelo admin.
    readonly_fields = (
        "fonte", "status", "iniciado_em", "finalizado_em",
        "itens_importados", "erro_detalhe",
    )

    def has_add_permission(self, request):
        return False
