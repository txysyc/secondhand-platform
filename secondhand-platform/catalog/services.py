from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from catalog.constants import MAX_IMAGE_COUNT
from catalog.models import Listing, ListingImage
from users.models import User

EDITABLE_STATUSES = {Listing.Status.DRAFT, Listing.Status.ACTIVE}

# 卖家手动状态动作的白名单。reserved / sold 由订单流程控制，本故事拒绝任何指向这两个状态的卖家动作。
ACTION_WITHDRAW = "withdraw"
ACTION_RESTORE_ACTIVE = "restore_active"
STATUS_ACTION_ALLOWED = {ACTION_WITHDRAW, ACTION_RESTORE_ACTIVE}


def ensure_listing_owner(user: User, listing: Listing):
    """校验当前用户是否为商品所有者。"""

    if listing.owner_id != user.id:
        raise PermissionDenied("该用户无权访问该对象")


def _delete_image_files_on_commit(file_fields):
    """收集文件信息，在数据库事务提交成功后再删除物理文件。"""

    files = []
    for file_field in file_fields:
        if file_field and file_field.name:
            files.append((file_field.storage, file_field.name))

    if not files:
        return

    def cleanup():
        """事务提交成功后删除已不再被数据库引用的图片文件。"""

        for storage, name in files:
            storage.delete(name)

    transaction.on_commit(cleanup)


def publish_listing(user: User, listing: Listing):
    """将草稿商品发布为在售商品。"""

    ensure_listing_owner(user, listing)
    if listing.status != Listing.Status.DRAFT:
        raise ValidationError("只有草稿商品可以发布")

    if listing.published_at is None:
        listing.published_at = timezone.now()
    listing.status = Listing.Status.ACTIVE


def delete_listing(user: User, listing: Listing):
    """删除草稿或在售商品，并在事务提交后清理关联图片文件。"""

    ensure_listing_owner(user, listing)

    if (
        listing.status != Listing.Status.DRAFT
        and listing.status != Listing.Status.ACTIVE
    ):
        raise ValidationError("只有草稿和发布状态的商品可以删除")

    files_to_delete = [image.image for image in listing.images.all()]

    with transaction.atomic():
        listing.delete()
        _delete_image_files_on_commit(files_to_delete)


def change_listing_status(user: User, listing: Listing, action: str):
    """按白名单动作推进当前用户自己的商品状态，集中维护卖家手动可执行的流转规则:主要为商品重新上架和商品下架两种动作"""

    ensure_listing_owner(user, listing)

    if action not in STATUS_ACTION_ALLOWED:
        raise ValidationError("无效的状态动作")

    if action == ACTION_WITHDRAW:
        if listing.status != Listing.Status.ACTIVE:
            raise ValidationError("只有在售商品可以下架")
        listing.status = Listing.Status.WITHDRAWN
        listing.save(update_fields=["status", "updated_at"])
        return listing

    # ACTION_RESTORE_ACTIVE
    if listing.status != Listing.Status.WITHDRAWN:
        raise ValidationError("只有已下架商品可以重新上架")
    # 变更时需要检测分类是否已停用
    if not listing.category.is_active:
        raise ValidationError("分类已停用，请先编辑商品并选择启用分类")

    update_fields = ["status", "updated_at"]
    if listing.published_at is None:
        # 历史脏数据兜底：重新上架时保证有发布时间，避免后续公开列表筛选失效。
        listing.published_at = timezone.now()
        update_fields.append("published_at")
    listing.status = Listing.Status.ACTIVE
    listing.save(update_fields=update_fields)
    return listing


def create_listing_from_payload(user: User, data: dict):
    """使用字典载荷创建商品草稿，供 API 层调用。"""

    listing = Listing(**data)
    listing.owner = user
    listing.status = Listing.Status.DRAFT
    listing.full_clean()
    listing.save()
    return listing


def update_listing_from_payload(user: User, listing: Listing, data: dict, *, publish: bool = False):
    """使用字典载荷更新商品，供 API 层调用。"""

    ensure_listing_owner(user, listing)

    if listing.status not in EDITABLE_STATUSES:
        raise ValidationError("只有草稿和发布状态的商品可以更新")

    original_status = listing.status
    original_published_at = listing.published_at

    for field_name, value in data.items():
        setattr(listing, field_name, value)

    listing.owner_id = user.id
    listing.status = original_status
    listing.published_at = original_published_at

    if original_status == Listing.Status.DRAFT and publish:
        publish_listing(user, listing)

    listing.full_clean()
    listing.save()
    return listing


def publish_listing_for_user(user: User, listing: Listing):
    """发布当前用户自己的草稿商品。"""

    publish_listing(user, listing)
    listing.save(update_fields=["status", "published_at", "updated_at"])
    return listing


def change_listing_status_for_user(user: User, listing: Listing, action: str):
    """切换当前用户自己的商品状态，并保存到数据库。"""

    listing = change_listing_status(user, listing, action)
    return listing


def delete_listing_for_user(user: User, listing: Listing):
    """删除当前用户自己的商品。"""

    delete_listing(user, listing)


def add_listing_images(user: User, listing: Listing, uploaded_images):
    """为商品新增图片，供 API 层一次上传一张或多张图片。"""

    ensure_listing_owner(user, listing)

    if listing.status not in EDITABLE_STATUSES:
        raise ValidationError("只有草稿和发布状态的商品可以管理图片")

    new_images = [image for image in uploaded_images if image]
    if not new_images:
        raise ValidationError("请至少上传一张图片")

    current_count = listing.images.count()
    if current_count + len(new_images) > MAX_IMAGE_COUNT:
        raise ValidationError(f"最多只能上传{MAX_IMAGE_COUNT}张图片")

    created_images = []
    with transaction.atomic():
        start_order = current_count
        for offset, uploaded_image in enumerate(new_images):
            image = ListingImage.objects.create(
                listing=listing,
                image=uploaded_image,
                sort_order=start_order + offset,
            )
            created_images.append(image)
    return created_images


def delete_listing_image(user: User, listing: Listing, image_id: int):
    """删除商品图片并在事务提交后清理物理文件。"""

    ensure_listing_owner(user, listing)

    if listing.status not in EDITABLE_STATUSES:
        raise ValidationError("只有草稿和发布状态的商品可以管理图片")

    image = listing.images.filter(pk=image_id).first()
    if image is None:
        raise ValidationError("图片不存在")

    file_field = image.image
    with transaction.atomic():
        image.delete()
        _delete_image_files_on_commit([file_field])


def reorder_listing_images(user: User, listing: Listing, image_ids: list[int]):
    """按图片 ID 列表重排商品图片顺序。"""

    ensure_listing_owner(user, listing)

    if listing.status not in EDITABLE_STATUSES:
        raise ValidationError("只有草稿和发布状态的商品可以管理图片")

    current_images = list(listing.images.order_by("sort_order", "id"))
    current_ids = [image.id for image in current_images]
    if sorted(current_ids) != sorted(image_ids):
        raise ValidationError("重排图片必须包含当前商品全部图片")

    image_map = {image.id: image for image in current_images}
    with transaction.atomic():
        for sort_order, image_id in enumerate(image_ids):
            image = image_map[image_id]
            if image.sort_order != sort_order:
                image.sort_order = sort_order
                image.save(update_fields=["sort_order"])
