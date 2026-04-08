from django.core import mail
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient

from mainApp.models import User


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_RESET_FRONTEND_URL="http://localhost:5173/dat-lai-mat-khau",
)
class PasswordResetAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="reset-test@example.com",
            password="Oldpass123!",
        )

    def test_forgot_password_sends_email_when_user_exists(self):
        mail.outbox.clear()
        response = self.client.post(
            "/auth/forgot-password/",
            {"email": "reset-test@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)
        self.assertEqual(len(mail.outbox), 1)
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn("uid=", html)
        self.assertIn("token=", html)

    def test_forgot_password_unknown_email_no_email_sent(self):
        mail.outbox.clear()
        response = self.client.post(
            "/auth/forgot-password/",
            {"email": "unknown@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_password_success(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        response = self.client.post(
            "/auth/reset-password/",
            {
                "uid": uid,
                "token": token,
                "new_password": "Newpass456!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Newpass456!"))

    def test_reset_password_invalid_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.post(
            "/auth/reset-password/",
            {
                "uid": uid,
                "token": "invalid-token",
                "new_password": "Newpass456!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
