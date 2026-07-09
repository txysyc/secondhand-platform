"""catalog API 序列化器。"""

from rest_framework import serializers

from catalog.constants import MAX_IMAGE_SIZE
from catalog.models import Category, Listing, ListingImage
from catalog.selectors import get_active_categories


class CategorySerializer(serializers.ModelSerializer):
    """启用分类展示。"""

    class Meta:
        model = Category
        fields = ["id", "name"]


class ListingOwnerSerializer(serializers.Serializer):
    """商品所有者摘要。"""

    id = serializers.IntegerField()
    username = serializers.CharField()


class ListingImageSerializer(serializers.ModelSerializer):
    """商品图片展示。"""

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ListingImage
        fields = ["id", "image", "image_url", "sort_order"]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        return obj.image.url


class ListingWriteSerializer(serializers.ModelSerializer):
    """商品写入参数。"""

    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.none())

    class Meta:
        model = Listing
        fields = [
            "title",
            "category",
            "item_type",
            "price",
            "condition",
            "description",
            "delivery_notes",
            "physical_delivery_method",
            "virtual_valid_until",
        ]
        extra_kwargs = {
            "condition": {"required": False, "allow_null": True},
            "delivery_notes": {"required": False, "allow_blank": True},
            "physical_delivery_method": {"required": False, "allow_null": True},
            "virtual_valid_until": {"required": False, "allow_null": True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 分类下拉只允许选择启用分类，避免新建或编辑商品时挂到已停用分类。
        self.fields["category"].queryset = get_active_categories()

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("价格必须大于0")
        return value

    def validate(self, attrs):
        instance = getattr(self, "instance", None)

        def resolved(name):
            # PATCH 场景需要合并实例原值与本次入参，才能正确校验实体/虚拟商品字段组合。
            if name in attrs:
                return attrs[name]
            if instance is not None:
                return getattr(instance, name)
            return None

        item_type = resolved("item_type")
        if item_type == Listing.ItemType.PHYSICAL:
            if not resolved("condition"):
                raise serializers.ValidationError({"condition": "实体商品必须填写成色"})
            if not resolved("physical_delivery_method"):
                raise serializers.ValidationError(
                    {"physical_delivery_method": "实体商品必须选择交付方式"}
                )
            attrs["virtual_valid_until"] = None

        if item_type == Listing.ItemType.VIRTUAL:
            if not resolved("virtual_valid_until"):
                raise serializers.ValidationError(
                    {"virtual_valid_until": "虚拟商品需要填写有效期"}
                )
            attrs["condition"] = None
            attrs["physical_delivery_method"] = None

        return attrs


class ListingDetailSerializer(serializers.ModelSerializer):
    """商品详情响应。"""

    category = CategorySerializer(read_only=True)
    owner = ListingOwnerSerializer(read_only=True)
    images = ListingImageSerializer(many=True, read_only=True)
    is_favorited = serializers.SerializerMethodField()
    item_type_display = serializers.CharField(source="get_item_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    condition_display = serializers.CharField(
        source="get_condition_display", read_only=True, allow_null=True
    )
    physical_delivery_method_display = serializers.CharField(
        source="get_physical_delivery_method_display",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Listing
        fields = [
            "id",
            "title",
            "category",
            "owner",
            "item_type",
            "item_type_display",
            "status",
            "status_display",
            "price",
            "condition",
            "condition_display",
            "description",
            "delivery_notes",
            "physical_delivery_method",
            "physical_delivery_method_display",
            "virtual_valid_until",
            "published_at",
            "created_at",
            "updated_at",
            "images",
            "is_favorited",
        ]

    def get_is_favorited(self, obj):
        """返回当前请求用户是否已收藏该商品。"""

        return bool(getattr(obj, "is_favorited", False))


class ListingImageUploadSerializer(serializers.Serializer):
    """商品图片上传参数。"""

    images = serializers.ListField(
        child=serializers.ImageField(),
        allow_empty=False,
        write_only=True,
    )

    def validate_images(self, value):
        if len(value) > 6:
            raise serializers.ValidationError("最多只能上传6张图片")
        for image in value:
            if image.size > MAX_IMAGE_SIZE:
                raise serializers.ValidationError("单张图片不能大于5MB")
        return value


class ListingImageReorderSerializer(serializers.Serializer):
    """商品图片重排参数。"""

    image_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def validate_image_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("图片顺序不能重复")
        return value
