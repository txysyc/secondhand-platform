"""认证流程视图。"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.views.decorators.csrf import csrf_protect

from users.forms import UserLoginForm, UserRegisterForm, ProfileForm
from users.services import register_add_group
from users.models import Profile


class LoginView(View):
    """处理登录页展示和登录提交。"""

    template_name = "users/login.html"
    form_class = UserLoginForm

    def get(self, request):
        """渲染登录页。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            HttpResponse: 包含登录表单和可选 `next` 参数的页面响应。
        """

        form = self.form_class(request=request)
        next_url = request.GET.get("next")

        context = {"form": form, "next": next_url}

        if next_url:
            messages.warning(request, "请先登录后继续访问该页面")

        return render(request, self.template_name, context=context)

    def post(self, request):
        """处理登录提交。

        Args:
            request: 当前 HTTP 请求，包含登录表单数据。

        Returns:
            HttpResponse: 登录成功时重定向；登录失败时重新渲染表单和错误反馈。
        """

        next_url = request.POST.get("next")
        form = self.form_class(data=request.POST, request=request)
        context = {"form": form, "next": next_url}

        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, "登录成功。")

            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            return redirect(settings.LOGIN_REDIRECT_URL)

        messages.error(request, "登录失败，请检查用户名或邮箱和密码。")
        return render(request, self.template_name, context=context)


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(View):
    """处理退出登录动作。"""

    def post(self, request):
        """通过 POST 结束当前用户会话。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            HttpResponseRedirect: 退出成功后跳转到公开落点。
        """

        logout(request)
        messages.success(request, "已退出登录。")
        return redirect(settings.LOGOUT_REDIRECT_URL)


class RegisterView(View):
    """处理注册页展示和注册提交。"""

    template_name = "users/register.html"
    form_class = UserRegisterForm

    def get(self, request):
        """渲染注册页。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            HttpResponse: 包含空注册表单的页面响应。
        """

        form = self.form_class()

        context = {
            "form": form,
        }
        return render(request, self.template_name, context=context)

    def post(self, request):
        """处理注册提交。

        Args:
            request: 当前 HTTP 请求，包含注册表单数据。

        Returns:
            HttpResponse: 注册成功时重定向到登录页；失败时重新渲染表单错误。
        """

        form = self.form_class(data=request.POST)

        context = {"form": form}

        if form.is_valid():
            register_add_group(form)
            messages.success(request, "注册成功，请登录。")
            return redirect(settings.LOGIN_URL)

        return render(request, self.template_name, context=context)


class ProfileView(LoginRequiredMixin, View):
    """处理当前登录用户的公开资料编辑。"""

    model = Profile
    template_name = "users/profile_form.html"
    form_class = ProfileForm

    def get(self, request, *args, **kwargs):
        """渲染当前用户资料编辑页。"""

        profile, _ = Profile.objects.get_or_create(user=request.user)

        form = self.form_class(instance=profile)

        context = {"form": form, "profile": profile}

        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
        """保存当前用户提交的公开资料。"""

        profile, _ = Profile.objects.get_or_create(user=request.user)

        form = self.form_class(
            data=request.POST,
            files=request.FILES,
            instance=profile,
        )
        context = {"form": form, "profile": profile}

        if form.is_valid():
            form.save()
            messages.success(request, "更新成功")
            return redirect("users:profile")

        return render(request, self.template_name, context=context)
