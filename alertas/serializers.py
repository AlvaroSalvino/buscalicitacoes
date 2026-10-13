from rest_framework import serializers

from licitacoes.serializers import LicitacaoListSerializer

from . import matching
from .models import Alerta, Notificacao


class AlertaSerializer(serializers.ModelSerializer):
    filtros = serializers.JSONField(
        help_text=(
            "Mesmos parâmetros de GET /api/licitacoes/ (q, uf, modalidade, "
            "status, valor_min, valor_max, ...). Listas aceitam array ou 'a,b'."
        ),
    )
    nao_lidas = serializers.SerializerMethodField()

    class Meta:
        model = Alerta
        fields = (
            "id", "nome", "filtros", "ativo", "notificar_email", "notificar_push",
            "nao_lidas", "criado_em", "atualizado_em",
        )
        read_only_fields = ("id", "nao_lidas", "criado_em", "atualizado_em")

    def get_nao_lidas(self, obj) -> int:
        return obj.notificacoes.filter(lida=False).count()

    def validate_filtros(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Deve ser um objeto JSON.")
        normalizados, erros = matching.validar(value)
        if erros:
            raise serializers.ValidationError(erros["filtros"])
        return normalizados


class NotificacaoSerializer(serializers.ModelSerializer):
    alerta_nome = serializers.CharField(source="alerta.nome", read_only=True)
    licitacao = LicitacaoListSerializer(read_only=True)

    class Meta:
        model = Notificacao
        fields = ("id", "alerta", "alerta_nome", "licitacao", "lida", "criado_em")
        read_only_fields = ("id", "alerta", "alerta_nome", "licitacao", "criado_em")


class PushSubscriptionSerializer(serializers.Serializer):
    """Corpo do PushSubscription.toJSON() do navegador."""

    endpoint = serializers.URLField(max_length=2000)
    keys = serializers.DictField(child=serializers.CharField(max_length=255))

    def validate_keys(self, value):
        if not value.get("p256dh") or not value.get("auth"):
            raise serializers.ValidationError("keys.p256dh e keys.auth são obrigatórios.")
        return value
