"""用户与认证 API 序列化器。"""

from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import Listing
from catalog.selectors import get_publish_listing_queryset
from users.models import Profile, User
from users.services import register_user


class UserRegisterSerializer(serializers.Serializer):
    """用户注册入参校验和创建。"""

    username = serializers.CharField(max_length=10)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate_username(self, value):
        if len(value) < 2:
            raise serializers.ValidationError("用户名长度不得少于2位")
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("该用户名已存在")
        return value

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("该邮箱已存在")
        return email

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "两次输入的密码不一致"})

        user = User(username=attrs["username"], email=attrs["email"])
        try:
            password_validation.validate_password(attrs["password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        return attrs

    def create(self, validated_data):
        return register_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )


class TokenPairSerializer(serializers.Serializer):
    """使用用户名或邮箱签发 JWT token。"""

    identifier = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(
            request,
            username=attrs["identifier"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("请输入正确的用户名或邮箱和密码")

        refresh = RefreshToken.for_user(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class ProfileSerializer(serializers.ModelSerializer):
    """用户资料展示与更新。"""

    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ["nickname", "avatar", "avatar_url", "bio"]
        extra_kwargs = {
            "avatar": {"required": False, "allow_null": True},
            "bio": {"required": False, "allow_blank": True},
        }

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return None
        return obj.avatar.url


class CurrentUserSerializer(serializers.ModelSerializer):
    """当前用户资料响应。"""

    profile = ProfileSerializer()

    class Meta:
        model = User
        fields = ["id", "username", "email", "profile"]
        read_only_fields = ["id", "username", "email"]


class PublicListingSummarySerializer(serializers.ModelSerializer):
    """公开主页中的商品摘要。"""

    category_name = serializers.CharField(source="category.name")
    price = serializers.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        model = Listing
        fields = ["id", "title", "price", "item_type", "category_name"]


class PublicUserSerializer(serializers.ModelSerializer):
    """公开用户主页响应。"""

    profile = ProfileSerializer()
    listings = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "profile", "listings"]

    def get_listings(self, obj):
        queryset = get_publish_listing_queryset().filter(owner=obj)
        return PublicListingSummarySerializer(queryset, many=True).data
