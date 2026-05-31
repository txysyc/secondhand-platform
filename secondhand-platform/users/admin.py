from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from users.models import User, Profile


class ProfileInline(admin.TabularInline):
    """用户资料内联后台。

    在用户详情页中展示和维护 Profile，并约束后台只能维护一份资料。
    当历史数据或导入数据导致用户缺少资料时，允许管理员补建。
    """

    model = Profile
    verbose_name = "个人资料"
    # Profile 与 User 是一对一关系，后台最多展示和维护一份资料。
    can_delete = False
    extra = 0
    max_num = 1

    def has_add_permission(self, request, obj=None):
        """判断当前用户后台页是否允许新增 Profile。

        Args:
            request (HttpRequest): 当前后台请求对象。
            obj (User | None): 当前正在编辑的用户对象；新增用户页为 None。

        Returns:
            bool: 新增用户页或已有用户缺少资料时返回 True，否则返回 False。
        """

        if obj is None:
            return True
        return not hasattr(obj, "profile")

    def get_extra(self, request, obj=None, **kwargs):
        """返回需要额外展示的空 Profile 表单数量。

        Args:
            request (HttpRequest): 当前后台请求对象。
            obj (User | None): 当前正在编辑的用户对象；新增用户页为 None。
            **kwargs: Django admin 传入的额外上下文参数。

        Returns:
            int: 用户缺少资料时返回 1，其余情况返回 0。
        """

        if obj is not None and not hasattr(obj, "profile"):
            return 1
        return 0


@admin.register(User)
class MyUserAdmin(UserAdmin):
    """自定义用户后台配置。

    配置用户列表展示、搜索字段、创建/编辑表单字段，以及用户资料内联表单。
    """

    list_display = [
        "id",
        "username",
        "email",
        "is_active",
        "is_staff",
        "is_superuser",
        "created_at",
        "updated_at",
    ]
    # 修改对象时的表单
    fieldsets = (
        ("基本信息", {"fields": ("username", "email", "password")}),
        ("发布信息", {"fields": ("created_at", "updated_at")}),
        (
            "权限信息",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("日志信息", {"fields": ("last_login",)}),
    )
    # 创建新对象时的表单
    add_fieldsets = (
        ("必填信息", {"fields": ("username", "email", "password1", "password2")}),
    )
    # 搜寻字段
    search_fields = ["id", "username", "email"]
    list_per_page = 20
    list_filter = ["is_active", "is_staff", "is_superuser", "groups", "created_at"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "last_login",
    ]
    inlines = [ProfileInline]
