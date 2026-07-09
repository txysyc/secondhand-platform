import type React from 'react';
import { ArrowLeft, ArrowRight, Camera, Trash2 } from 'lucide-react';

import { resolveMediaUrl } from '../../../utils/media';
import type { ListingImage } from '../../../types/listings';
import type { PendingListingImage } from './types';

interface ListingImageManagerProps {
  isEditMode: boolean;
  saving: boolean;
  uploadedImages: ListingImage[];
  pendingImages: PendingListingImage[];
  onImageUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onImageDelete: (imageId: number) => void;
  onPendingImageDelete: (imageId: string) => void;
  onImageMove: (index: number, direction: 'left' | 'right') => void;
  onPendingImageMove: (index: number, direction: 'left' | 'right') => void;
}

export const ListingImageManager: React.FC<ListingImageManagerProps> = ({
  isEditMode,
  saving,
  uploadedImages,
  pendingImages,
  onImageUpload,
  onImageDelete,
  onPendingImageDelete,
  onImageMove,
  onPendingImageMove,
}) => {
  if (isEditMode) {
    return (
      <div className="image-manager-section">
        <div className="image-manager-section-title">商品图片管理 ({uploadedImages.length}/6)</div>
        <p className="image-manager-hint">
          支持最多上传 6 张高清大图，首图将被用作搜索封面。支持左右方向键进行排序。
        </p>

        <div className="image-manager-grid">
          {uploadedImages.map((img, idx) => (
            <div key={img.id} className="image-manager-item">
              <img
                src={resolveMediaUrl(img.image_url) || undefined}
                alt={`商品图 ${idx + 1}`}
                className="image-manager-img"
              />

              {/* 编辑模式删除已上传图片。 */}
              <button
                type="button"
                onClick={() => onImageDelete(img.id)}
                className="image-manager-delete-btn"
                disabled={saving}
                title="删除"
              >
                <Trash2 size={14} />
              </button>

              {/* 编辑模式调整已上传图片顺序。 */}
              <div className="image-manager-controls">
                <button
                  type="button"
                  onClick={() => onImageMove(idx, 'left')}
                  disabled={idx === 0 || saving}
                  className="image-control-btn"
                  title="前移"
                >
                  <ArrowLeft size={16} />
                </button>
                <button
                  type="button"
                  onClick={() => onImageMove(idx, 'right')}
                  disabled={idx === uploadedImages.length - 1 || saving}
                  className="image-control-btn"
                  title="后移"
                >
                  <ArrowRight size={16} />
                </button>
              </div>
            </div>
          ))}

          {uploadedImages.length < 6 && (
            <div className="image-manager-upload-card">
              <Camera className="image-manager-upload-icon" size={32} />
              <span>添加图片</span>
              <input
                type="file"
                multiple
                accept="image/*"
                className="image-manager-file-input"
                onChange={onImageUpload}
                disabled={saving}
              />
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="image-manager-section">
      <div className="image-manager-section-title">商品图片 ({pendingImages.length}/6)</div>
      <p className="image-manager-hint">
        可先选择图片，提交后会自动创建草稿、上传图片，并按您的选择保存或发布。
      </p>

      <div className="image-manager-grid">
        {pendingImages.map((img, idx) => (
          <div key={img.id} className="image-manager-item">
            <img src={img.previewUrl} alt={`商品图预览 ${idx + 1}`} className="image-manager-img" />

            {/* 新建模式删除本地待上传图片。 */}
            <button
              type="button"
              onClick={() => onPendingImageDelete(img.id)}
              className="image-manager-delete-btn"
              disabled={saving}
              title="删除"
            >
              <Trash2 size={14} />
            </button>

            {/* 新建模式调整本地待上传图片顺序。 */}
            <div className="image-manager-controls">
              <button
                type="button"
                onClick={() => onPendingImageMove(idx, 'left')}
                disabled={idx === 0 || saving}
                className="image-control-btn"
                title="前移"
              >
                <ArrowLeft size={16} />
              </button>
              <button
                type="button"
                onClick={() => onPendingImageMove(idx, 'right')}
                disabled={idx === pendingImages.length - 1 || saving}
                className="image-control-btn"
                title="后移"
              >
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        ))}

        {pendingImages.length < 6 && (
          <div className="image-manager-upload-card">
            <Camera className="image-manager-upload-icon" size={32} />
            <span>添加图片</span>
            <input
              type="file"
              multiple
              accept="image/*"
              className="image-manager-file-input"
              onChange={onImageUpload}
              disabled={saving}
            />
          </div>
        )}
      </div>

      <p className="image-manager-tip">
        提示：至少填写完整商品信息后，可以保存为草稿，也可以直接发布上架。
      </p>
    </div>
  );
};
