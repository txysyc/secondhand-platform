import { apiClient } from '../client';
import type {
  BrowseHistoryItem,
  Category,
  FavoriteItem,
  Listing,
  PaginatedResponse,
} from '../../types/listings';

interface ListingPayload {
  title: string;
  category: number;
  item_type: 'physical' | 'virtual';
  price: string;
  description: string;
  delivery_notes: string;
  condition?: 'new' | 'like_new' | 'good' | 'fair' | null;
  physical_delivery_method?: 'meetup' | 'shipping' | 'both' | null;
  virtual_valid_until?: string | null;
}

export interface ListingFilterParams {
  q?: string;
  category?: string | number;
  item_type?: string;
  min_price?: string | number;
  max_price?: string | number;
  published_after?: string;
  published_before?: string;
  sort?: string;
  page?: string | number;
  page_size?: string | number;
}

export interface MyListingFilterParams {
  q?: string;
  status?: string;
  category?: string | number;
  item_type?: string;
  min_price?: string | number;
  max_price?: string | number;
  updated_after?: string;
  updated_before?: string;
  sort?: string;
  page?: string | number;
  page_size?: string | number;
}

type ListingQueryParams = Record<string, string | number | boolean>;

/**
 * 获取启用的分类列表
 */
export const getCategories = async (): Promise<Category[]> => {
  return apiClient.get<Category[]>('/categories/');
};

/**
 * 获取公开商品列表，支持筛选、排序和分页
 */
export const getListings = async (
  params?: ListingFilterParams
): Promise<PaginatedResponse<Listing>> => {
  return apiClient.get<PaginatedResponse<Listing>>('/listings/', { params: params as ListingQueryParams });
};

/**
 * 获取特定商品的详情
 */
export const getListingDetail = async (id: string | number): Promise<Listing> => {
  return apiClient.get<Listing>(`/listings/${id}/`);
};

/**
 * 收藏指定商品
 */
export const favoriteListing = async (
  id: string | number
): Promise<{ listing_id: number; is_favorited: boolean }> => {
  return apiClient.post<{ listing_id: number; is_favorited: boolean }>(`/listings/${id}/favorite/`);
};

/**
 * 取消收藏指定商品
 */
export const unfavoriteListing = async (id: string | number): Promise<void> => {
  return apiClient.delete<void>(`/listings/${id}/favorite/`);
};

/**
 * 获取当前登录用户的收藏商品列表
 */
export const getMyFavorites = async (
  params?: { page?: string | number; page_size?: string | number }
): Promise<PaginatedResponse<FavoriteItem>> => {
  return apiClient.get<PaginatedResponse<FavoriteItem>>('/my/favorites/', { params: params as ListingQueryParams });
};

/**
 * 获取当前登录用户的浏览历史列表
 */
export const getBrowseHistory = async (
  params?: { page?: string | number; page_size?: string | number }
): Promise<PaginatedResponse<BrowseHistoryItem>> => {
  return apiClient.get<PaginatedResponse<BrowseHistoryItem>>('/my/browse-history/', { params: params as ListingQueryParams });
};

/**
 * 获取当前登录用户自己的商品详情，包含草稿和已下架商品
 */
export const getMyListingDetail = async (id: string | number): Promise<Listing> => {
  return apiClient.get<Listing>(`/my/listings/${id}/`);
};

/**
 * 获取当前登录用户的商品列表 (草稿、在售、下架等)
 */
export const getMyListings = async (
  params?: MyListingFilterParams
): Promise<PaginatedResponse<Listing>> => {
  return apiClient.get<PaginatedResponse<Listing>>('/my/listings/', { params: params as ListingQueryParams });
};

/**
 * 创建商品草稿
 */
export const createListing = async (data: ListingPayload): Promise<Listing> => {
  return apiClient.post<Listing>('/my/listings/', data);
};

/**
 * 更新自己特定的商品
 */
export const updateListing = async (
  id: string | number,
  data: Partial<ListingPayload>
): Promise<Listing> => {
  return apiClient.patch<Listing>(`/my/listings/${id}/`, data);
};

/**
 * 删除自己特定的商品
 */
export const deleteListing = async (id: string | number): Promise<void> => {
  return apiClient.delete<void>(`/my/listings/${id}/`);
};

/**
 * 发布商品 (由草稿转为在售)
 */
export const publishListing = async (id: string | number): Promise<Listing> => {
  return apiClient.post<Listing>(`/my/listings/${id}/publish/`);
};

/**
 * 下架商品
 */
export const deactivateListing = async (id: string | number): Promise<Listing> => {
  return apiClient.post<Listing>(`/my/listings/${id}/deactivate/`);
};

/**
 * 重新上架商品
 */
export const reactivateListing = async (id: string | number): Promise<Listing> => {
  return apiClient.post<Listing>(`/my/listings/${id}/reactivate/`);
};

/**
 * 上传商品图片 (使用 multipart/form-data，支持多文件，单次可传多张)
 */
export const uploadListingImage = async (
  id: string | number,
  formData: FormData
): Promise<Listing> => {
  return apiClient.post<Listing>(`/my/listings/${id}/images/`, formData);
};

/**
 * 删除商品的指定图片
 */
export const deleteListingImage = async (
  listingId: string | number,
  imageId: string | number
): Promise<void> => {
  return apiClient.delete<void>(`/my/listings/${listingId}/images/${imageId}/`);
};

/**
 * 重新排列商品的图片顺序
 */
export const reorderListingImages = async (
  id: string | number,
  imageIds: number[]
): Promise<Listing> => {
  return apiClient.post<Listing>(`/my/listings/${id}/images/reorder/`, { image_ids: imageIds });
};
