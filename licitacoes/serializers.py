from rest_framework import serializers

from .models import Licitacao, Orgao


class OrgaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Orgao
        fields = ("id", "cnpj", "razao_social", "esfera", "uf", "municipio")
        read_only_fields = fields


class LicitacaoListSerializer(serializers.ModelSerializer):
    orgao = serializers.CharField(source="orgao.razao_social", read_only=True)
    fonte = serializers.CharField(source="fonte.nome", read_only=True)
    modalidade_display = serializers.CharField(
        source="get_modalidade_display", read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True,
    )

    class Meta:
        model = Licitacao
        fields = (
            "id", "numero", "orgao", "fonte", "modalidade", "modalidade_display",
            "status", "status_display", "objeto", "valor_estimado",
            "uf", "municipio", "data_publicacao", "data_abertura",
            "data_encerramento_propostas", "link_original",
        )
        read_only_fields = fields


class LicitacaoDetailSerializer(LicitacaoListSerializer):
    orgao = OrgaoSerializer(read_only=True)
    id_externo = serializers.CharField(read_only=True)
    licitacao_matriz = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta(LicitacaoListSerializer.Meta):
        fields = LicitacaoListSerializer.Meta.fields + (
            "id_externo", "licitacao_matriz", "criado_em", "atualizado_em",
        )
        read_only_fields = fields
