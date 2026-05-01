"""认证相关表单。

本模块集中处理注册和登录表单校验，避免视图直接承载认证细节。
"""

from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm
from django import forms

from users.models import User, Profile


class UserLoginForm(forms.Form):
    """用户名或邮箱登录表单。

    该表单只负责收集登录凭据并调用 Django 认证系统。用户名认证由默认
    `ModelBackend` 处理，邮箱认证由项目自定义后端处理。

    Attributes:
        user: 认证成功后的用户对象；认证失败时为 None。
    """

    username = forms.CharField(label="用户名/邮箱", max_length=150)
    password = forms.CharField(label="密码", widget=forms.PasswordInput)

    def __init__(self, *args, request=None, **kwargs):
        """初始化登录表单。

        Args:
            *args: 传递给 Django 表单父类的位置参数。
            request: 当前请求对象，供 `authenticate()` 传递给认证后端。
            **kwargs: 传递给 Django 表单父类的关键字参数。
        """

        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None

    def clean(self):
        """校验登录凭据并保存认证成功的用户。

        Returns:
            dict: 已通过字段级清洗的数据。

        Raises:
            forms.ValidationError: 用户名或邮箱与密码无法认证，或账号已被禁用。
        """

        cleaned_data = super().clean()

        username = cleaned_data.get("username")
        password = cleaned_data.get("password")

        if username and password:
            self.user = authenticate(self.request, username=username, password=password)

        # 缺少字段时交给字段级 required 错误处理，避免额外叠加通用登录失败提示。
        if not username or not password:
            return cleaned_data

        if self.user is None:
            raise forms.ValidationError("请输入正确的用户名或邮箱和密码")

        if not self.user.is_active:
            raise forms.ValidationError("该账号被禁用")

        return cleaned_data

    def get_user(self):
        """返回认证成功的用户对象。

        Returns:
            User | None: 认证成功时为用户对象，否则为 None。
        """

        return self.user


class UserRegisterForm(UserCreationForm):
    """用户注册表单。

    该表单基于 Django `UserCreationForm`，复用内置密码校验和哈希保存流程，
    同时补充邮箱规范化与用户名、邮箱唯一性校验。
    """

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]
        labels = {
            "username": "用户名",
            "email": "邮箱",
            "password1": "密码",
            "password2": "确认密码",
        }
        help_texts = {
            "username": "用户名长度不得少于2位",
        }

    def clean_email(self):
        """规范化邮箱并校验唯一性。

        Returns:
            str: 去除首尾空白并转为小写后的邮箱。

        Raises:
            forms.ValidationError: 邮箱为空或已被注册。
        """

        email = self.cleaned_data.get("email")
        if email is None or email.strip() == "":
            raise forms.ValidationError("邮箱不能为空")

        email = email.strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("该邮箱已存在")
        return email

    def clean_username(self):
        """校验用户名唯一性。

        Returns:
            str: 通过校验的用户名。

        Raises:
            forms.ValidationError: 用户名已被注册。
        """

        username = self.cleaned_data.get("username")

        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("该用户名已存在")

        return username


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["nickname", "avatar", "bio"]
        labels = {
            "nickname": "用户昵称",
            "avatar": "用户头像",
            "bio": "用户简介",
        }
