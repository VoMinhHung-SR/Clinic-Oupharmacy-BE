import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from mainApp.models import User
from mainApp.serializers import ForgotPasswordSerializer, ResetPasswordSerializer
from mainApp.services.auth_tokens import revoke_oauth2_tokens_for_user
from mainApp.throttles import ForgotPasswordThrottle, ResetPasswordThrottle

logger = logging.getLogger(__name__)

FORGOT_GENERIC_MSG = {
    "message": "Vui lòng kiểm tra email để đặt lại mật khẩu.",
}


def _build_reset_link(user, base_url: str) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    base = base_url.rstrip("/")
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}uid={uid}&token={token}"


def _send_password_reset_email(user, reset_link: str) -> None:
    subject = "OUPharmacy — Đặt lại mật khẩu"
    context = {
        "user": user,
        "reset_link": reset_link,
        "site_name": "OUPharmacy",
    }
    text_body = render_to_string("emails/password_reset.txt", context)
    html_body = render_to_string("emails/password_reset.html", context)
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or settings.EMAIL_HOST_USER
    msg = EmailMultiAlternatives(subject, text_body, from_email, [user.email])
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ForgotPasswordThrottle])
def forgot_password(request):
    serializer = ForgotPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"].strip().lower()

    base_url = getattr(settings, "PASSWORD_RESET_FRONTEND_URL", "") or ""
    if not base_url:
        logger.warning("PASSWORD_RESET_FRONTEND_URL is not set; skipping password reset email.")
        return Response(FORGOT_GENERIC_MSG, status=status.HTTP_200_OK)

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response(FORGOT_GENERIC_MSG, status=status.HTTP_200_OK)

    if not user.is_active:
        return Response(FORGOT_GENERIC_MSG, status=status.HTTP_200_OK)

    try:
        reset_link = _build_reset_link(user, base_url)
        _send_password_reset_email(user, reset_link)
    except Exception:
        logger.exception("Failed to send password reset email for user_id=%s", user.pk)

    return Response(FORGOT_GENERIC_MSG, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ResetPasswordThrottle])
def reset_password(request):
    serializer = ResetPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data["user"]
    new_password = serializer.validated_data["new_password"]
    user.set_password(new_password)
    user.save()
    revoke_oauth2_tokens_for_user(user)
    return Response(
        {"message": "Đặt lại mật khẩu thành công. Vui lòng đăng nhập lại."},
        status=status.HTTP_200_OK,
    )
