import type React from 'react';
import { ImageIcon } from 'lucide-react';

import { resolveMediaUrl } from '../../../utils/media';
import type { Listing, ListingImage } from '../../../types/listings';

interface ListingGalleryProps {
  listing: Listing;
  images: ListingImage[];
  activeImageIndex: number;
  activeImage: string | null;
  onActiveImageIndexChange: (index: number) => void;
}

export const ListingGallery: React.FC<ListingGalleryProps> = ({
  listing,
  images,
  activeImageIndex,
  activeImage,
  onActiveImageIndexChange,
}) => (
  <section className="detail-gallery">
    <div className="gallery-preview-wrapper">
      {activeImage ? (
        <img src={activeImage} alt={listing.title} className="gallery-preview-img" />
      ) : (
        <div className="listing-card-placeholder gallery-preview-placeholder">
          <ImageIcon className="listing-card-placeholder-icon" size={64} strokeWidth={1.5} />
          <span>{listing.category.name}</span>
        </div>
      )}

      <div className="listing-card-badges">
        <span
          className={`card-badge ${
            listing.item_type === 'physical' ? 'card-badge-physical' : 'card-badge-virtual'
          }`}
        >
          {listing.item_type_display}
        </span>
      </div>
    </div>

    {/* 缩略图选择器。 */}
    {images.length > 1 && (
      <div className="gallery-thumbnails">
        {images.map((img, idx) => (
          <button
            key={img.id}
            onClick={() => onActiveImageIndexChange(idx)}
            className={`gallery-thumb-btn ${activeImageIndex === idx ? 'active' : ''}`}
            aria-label={`查看第 ${idx + 1} 张图片`}
          >
            <img src={resolveMediaUrl(img.image_url) || ''} alt={`缩略图 ${idx + 1}`} />
          </button>
        ))}
      </div>
    )}
  </section>
);
