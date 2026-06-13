from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


class ApiBaseLayerTests(TestCase):
    """P1 基础 API 层门禁测试。"""

    def setUp(self):
        self.client = APIClient()

    def _create_token_header(self, user):
        token = RefreshToken.for_user(user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_api_root_is_public_and_returns_version_metadata(self):
        response = self.client.get(reverse("api:root"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"name": "secondhand-platform API", "version": "v1", "status": "ok"},
        )

    def test_api_root_returns_cors_header_for_local_vite_origin(self):
        response = self.client.get(
            reverse("api:root"),
            HTTP_ORIGIN="http://localhost:5173",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            "http://localhost:5173",
        )

    def test_authenticated_probe_accepts_valid_bearer_token(self):
        user = get_user_model().objects.create_user(
            username="apiuser",
            email="apiuser@example.com",
            password="strong-pass-123",
        )

        response = self.client.get(
            reverse("api:authenticated_probe"),
            **self._create_token_header(user),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"authenticated": True})

    def test_authenticated_probe_rejects_missing_token_with_json_error(self):
        response = self.client.get(reverse("api:authenticated_probe"))

        self.assertEqual(response.status_code, 401)
        self.assertIn("message", response.json())
        self.assertIn("errors", response.json())

    def test_authenticated_probe_rejects_invalid_token_with_json_error(self):
        response = self.client.get(
            reverse("api:authenticated_probe"),
            HTTP_AUTHORIZATION="Bearer invalid-token",
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("message", response.json())
        self.assertIn("errors", response.json())

    def test_staff_probe_rejects_non_staff_user_with_json_error(self):
        user = get_user_model().objects.create_user(
            username="normaluser",
            email="normaluser@example.com",
            password="strong-pass-123",
        )

        response = self.client.get(
            reverse("api:staff_probe"),
            **self._create_token_header(user),
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("message", response.json())
        self.assertIn("errors", response.json())

    def test_home_page_still_returns_template_response(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
