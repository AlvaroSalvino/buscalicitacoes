from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Convite

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    """Cadastro por convite: o e-mail vem do convite, não do cliente."""

    token = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    email = serializers.EmailField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "first_name", "last_name", "token")
        read_only_fields = ("id", "email")

    def validate_token(self, value):
        convite = Convite.pendente_por_token(value)
        if convite is None:
            raise serializers.ValidationError("Convite inválido, expirado ou já utilizado.")
        self._convite = convite
        return value

    def validate(self, attrs):
        senha = attrs["password"]
        candidato = User(
            username=attrs.get("username", ""), email=self._convite.email,
            first_name=attrs.get("first_name", ""), last_name=attrs.get("last_name", ""),
        )
        validate_password(senha, candidato)
        if User.objects.filter(email__iexact=self._convite.email).exists():
            raise serializers.ValidationError("Já existe uma conta com o e-mail deste convite.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop("token")
        # Reconfere dentro da transação: o convite só pode ser usado uma vez.
        convite = Convite.objects.select_for_update().get(pk=self._convite.pk)
        if convite.usado_em is not None:
            raise serializers.ValidationError({"token": "Convite já utilizado."})
        user = User.objects.create_user(email=convite.email, **validated_data)
        convite.usado_em = timezone.now()
        convite.usuario = user
        convite.save(update_fields=["usado_em", "usuario"])
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "is_superuser")
        read_only_fields = ("id", "username", "is_superuser")


class ConviteSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    criado_por = serializers.CharField(source="criado_por.username", read_only=True)

    class Meta:
        model = Convite
        fields = ("id", "email", "status", "criado_por", "criado_em", "expira_em", "usado_em")
        read_only_fields = fields


class SenhaEnviarSerializer(serializers.Serializer):
    email = serializers.EmailField()


class SenhaConfirmarSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"})


class ConviteCriarSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Já existe uma conta com este e-mail.")
        return value.strip().lower()
