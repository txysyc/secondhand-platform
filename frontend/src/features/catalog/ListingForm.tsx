import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';
import {
  getCategories,
  createListing,
  updateListing,
  getMyListingDetail,
  uploadListingImage,
  deleteListingImage,
  reorderListingImages,
  publishListing,
} from '../../api/endpoints/listings';
import { useAuth } from '../../app/auth';
import { Button, Card, ErrorState, Loading } from '../../components/ui';
import { ListingFormFields } from './form/ListingFormFields';
import { ListingImageManager } from './form/ListingImageManager';
import type { ListingPayload, PendingListingImage } from './form/types';
import type {
  Category,
  Listing,
  ListingImage,
  ListingStatus,
  ItemType,
  ItemCondition,
  PhysicalDeliveryMethod,
} from '../../types/listings';

const getErrorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return fallback;
};

const readImagePreview = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const previewUrl = String(reader.result || '');
      if (!previewUrl.startsWith('data:image/')) {
        reject(new Error(`文件 ${file.name} 不是可预览的图片格式`));
        return;
      }

      const image = new Image();
      image.onload = () => resolve(previewUrl);
      image.onerror = () => {
        reject(new Error(`图片 ${file.name} 无法预览，请选择 JPG、PNG、WebP 等浏览器支持的图片`));
      };
      image.src = previewUrl;
    };
    reader.onerror = () => reject(new Error('图片预览生成失败'));
    reader.readAsDataURL(file);
  });
};

export const ListingForm: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isEditMode = !!id;

  // 基础表单状态
  const [categories, setCategories] = useState<Category[]>([]);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState<string>('');
  const [itemType, setItemType] = useState<ItemType>('physical');
  const [price, setPrice] = useState('');
  const [description, setDescription] = useState('');
  const [deliveryNotes, setDeliveryNotes] = useState('');

  // 实体商品特有字段
  const [condition, setCondition] = useState<ItemCondition>('good');
  const [physicalDeliveryMethod, setPhysicalDeliveryMethod] = useState<PhysicalDeliveryMethod>('meetup');

  // 虚拟商品特有字段
  const [virtualValidUntil, setVirtualValidUntil] = useState('');

  // 图片管理状态
  const [uploadedImages, setUploadedImages] = useState<ListingImage[]>([]);
  const [pendingImages, setPendingImages] = useState<PendingListingImage[]>([]);
  const [currentStatus, setCurrentStatus] = useState<ListingStatus | null>(null);

  // 辅助交互状态
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const categoryOptions = categories.map((c) => ({ value: c.id, label: c.name }));

  // 1. 加载分类
  useEffect(() => {
    const fetchCategories = async () => {
      try {
        const data = await getCategories();
        setCategories(data);
        if (data.length > 0) setCategory(String(data[0].id));
      } catch {
        setErrorMsg('加载分类失败，请检查网络连接');
      }
    };
    fetchCategories();
  }, []);

  // 2. 如果是编辑模式，加载商品详情
  useEffect(() => {
    const loadListingDetail = async () => {
      if (!isEditMode || !id) return;
      setLoading(true);
      setErrorMsg('');

      try {
        const data = await getMyListingDetail(id);
        fillForm(data);
      } catch {
        setErrorMsg('获取商品详情失败，请检查网络连接');
      } finally {
        setLoading(false);
      }
    };

    const fillForm = (data: Listing) => {
      setTitle(data.title);
      setCategory(String(data.category.id));
      setItemType(data.item_type);
      setPrice(data.price);
      setDescription(data.description);
      setDeliveryNotes(data.delivery_notes);
      setCurrentStatus(data.status);

      if (data.item_type === 'physical') {
        setCondition(data.condition || 'good');
        setPhysicalDeliveryMethod(data.physical_delivery_method || 'meetup');
      } else if (data.item_type === 'virtual' && data.virtual_valid_until) {
        // datetime-local 格式为 YYYY-MM-DDTHH:mm
        const dateObj = new Date(data.virtual_valid_until);
        const formatted = dateObj.toISOString().slice(0, 16);
        setVirtualValidUntil(formatted);
      }
      setUploadedImages(data.images ? [...data.images].sort((a, b) => a.sort_order - b.sort_order) : []);
    };

    loadListingDetail();
  }, [id, isEditMode]);

  // 3. 多图上传处理
  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const selectedFiles = Array.from(files);
    const currentImageCount = isEditMode ? uploadedImages.length : pendingImages.length;

    if (currentImageCount + selectedFiles.length > 6) {
      setErrorMsg('最多只能上传 6 张商品图片！');
      e.target.value = '';
      return;
    }

    // 单个文件大小限制 5MB 的前端防线
    for (const file of selectedFiles) {
      if (file.size > 5 * 1024 * 1024) {
        setErrorMsg(`图片 ${file.name} 超过 5MB 限制，请重新选择较小的图片。`);
        e.target.value = '';
        return;
      }
    }

    if (!isEditMode) {
      try {
        const previews = await Promise.all(selectedFiles.map((file) => readImagePreview(file)));
        const startOrder = pendingImages.length;
        setPendingImages((prev) => [
          ...prev,
          ...selectedFiles.map((file, index) => ({
            id: `${file.name}-${file.lastModified}-${startOrder + index}`,
            file,
            previewUrl: previews[index],
            sort_order: startOrder + index,
          })),
        ]);
        setErrorMsg('');
      } catch (err) {
        setErrorMsg(getErrorMessage(err, '图片预览生成失败，请重新选择图片'));
      }
      e.target.value = '';
      return;
    }

    if (!id) return;

    setSaving(true);
    try {
      // 编辑模式 + 真实接口：调用后端上传多图
      const formData = new FormData();
      for (const file of selectedFiles) {
        formData.append('images', file);
      }
      const updatedListing = await uploadListingImage(id, formData);
      setUploadedImages(
        updatedListing.images ? [...updatedListing.images].sort((a, b) => a.sort_order - b.sort_order) : []
      );
      setErrorMsg('');
    } catch (err) {
      setErrorMsg(getErrorMessage(err, '图片上传失败，请重试'));
    } finally {
      setSaving(false);
      e.target.value = '';
    }
  };

  // 4. 删除图片
  const handleImageDelete = async (imgId: number) => {
    if (!isEditMode || !id) return;
    setSaving(true);
    try {
      // 调用后端删除
      await deleteListingImage(id, imgId);
      const next = uploadedImages
        .filter((x) => x.id !== imgId)
        .map((x, idx) => ({ ...x, sort_order: idx + 1 }));
      setUploadedImages(next);
      setErrorMsg('');
    } catch (err) {
      setErrorMsg(getErrorMessage(err, '删除图片失败'));
    } finally {
      setSaving(false);
    }
  };

  const handlePendingImageDelete = (imageId: string) => {
    setPendingImages((prev) => {
      return prev
        .filter((image) => image.id !== imageId)
        .map((image, index) => ({ ...image, sort_order: index }));
    });
  };

  // 5. 图片重排 (左移/右移)
  const handleImageMove = async (index: number, direction: 'left' | 'right') => {
    if (!isEditMode || !id) return;
    if (direction === 'left' && index === 0) return;
    if (direction === 'right' && index === uploadedImages.length - 1) return;

    const nextIndex = direction === 'left' ? index - 1 : index + 1;
    const nextImages = [...uploadedImages];

    // 互换位置
    const temp = nextImages[index];
    nextImages[index] = nextImages[nextIndex];
    nextImages[nextIndex] = temp;

    // 重新校准 sort_order
    const reordered = nextImages.map((img, idx) => ({
      ...img,
      sort_order: idx + 1,
    }));

    setUploadedImages(reordered);

    try {
      await reorderListingImages(id, reordered.map((x) => x.id));
    } catch (err) {
      console.error('排序接口调用失败，但保持前端排序。', err);
    }
  };

  const handlePendingImageMove = (index: number, direction: 'left' | 'right') => {
    if (direction === 'left' && index === 0) return;
    if (direction === 'right' && index === pendingImages.length - 1) return;

    const nextIndex = direction === 'left' ? index - 1 : index + 1;
    const nextImages = [...pendingImages];
    const temp = nextImages[index];
    nextImages[index] = nextImages[nextIndex];
    nextImages[nextIndex] = temp;

    setPendingImages(nextImages.map((image, idx) => ({ ...image, sort_order: idx })));
  };

  const uploadPendingImages = async (listingId: string | number) => {
    if (pendingImages.length === 0) return;

    const formData = new FormData();
    pendingImages.forEach((image) => {
      formData.append('images', image.file);
    });
    await uploadListingImage(listingId, formData);
  };

  // 6. 表单提交 (创建 / 保存修改)
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const submitter = (e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const shouldPublish = submitter?.value === 'publish';

    setSaving(true);
    setFieldErrors({});
    setErrorMsg('');

    // 动态字段组装
    const payload: ListingPayload = {
      title,
      category: parseInt(category, 10),
      item_type: itemType,
      price,
      description,
      delivery_notes: deliveryNotes,
    };

    if (itemType === 'physical') {
      payload.condition = condition;
      payload.physical_delivery_method = physicalDeliveryMethod;
      payload.virtual_valid_until = null;
    } else {
      if (!virtualValidUntil) {
        setFieldErrors({ virtual_valid_until: '虚拟商品有效期不能为空' });
        setSaving(false);
        return;
      }
      payload.condition = null;
      payload.physical_delivery_method = null;
      payload.virtual_valid_until = new Date(virtualValidUntil).toISOString();
    }

    try {
      if (isEditMode) {
        const updatedListing = await updateListing(id!, payload);
        if (shouldPublish && updatedListing.status === 'draft') {
          await publishListing(id!);
        }
      } else {
        // 后端以草稿作为创建入口；图片上传和发布动作在草稿创建成功后顺序执行。
        const listing = await createListing(payload);
        await uploadPendingImages(listing.id);
        if (shouldPublish) {
          await publishListing(listing.id);
        }
      }

      navigate('/me/listings');
    } catch (err) {
      setErrorMsg(getErrorMessage(err, isEditMode ? '保存修改失败，请重试' : '创建商品失败，请重试'));
    } finally {
      setSaving(false);
    }
  };

  if (!user) {
    return (
      <ErrorState
        title="您尚未登录"
        message="必须登录后才能发布或修改商品。"
        onBack={() => navigate('/login')}
      />
    );
  }

  if (loading) {
    return <Loading text="正在获取商品详情..." />;
  }

  return (
    <div className="listing-form-container fade-in">
      <Card padding="lg" shadow="md" className="form-card">
        <h2 className="auth-title">{isEditMode ? '修改商品信息' : '发布闲置商品'}</h2>
        <p className="auth-subtitle">
          {isEditMode ? '更新您的商品详情及图片管理' : '创建一个商品草稿，稍后可以发布上架销售'}
        </p>

        {errorMsg && (
          <div className="alert alert-error" role="alert">
            <AlertCircle size={18} />
            <span>{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <ListingFormFields
            categoryOptions={categoryOptions}
            title={title}
            category={category}
            itemType={itemType}
            price={price}
            description={description}
            deliveryNotes={deliveryNotes}
            condition={condition}
            physicalDeliveryMethod={physicalDeliveryMethod}
            virtualValidUntil={virtualValidUntil}
            fieldErrors={fieldErrors}
            saving={saving}
            isEditMode={isEditMode}
            onTitleChange={setTitle}
            onCategoryChange={setCategory}
            onItemTypeChange={setItemType}
            onPriceChange={setPrice}
            onDescriptionChange={setDescription}
            onDeliveryNotesChange={setDeliveryNotes}
            onConditionChange={setCondition}
            onPhysicalDeliveryMethodChange={setPhysicalDeliveryMethod}
            onVirtualValidUntilChange={setVirtualValidUntil}
          />

          <ListingImageManager
            isEditMode={isEditMode}
            saving={saving}
            uploadedImages={uploadedImages}
            pendingImages={pendingImages}
            onImageUpload={handleImageUpload}
            onImageDelete={handleImageDelete}
            onPendingImageDelete={handlePendingImageDelete}
            onImageMove={handleImageMove}
            onPendingImageMove={handlePendingImageMove}
          />

          <div className="form-actions-bar">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/me/listings')}
              disabled={saving}
            >
              取消并返回
            </Button>
            <Button type="submit" name="intent" value="draft" variant="secondary" disabled={saving} loading={saving}>
              {isEditMode ? '保存修改信息' : '保存商品草稿'}
            </Button>
            {(!isEditMode || currentStatus === 'draft') && (
              <Button type="submit" name="intent" value="publish" variant="primary" disabled={saving} loading={saving}>
                {isEditMode ? '保存并发布' : '直接发布商品'}
              </Button>
            )}
          </div>
        </form>
      </Card>
    </div>
  );
};
