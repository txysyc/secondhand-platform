import type { ListingImage } from './listings';

export interface ShippingAddressSnapshot {
  recipient_name: string;
  phone: string;
  province: string;
  city: string;
  district: string;
  detail_address: string;
}

export interface OrderUser {
  id: number;
  username: string;
}

export interface OrderRating {
  score: number;
  created_at: string;
}

export interface OrderListingCategory {
  id: number;
  name: string;
}

export interface OrderListing {
  id: number;
  title: string;
  category: OrderListingCategory;
  owner: {
    id: number;
    username: string;
  };
  images: ListingImage[];
  item_type: 'physical' | 'virtual';
  item_type_display: string;
  status: string;
  status_display: string;
}

export interface Order {
  id: number;
  buyer: OrderUser | null;
  buyer_display_name: string;
  seller: OrderUser | null;
  seller_display_name: string;
  listing: OrderListing | null;
  listing_title_snapshot: string;
  listing_image_snapshot: string | null;
  status: 'pending_payment' | 'awaiting_shipment' | 'awaiting_receipt' | 'signed' | 'completed' | 'cancelled';
  status_display: string;
  order_price: string;
  payment_deadline: string | null;
  paid_at: string | null;
  shipped_at: string | null;
  logistics_signed_due_at: string | null;
  signed_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  shipping_address_snapshot: ShippingAddressSnapshot | null;
  created_at: string;
  updated_at: string;
  viewer_role: 'buyer' | 'seller';
  is_expired: boolean;
  available_actions: ('pay' | 'confirm_delivery' | 'confirm_receipt' | 'rate')[];
  buyer_rating: OrderRating | null;
}
