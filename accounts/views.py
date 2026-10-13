import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Convite
from .serializers import (
    ConviteCriarSerializer, ConviteSerializer, RegisterSerializer,
    SenhaConfirmarSerializer, SenhaEnviarSerializer, UserSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class IsSuperuser(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_superuser)


class AuthThrottle(AnonRateThrottle):
    scope = "auth"


class LoginView(TokenObtainPairView):
    throttle_classes = [AuthThrottle]


@extend_schema(tags=["auth"], summary="Criar conta a partir de um convite")
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthThrottle]


@extend_schema(tags=["auth"], summary="Dados do usuário autenticado")
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


@extend_schema(
    tags=["auth"], summary="Validar token de convite",
    parameters=[OpenApiParameter("token", str, required=True)],
    responses={200: dict},
)
class ConviteValidarView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthThrottle]

    def get(self, request):
        convite = Convite.pendente_por_token(request.query_params.get("token", ""))
        if convite is None:
            return Response(
                {"detail": "Convite inválido, expirado ou já utilizado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"email": convite.email})


def _link_cadastro(request, token):
    base = (getattr(settings, "SITE_URL", "") or request.build_absolute_uri("/")).rstrip("/")
    return f"{base}/#/cadastro?token={token}"


@extend_schema(tags=["convites"])
class ConviteListCreateView(generics.ListCreateAPIView):
    """Somente superusuários: convidam novas pessoas e veem os convites."""

    permission_classes = [IsSuperuser]
    queryset = Convite.objects.select_related("criado_por")
    pagination_class = None

    def get_serializer_class(self):
        return ConviteCriarSerializer if self.request.method == "POST" else ConviteSerializer

    @extend_schema(request=ConviteCriarSerializer, responses={201: dict})
    def create(self, request, *args, **kwargs):
        ser = ConviteCriarSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data["email"]

        # Um único convite pendente por e-mail: reenviar invalida o anterior.
        Convite.objects.filter(email=email, usado_em__isnull=True).delete()
        convite, token = Convite.criar(email, request.user)
        link = _link_cadastro(request, token)

        quem = request.user.get_full_name() or request.user.username
        email_enviado = True
        try:
            send_mail(
                subject="Convite para o Busca Licitações",
                message=(
                    f"{quem} convidou você para usar o Busca Licitações.\n\n"
                    f"Crie sua conta pelo link abaixo (válido por "
                    f"{getattr(settings, 'CONVITE_VALIDADE_DIAS', 7)} dias, uso único):\n\n"
                    f"{link}\n\n"
                    f"Se você não esperava este convite, ignore esta mensagem."
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[email],
            )
        except Exception:
            logger.exception("Falha ao enviar convite para %s", email)
            email_enviado = False

        dados = ConviteSerializer(convite).data
        # O link volta só para o superusuário que criou (útil se o e-mail falhar).
        return Response(
            {**dados, "link": link, "email_enviado": email_enviado},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["convites"], summary="Revogar convite pendente")
class ConviteDetailView(generics.DestroyAPIView):
    permission_classes = [IsSuperuser]
    queryset = Convite.objects.all()
    serializer_class = ConviteSerializer

    def destroy(self, request, *args, **kwargs):
        convite = self.get_object()
        if convite.usado_em:
            return Response(
                {"detail": "Convite já utilizado não pode ser removido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        convite.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- Senha
def _usuario_do_link(uid, token):
    """Usuário do link de redefinição, ou None se uid/token forem inválidos."""
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return None
    return user if default_token_generator.check_token(user, token) else None


@extend_schema(tags=["senha"], request=SenhaEnviarSerializer, responses={200: dict},
               summary="Enviar e-mail de redefinição de senha (superusuário)")
class SenhaEnviarView(APIView):
    permission_classes = [IsSuperuser]

    def post(self, request):
        ser = SenhaEnviarSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data["email"]
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is None:
            return Response(
                {"detail": "Nenhum usuário ativo com este e-mail."},
                status=status.HTTP_404_NOT_FOUND,
            )
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        base = (getattr(settings, "SITE_URL", "") or request.build_absolute_uri("/")).rstrip("/")
        link = f"{base}/#/redefinir-senha?uid={uid}&token={token}"

        horas = max(1, settings.PASSWORD_RESET_TIMEOUT // 3600)
        email_enviado = True
        try:
            send_mail(
                subject="Redefinição de senha - Busca Licitações",
                message=(
                    f"Olá, {user.get_full_name() or user.username}.\n\n"
                    f"Foi solicitada a redefinição da sua senha no Busca Licitações. "
                    f"Crie uma nova senha pelo link abaixo (válido por {horas}h, uso único):\n\n"
                    f"{link}\n\n"
                    f"Se você não esperava este e-mail, avise quem administra o aplicativo."
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[user.email],
            )
        except Exception:
            logger.exception("Falha ao enviar redefinição de senha para %s", user.pk)
            email_enviado = False
        return Response({"email": user.email, "email_enviado": email_enviado, "link": link})


@extend_schema(
    tags=["senha"], summary="Validar link de redefinição de senha",
    parameters=[OpenApiParameter("uid", str, required=True), OpenApiParameter("token", str, required=True)],
    responses={200: dict},
)
class SenhaValidarView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthThrottle]

    def get(self, request):
        user = _usuario_do_link(
            request.query_params.get("uid", ""), request.query_params.get("token", ""),
        )
        if user is None:
            return Response(
                {"detail": "Link inválido, expirado ou já utilizado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"email": user.email, "username": user.username})


@extend_schema(tags=["senha"], request=SenhaConfirmarSerializer, responses={204: None},
               summary="Definir nova senha com o link recebido")
class SenhaConfirmarView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthThrottle]

    def post(self, request):
        ser = SenhaConfirmarSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        user = _usuario_do_link(d["uid"], d["token"])
        if user is None:
            return Response(
                {"detail": "Link inválido, expirado ou já utilizado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validate_password(d["password"], user)
        except DjangoValidationError as exc:
            return Response({"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        # set_password muda o hash e, com isso, invalida o link (uso único).
        user.set_password(d["password"])
        user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)
