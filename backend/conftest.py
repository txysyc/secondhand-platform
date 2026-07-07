"""pytest 共享测试夹具。"""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


@pytest.fixture
def api_client():
    """返回 DRF APIClient，供 API 测试直接注入。"""

    return APIClient()


@pytest.fixture
def auth_headers():
    """生成指定用户的 JWT Authorization 请求头。"""

    def _build_headers(user):
        token = RefreshToken.for_user(user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    return _build_headers


@pytest.fixture
def png_image():
    """构造测试用 PNG 上传文件。"""

    def _build_image(name="image.png", size=(1, 1)):
        buffer = BytesIO()
        image = Image.new("RGB", size, color="white")
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    return _build_image
