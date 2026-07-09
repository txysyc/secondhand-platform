import type React from 'react';
import { ImageIcon } from 'lucide-react';

import { resolveAvatarUrl, resolveMediaUrl } from '../../../utils/media';
import type { Listing } from '../../../types/listings';

interface ListingGridProps {
  listings: Listing[];
  onOpenListing: (listingId: number) => void;
}

const getCoverImage = (item: Listing) => {
  if (item.images && item.images.length > 0) {
    // 优先显示排序最靠前的商品图片。
    const sorted = [...item.images].sort((a, b) => a.sort_order - b.sort_order);
    return resolveMediaUrl(sorted[0].image_url);
  }
  return null;
};

export const ListingGrid: React.FC<ListingGridProps> = ({ listings, onOpenListing }) => (
  <div className="listings-grid">
    {listings.map((item) => {
      const cover = getCoverImage(item);
      return (
        <article
          key={item.id}
          className="listing-card"
          onClick={() => onOpenListing(item.id)}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              onOpenListing(item.id);
            }
          }}
          aria-label={`查看商品：${item.title}`}
        >
          <div className="listing-card-image-wrapper">
            {cover ? (
              <img src={cover} alt={item.title} className="listing-card-image" loading="lazy" />
            ) : (
              <div className="listing-card-placeholder">
                <ImageIcon className="listing-card-placeholder-icon" size={48} strokeWidth={1.5} />
                <span>{item.category.name}</span>
              </div>
            )}

            <div className="listing-card-badges">
              <span
                className={`card-badge ${
                  item.item_type === 'physical' ? 'card-badge-physical' : 'card-badge-virtual'
                }`}
              >
                {item.item_type_display}
              </span>
            </div>

            {item.status !== 'active' && <span className="card-badge-status">{item.status_display}</span>}
          </div>

          <div className="listing-card-content">
            <span className="listing-card-category">{item.category.name}</span>
            <h2 className="listing-card-title">{item.title}</h2>

            <div className="listing-card-price-row">
              <span className="listing-card-price">{item.price}</span>
              {item.item_type === 'physical' && item.condition_display && (
                <span className="listing-card-condition">{item.condition_display}</span>
              )}
            </div>
          </div>

          <div className="listing-card-footer">
            <div className="listing-card-owner">
              <img
                src={resolveAvatarUrl(item.owner.profile?.avatar_url, item.owner.username)}
                alt={item.owner.username}
                className="listing-card-avatar"
              />
              <span>{item.owner.profile?.nickname || item.owner.username}</span>
            </div>
            <span>
              {new Date(item.created_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })}
            </span>
          </div>
        </article>
      );
    })}
  </div>
);
