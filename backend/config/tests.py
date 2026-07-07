"""基础 API 层 pytest 测试。"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


pytestmark = pytest.mark.django_db


def test_api_root_is_public_and_returns_version_metadata(api_client):
    """API 根路径公开返回版本元信息。"""

    response = api_client.get(reverse("api:root"))

    assert response.status_code == 200
    assert response.json() == {
        "name": "secondhand-platform API",
        "version": "v1",
        "status": "ok",
    }


def test_api_root_returns_cors_header_for_local_vite_origin(api_client):
    """本地 Vite 来源请求会返回允许跨域响应头。"""

    response = api_client.get(
        reverse("api:root"),
        HTTP_ORIGIN="http://localhost:5173",
    )

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"


def test_authenticated_probe_accepts_valid_bearer_token(api_client, auth_headers):
    """携带有效 Bearer token 时认证探针返回已认证。"""

    user = get_user_model().objects.create_user(
        username="apiuser",
        email="apiuser@example.com",
        password="strong-pass-123",
    )

    response = api_client.get(
        reverse("api:authenticated_probe"),
        **auth_headers(user),
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


def test_authenticated_probe_rejects_missing_token_with_json_error(api_client):
    """缺失 token 时认证探针返回统一 JSON 错误结构。"""

    response = api_client.get(reverse("api:authenticated_probe"))

    assert response.status_code == 401
    assert "message" in response.json()
    assert "errors" in response.json()


def test_authenticated_probe_rejects_invalid_token_with_json_error(api_client):
    """无效 token 时认证探针返回统一 JSON 错误结构。"""

    response = api_client.get(
        reverse("api:authenticated_probe"),
        HTTP_AUTHORIZATION="Bearer invalid-token",
    )

    assert response.status_code == 401
    assert "message" in response.json()
    assert "errors" in response.json()


def test_staff_probe_rejects_non_staff_user_with_json_error(api_client, auth_headers):
    """非 staff 用户访问 staff 探针时返回权限错误。"""

    user = get_user_model().objects.create_user(
        username="normaluser",
        email="normaluser@example.com",
        password="strong-pass-123",
    )

    response = api_client.get(
        reverse("api:staff_probe"),
        **auth_headers(user),
    )

    assert response.status_code == 403
    assert "message" in response.json()
    assert "errors" in response.json()


def test_legacy_home_page_is_not_exposed_by_api_only_backend(api_client):
    """API-only 后端不暴露旧首页。"""

    response = api_client.get("/")

    assert response.status_code == 404
