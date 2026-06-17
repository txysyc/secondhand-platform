import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getCategories, createListing, updateListing, getMyListingDetail, uploadListingImage, deleteListingImage, reorderListingImages, publishListing } from '../../api/endpoints/listings';
import { useAuth } from '../../app/providers';
import { resolveMediaUrl } from '../../utils/media';
import type { Category, Listing, ListingImage, ListingStatus, ItemType, ItemCondition, PhysicalDeliveryMethod } from '../../types/listings';

interface PendingListingImage {
  id: string;
  file: File;
  previewUrl: string;
  sort_order: number;
}

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

  // 1. 加载分类
  useEffect(() => {
    const fetchCategories = async () => {
      try {
        const data = await getCategories();
        setCategories(data);
        if (data.length > 0) setCategory(String(data[0].id));
      } catch (err: any) {
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
      } catch (err: any) {
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
      alert('最多只能上传 6 张商品图片！');
      e.target.value = '';
      return;
    }

    // 单个文件大小限制 5MB 的前端防线
    for (const file of selectedFiles) {
      if (file.size > 5 * 1024 * 1024) {
        alert(`图片 ${file.name} 超过 5MB 限制，请重新选择较小的图片。`);
        e.target.value = '';
        return;
      }
    }

    if (!isEditMode) {
      try {
        const previews = await Promise.all(
          selectedFiles.map((file) => readImagePreview(file))
        );
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
      } catch (err: any) {
        alert(err.message || '图片预览生成失败，请重新选择图片');
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
      setUploadedImages(updatedListing.images ? [...updatedListing.images].sort((a, b) => a.sort_order - b.sort_order) : []);
    } catch (err: any) {
      alert(err.message || '图片上传失败，请重试');
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
      const next = uploadedImages.filter((x) => x.id !== imgId).map((x, idx) => ({ ...x, sort_order: idx + 1 }));
      setUploadedImages(next);
    } catch (err: any) {
      alert(err.message || '删除图片失败');
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
    } catch (err: any) {
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
    const payload: any = {
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
        const updatedListing = await updateListing(id, payload);
        if (shouldPublish && updatedListing.status === 'draft') {
          await publishListing(id);
        }
      } else {
        // 后端以草稿作为创建入口；图片上传和发布动作在草稿创建成功后顺序执行。
        const listing = await createListing(payload);
        await uploadPendingImages(listing.id);
        if (shouldPublish) {
          await publishListing(listing.id);
        }
      }

      alert(shouldPublish ? '商品已发布！' : isEditMode ? '商品信息保存成功！' : '草稿创建成功！');
      navigate('/me/listings');
    } catch (err: any) {
      setErrorMsg(err.message || (isEditMode ? '保存修改失败，请重试' : '创建商品失败，请重试'));
    } finally {
      setSaving(false);
    }
  };

  if (!user) {
    return (
      <div className="placeholder-card error-card">
        <h2>⚠️ 您尚未登录</h2>
        <p>必须登录后才能发布或修改商品。</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="loading-container">
        <div className="spinner"></div>
        <p>正在获取商品详情...</p>
      </div>
    );
  }

  return (
    <div className="listing-form-container fade-in">
      <div className="form-card">
        <h2 className="auth-title" style={{ marginBottom: '8px' }}>
          {isEditMode ? '修改商品信息' : '发布闲置商品'}
        </h2>
        <p className="auth-subtitle" style={{ marginBottom: '32px' }}>
          {isEditMode ? '更新您的商品详情及图片管理' : '创建一个商品草稿，稍后可以发布上架销售'}
        </p>

        {errorMsg && (
          <div className="alert alert-error">
            <span>⚠️ {errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* 商品标题 */}
          <div className="form-group">
            <label htmlFor="title">商品标题</label>
            <input
              id="title"
              type="text"
              className="form-control"
              placeholder="请输入商品标题 (例如：品牌、型号、关键规格)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={saving}
              required
            />
          </div>

          {/* 分类与交付类别 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <div className="form-group">
              <label htmlFor="category">商品分类</label>
              <select
                id="category"
                className="form-control"
                style={{ cursor: 'pointer' }}
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                disabled={saving}
              >
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="itemType">交付类别</label>
              <select
                id="itemType"
                className="form-control"
                style={{ cursor: 'pointer' }}
                value={itemType}
                onChange={(e) => setItemType(e.target.value as ItemType)}
                disabled={saving || isEditMode} // 编辑模式通常不允许修改商品的大交付类别
              >
                <option value="physical">实体商品</option>
                <option value="virtual">虚拟商品 (卡券/兑换码等)</option>
              </select>
            </div>
          </div>

          {/* 价格 */}
          <div className="form-group">
            <label htmlFor="price">转让价格 (元)</label>
            <div className="price-input-wrapper">
              <span className="price-currency" style={{ fontSize: '1rem', left: '16px' }}>¥</span>
              <input
                id="price"
                type="number"
                step="0.01"
                min="0"
                className="form-control"
                style={{ paddingLeft: '32px' }}
                placeholder="请输入转让价格"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                disabled={saving}
                required
              />
            </div>
          </div>

          {/* 动态属性表单配置 */}
          <div className="form-specs-section">
            {itemType === 'physical' ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label htmlFor="condition">商品成色</label>
                  <select
                    id="condition"
                    className="form-control"
                    style={{ cursor: 'pointer' }}
                    value={condition}
                    onChange={(e) => setCondition(e.target.value as ItemCondition)}
                    disabled={saving}
                  >
                    <option value="new">全新 (未拆封/未使用)</option>
                    <option value="like_new">九五新 (几乎无使用痕迹)</option>
                    <option value="good">九成新 (轻微使用痕迹)</option>
                    <option value="fair">八成新及以下 (有明显瑕疵/使用痕迹)</option>
                  </select>
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label htmlFor="deliveryMethod">建议交付方式</label>
                  <select
                    id="deliveryMethod"
                    className="form-control"
                    style={{ cursor: 'pointer' }}
                    value={physicalDeliveryMethod}
                    onChange={(e) => setPhysicalDeliveryMethod(e.target.value as PhysicalDeliveryMethod)}
                    disabled={saving}
                  >
                    <option value="meetup">同城当面面交</option>
                    <option value="shipping">邮寄顺丰包邮</option>
                    <option value="both">均可</option>
                  </select>
                </div>
              </div>
            ) : (
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label htmlFor="validUntil">虚拟兑换码有效期</label>
                <input
                  id="validUntil"
                  type="datetime-local"
                  className={`form-control ${fieldErrors.virtual_valid_until ? 'is-invalid' : ''}`}
                  value={virtualValidUntil}
                  onChange={(e) => setVirtualValidUntil(e.target.value)}
                  disabled={saving}
                />
                {fieldErrors.virtual_valid_until && (
                  <span className="invalid-feedback">{fieldErrors.virtual_valid_until}</span>
                )}
              </div>
            )}
          </div>

          {/* 商品详细描述 */}
          <div className="form-group">
            <label htmlFor="description">商品描述</label>
            <textarea
              id="description"
              className="form-control"
              style={{ minHeight: '140px', resize: 'vertical' }}
              placeholder="请详细说明商品的规格参数、购买途径、使用痕迹、功能瑕疵等，有利于更快卖出"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={saving}
              required
            />
          </div>

          {/* 交易交易说明 */}
          <div className="form-group">
            <label htmlFor="deliveryNotes">补充交易说明 (可选)</label>
            <input
              id="deliveryNotes"
              type="text"
              className="form-control"
              placeholder="例：同城可约地铁站面交；谢绝砍价；不退换"
              value={deliveryNotes}
              onChange={(e) => setDeliveryNotes(e.target.value)}
              disabled={saving}
            />
          </div>

          {/* 多图上传及重排区域 */}
          {isEditMode ? (
            <div className="image-manager-section">
              <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500, fontSize: '0.9rem', color: 'var(--text-main)' }}>
                商品图片管理 ({uploadedImages.length}/6)
              </label>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: '12px' }}>
                支持最多上传 6 张高清大图，首图将被用作搜索封面。支持左右方向键进行排序。
              </p>

              <div className="image-manager-grid">
                {uploadedImages.map((img, idx) => (
                  <div key={img.id} className="image-manager-item">
                    <div
                      className="image-manager-img"
                      aria-label="商品图预览"
                      style={{
                        backgroundImage: `url("${resolveMediaUrl(img.image_url) || ''}")`,
                        backgroundPosition: 'center',
                        backgroundRepeat: 'no-repeat',
                        backgroundSize: 'cover',
                      }}
                    />
                    
                    {/* 删除图片 */}
                    <button
                      type="button"
                      onClick={() => handleImageDelete(img.id)}
                      className="image-manager-delete-btn"
                      disabled={saving}
                      title="删除"
                    >
                      ×
                    </button>

                    {/* 左右移动控制 */}
                    <div className="image-manager-controls">
                      <button
                        type="button"
                        onClick={() => handleImageMove(idx, 'left')}
                        disabled={idx === 0 || saving}
                        className="image-control-btn"
                        title="前移"
                      >
                        ←
                      </button>
                      <button
                        type="button"
                        onClick={() => handleImageMove(idx, 'right')}
                        disabled={idx === uploadedImages.length - 1 || saving}
                        className="image-control-btn"
                        title="后移"
                      >
                        →
                      </button>
                    </div>
                  </div>
                ))}

                {/* 上传卡片 */}
                {uploadedImages.length < 6 && (
                  <div className="image-manager-upload-card">
                    <span className="image-manager-upload-icon">📷</span>
                    <span>添加图片</span>
                    <input
                      type="file"
                      multiple
                      accept="image/*"
                      style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', opacity: 0, cursor: 'pointer' }}
                      onChange={handleImageUpload}
                      disabled={saving}
                    />
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="image-manager-section">
              <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500, fontSize: '0.9rem', color: 'var(--text-main)' }}>
                商品图片 ({pendingImages.length}/6)
              </label>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: '12px' }}>
                可先选择图片，提交后会自动创建草稿、上传图片，并按您的选择保存或发布。
              </p>

              <div className="image-manager-grid">
                {pendingImages.map((img, idx) => (
                  <div key={img.id} className="image-manager-item">
                    <div
                      className="image-manager-img"
                      aria-label="商品图预览"
                      style={{
                        backgroundImage: `url("${img.previewUrl}")`,
                        backgroundPosition: 'center',
                        backgroundRepeat: 'no-repeat',
                        backgroundSize: 'cover',
                      }}
                    />

                    <button
                      type="button"
                      onClick={() => handlePendingImageDelete(img.id)}
                      className="image-manager-delete-btn"
                      disabled={saving}
                      title="删除"
                    >
                      ×
                    </button>

                    <div className="image-manager-controls">
                      <button
                        type="button"
                        onClick={() => handlePendingImageMove(idx, 'left')}
                        disabled={idx === 0 || saving}
                        className="image-control-btn"
                        title="前移"
                      >
                        ←
                      </button>
                      <button
                        type="button"
                        onClick={() => handlePendingImageMove(idx, 'right')}
                        disabled={idx === pendingImages.length - 1 || saving}
                        className="image-control-btn"
                        title="后移"
                      >
                        →
                      </button>
                    </div>
                  </div>
                ))}

                {pendingImages.length < 6 && (
                  <div className="image-manager-upload-card">
                    <span className="image-manager-upload-icon">📷</span>
                    <span>添加图片</span>
                    <input
                      type="file"
                      multiple
                      accept="image/*"
                      style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', opacity: 0, cursor: 'pointer' }}
                      onChange={handleImageUpload}
                      disabled={saving}
                    />
                  </div>
                )}
              </div>

              <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', margin: 0 }}>
                💡 提示：至少填写完整商品信息后，可以保存为草稿，也可以直接发布上架。
              </p>
            </div>
          )}

          <div style={{ display: 'flex', gap: '16px', marginTop: '32px' }}>
            <button
              type="button"
              onClick={() => navigate('/me/listings')}
              className="btn btn-outline"
              style={{ flex: 1 }}
              disabled={saving}
            >
              取消并返回
            </button>
            <button
              type="submit"
              name="intent"
              value="draft"
              className="btn btn-primary"
              style={{ flex: 2 }}
              disabled={saving}
            >
              {saving ? '正在保存...' : isEditMode ? '保存修改信息' : '保存商品草稿'}
            </button>
            {(!isEditMode || currentStatus === 'draft') && (
              <button
                type="submit"
                name="intent"
                value="publish"
                className="btn btn-primary"
                style={{ flex: 2 }}
                disabled={saving}
              >
                {saving ? '正在发布...' : isEditMode ? '保存并发布' : '直接发布商品'}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
};
