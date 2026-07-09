import type { ItemType, ItemCondition, PhysicalDeliveryMethod } from '../../../types/listings';

export interface PendingListingImage {
  id: string;
  file: File;
  previewUrl: string;
  sort_order: number;
}

export interface ListingPayload {
  title: string;
  category: number;
  item_type: ItemType;
  price: string;
  description: string;
  delivery_notes: string;
  condition?: ItemCondition | null;
  physical_delivery_method?: PhysicalDeliveryMethod | null;
  virtual_valid_until?: string | null;
}
