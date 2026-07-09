import type React from 'react';
import { ImageIcon } from 'lucide-react';

import { Badge, Button } from '../../../components/ui';
import type { BadgeVariant } from '../../../components/ui';
import { resolveMediaUrl } from '../../../utils/media';
import type { Listing, ListingStatus } from '../../../types/listings';

type ActionType = 'publish' | 'deactivate' | 'reactivate' | 'delete';

const STATUS_VARIANT_MAP: Record<ListingStatus, BadgeVariant> = {
  draft: 'draft',
  active: 'active',
  reserved: 'warning',
  sold: 'sold',
  withdrawn: 'inactive',
};

interface MyListingsRowsProps {
  listings: Listing[];
  actionLoadingId: number | null;
  onOpenListing: (item: Listing) => void;
  onEditListing: (listingId: number) => void;
  onAction: (listingId: number, actionType: ActionType) => void;
}

const getCoverImage = (item: Listing) => {
  if (item.images && item.images.length > 0) {
    // 优先显示排序最靠前的商品图片。
    const sorted = [...item.images].sort((a, b) => a.sort_order - b.sort_order);
    return resolveMediaUrl(sorted[0].image_url);
  }
  return null;
};

export const MyListingsRows: React.FC<MyListingsRowsProps> = ({
  listings,
  actionLoadingId,
  onOpenListing,
  onEditListing,
  onAction,
}) => (
  <div className="my-listings-list">
    {listings.map((item) => {
      const cover = getCoverImage(item);
      const isActionBusy = actionLoadingId === item.id;

      return (
        <div
          key={item.id}
          className="my-listing-row"
          onClick={() => onOpenListing(item)}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              onOpenListing(item);
            }
          }}
          title={item.status === 'draft' ? '编辑草稿' : '查看商品详情'}
        >
          <div className="my-listing-thumb-wrapper">
            {cover ? (
              <img src={cover} alt={item.title} className="my-listing-thumb" loading="lazy" />
            ) : (
              <ImageIcon className="my-listing-thumb-icon" size={36} strokeWidth={1.5} />
            )}
          </div>

          <div className="my-listing-info">
            <div className="my-listing-title-row">
              <Badge variant={STATUS_VARIANT_MAP[item.status]} size="sm">
                {item.status_display}
              </Badge>
              <h3 className="my-listing-title" title={item.title}>
                {item.title}
              </h3>
            </div>
            <div className="my-listing-meta">
              <span className="my-listing-price">¥ {item.price}</span>
              <span>分类: {item.category.name}</span>
              <span>类别: {item.item_type_display}</span>
              <span>更新: {new Date(item.updated_at).toLocaleDateString('zh-CN')}</span>
            </div>
          </div>

          <div className="my-listing-actions" onClick={(event) => event.stopPropagation()} role="group">
            {item.status === 'draft' && (
              <>
                <Button variant="outline" size="sm" disabled={isActionBusy} onClick={() => onEditListing(item.id)}>
                  编辑
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  disabled={isActionBusy}
                  loading={isActionBusy}
                  onClick={() => onAction(item.id, 'publish')}
                >
                  发布
                </Button>
              </>
            )}

            {item.status === 'active' && (
              <>
                <Button variant="outline" size="sm" disabled={isActionBusy} onClick={() => onEditListing(item.id)}>
                  编辑/多图
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  disabled={isActionBusy}
                  loading={isActionBusy}
                  onClick={() => onAction(item.id, 'deactivate')}
                >
                  下架
                </Button>
              </>
            )}

            {item.status === 'withdrawn' && (
              <>
                <Button
                  variant="primary"
                  size="sm"
                  disabled={isActionBusy}
                  loading={isActionBusy}
                  onClick={() => onAction(item.id, 'reactivate')}
                >
                  重新上架
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  disabled={isActionBusy}
                  loading={isActionBusy}
                  onClick={() => onAction(item.id, 'delete')}
                >
                  删除
                </Button>
              </>
            )}

            {item.status === 'sold' && <span className="my-listing-status-note">交易已完成</span>}
          </div>
        </div>
      );
    })}
  </div>
);
