import type { User } from './auth';

export interface Category {
  id: number;
  name: string;
}

export interface ListingImage {
  id: number;
  image: string;
  image_url: string;
  sort_order: number;
}

export type ItemType = 'physical' | 'virtual';
export type ListingStatus = 'draft' | 'active' | 'reserved' | 'sold' | 'withdrawn';
export type PhysicalDeliveryMethod = 'meetup' | 'shipping' | 'both';
export type ItemCondition = 'new' | 'like_new' | 'good' | 'fair';

export interface Listing {
  id: number;
  title: string;
  category: Category;
  owner: User;
  item_type: ItemType;
  item_type_display: string;
  status: ListingStatus;
  status_display: string;
  price: string;
  description: string;
  delivery_notes: string;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  images: ListingImage[];

  // 实体商品特有字段
  condition: ItemCondition | null;
  condition_display: string | null;
  physical_delivery_method: PhysicalDeliveryMethod | null;
  physical_delivery_method_display: string | null;

  // 虚拟商品特有字段
  virtual_valid_until: string | null;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  page_size?: number;
  results: T[];
}
