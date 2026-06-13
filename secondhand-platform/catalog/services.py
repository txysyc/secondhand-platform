from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.forms import BaseInlineFormSet
from django.utils import timezone

from catalog.forms import MAX_IMAGE_COUNT, ListingForm
from catalog.models import Listing, ListingImage
from users.models import User

INTENT_SAVE_DRAFT = "save_draft"
INTENT_PUBLISH = "publish"
INTENT_SAVE_CHANGES = "save_changes"

CREATE_ALLOWED_INTENTS = {INTENT_SAVE_DRAFT, INTENT_PUBLISH}
DRAFT_UPDATE_ALLOWED_INTENTS = {INTENT_SAVE_DRAFT, INTENT_PUBLISH}
ACTIVE_UPDATE_ALLOWED_INTENTS = {INTENT_SAVE_CHANGES}
EDITABLE_STATUSES = {Listing.Status.DRAFT, Listing.Status.ACTIVE}

# 卖家手动状态动作的白名单。reserved / sold 由订单流程控制，本故事拒绝任何指向这两个状态的卖家动作。
ACTION_WITHDRAW = "withdraw"
ACTION_RESTORE_ACTIVE = "restore_active"
STATUS_ACTION_ALLOWED = {ACTION_WITHDRAW, ACTION_RESTORE_ACTIVE}


def ensure_listing_owner(user: User, listing: Listing):
    """校验当前用户是否为商品所有者。"""

    if listing.owner_id != user.id:
        raise PermissionDenied("该用户无权访问该对象")


def _validate_intent(intent: str, allowed_intents: set[str]):
    """校验提交意图，避免伪造值被静默当作普通保存。"""

    if intent not in allowed_intents:
        raise ValidationError("无效的提交操作")


def _count_formset_images(formset: BaseInlineFormSet) -> int:
    """统计实际上传且未标记删除的图片数量。"""

    count = 0
    for form in formset.forms:
        # 防止绕过 view 直接调用服务时传入未校验 formset。
        if not hasattr(form, "cleaned_data"):
            continue
        if form.cleaned_data.get("DELETE"):
            continue
        if form.cleaned_data.get("image"):
            count += 1
    return count


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


def _collect_replaced_or_deleted_files(formset: BaseInlineFormSet):
    """找出编辑图片时被删除或被替换的旧文件。"""

    files_to_delete = []
    for image_form in formset.initial_forms:
        if not hasattr(image_form, "cleaned_data"):
            continue
        if not image_form.instance.pk:
            continue

        old_image = ListingImage.objects.only("image").get(pk=image_form.instance.pk)
        if image_form.cleaned_data.get("DELETE"):
            files_to_delete.append(old_image.image)
            continue
        if "image" in image_form.changed_data:
            files_to_delete.append(old_image.image)

    return files_to_delete


def _reorder_images_by_form_order(formset: BaseInlineFormSet):
    """按表单顺序重排保留下来的图片。"""

    sort_order = 0
    for image_form in formset.forms:
        if not hasattr(image_form, "cleaned_data"):
            continue
        if image_form.cleaned_data.get("DELETE"):
            continue
        if not image_form.instance.pk:
            continue

        if image_form.instance.sort_order != sort_order:
            image_form.instance.sort_order = sort_order
            image_form.instance.save(update_fields=["sort_order"])
        sort_order += 1


def create_listing(
    user: User,
    form: ListingForm,
    formset: BaseInlineFormSet,
    intent: str,
):
    """创建商品并按提交意图保存为草稿或直接发布。"""

    _validate_intent(intent, CREATE_ALLOWED_INTENTS)

    listing: Listing = form.save(commit=False)
    listing.owner = user
    listing.status = Listing.Status.DRAFT

    if intent == INTENT_PUBLISH:
        publish_listing(user, listing)

    formset.instance = listing
    if _count_formset_images(formset) > MAX_IMAGE_COUNT:
        raise ValidationError(f"最多只能上传{MAX_IMAGE_COUNT}张图片")

    with transaction.atomic():
        listing.save()
        images = formset.save(commit=False)

        for sort_order, image in enumerate(images):
            image.listing = listing
            image.sort_order = sort_order
            image.save()

        for deleted_image in formset.deleted_objects:
            deleted_image.delete()

    return listing


def update_listing(
    user: User,
    listing: Listing,
    form: ListingForm,
    formset: BaseInlineFormSet,
    intent: str,
):
    """更新商品字段和图片，并按当前状态限制允许的提交意图。"""

    ensure_listing_owner(user, listing)

    if listing.status not in EDITABLE_STATUSES:
        raise ValidationError("只有草稿和发布状态的商品可以更新")
    if listing.status == Listing.Status.DRAFT:
        _validate_intent(intent, DRAFT_UPDATE_ALLOWED_INTENTS)
    if listing.status == Listing.Status.ACTIVE:
        _validate_intent(intent, ACTIVE_UPDATE_ALLOWED_INTENTS)

    if form.instance.pk != listing.pk:
        raise ValidationError("表单对象与商品对象不一致")
    # 保留原有的状态和发布时间
    original_status = listing.status
    original_published_at = listing.published_at

    updated_listing: Listing = form.save(commit=False)
    updated_listing.owner_id = listing.owner_id
    updated_listing.status = original_status
    updated_listing.published_at = original_published_at
    formset.instance = updated_listing

    files_to_delete = _collect_replaced_or_deleted_files(formset)
    # 如果更新时是草稿转台并且提交为发布：执行发布流程
    if original_status == Listing.Status.DRAFT and intent == INTENT_PUBLISH:
        publish_listing(user, updated_listing)

    with transaction.atomic():
        updated_listing.save()
        # formset.save(commit=False) 只返回新增对象和被修改对象，不包含所有保留图片。
        images = formset.save(commit=False)
        for image in images:
            image.listing = updated_listing
            image.save()

        for deleted_object in formset.deleted_objects:
            deleted_object.delete()

        _reorder_images_by_form_order(formset)
        _delete_image_files_on_commit(files_to_delete)

    return updated_listing


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
