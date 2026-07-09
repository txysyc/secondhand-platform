import { apiClient } from '../client';
import type { Category, Listing, PaginatedResponse } from '../../types/listings';

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
  return apiClient.get('/categories/');
};

/**
 * 获取公开商品列表，支持筛选、排序和分页
 */
export const getListings = async (
  params?: ListingFilterParams
): Promise<PaginatedResponse<Listing>> => {
  return apiClient.get('/listings/', { params: params as ListingQueryParams });
};

/**
 * 获取特定商品的详情
 */
export const getListingDetail = async (id: string | number): Promise<Listing> => {
  return apiClient.get(`/listings/${id}/`);
};

/**
 * 获取当前登录用户自己的商品详情，包含草稿和已下架商品
 */
export const getMyListingDetail = async (id: string | number): Promise<Listing> => {
  return apiClient.get(`/my/listings/${id}/`);
};

/**
 * 获取当前登录用户的商品列表 (草稿、在售、下架等)
 */
export const getMyListings = async (
  params?: MyListingFilterParams
): Promise<PaginatedResponse<Listing>> => {
  return apiClient.get('/my/listings/', { params: params as ListingQueryParams });
};

/**
 * 创建商品草稿
 */
export const createListing = async (data: any): Promise<Listing> => {
  return apiClient.post('/my/listings/', data);
};

/**
 * 更新自己特定的商品
 */
export const updateListing = async (id: string | number, data: any): Promise<Listing> => {
  return apiClient.patch(`/my/listings/${id}/`, data);
};

/**
 * 删除自己特定的商品
 */
export const deleteListing = async (id: string | number): Promise<void> => {
  return apiClient.delete(`/my/listings/${id}/`);
};

/**
 * 发布商品 (由草稿转为在售)
 */
export const publishListing = async (id: string | number): Promise<Listing> => {
  return apiClient.post(`/my/listings/${id}/publish/`);
};

/**
 * 下架商品
 */
export const deactivateListing = async (id: string | number): Promise<Listing> => {
  return apiClient.post(`/my/listings/${id}/deactivate/`);
};

/**
 * 重新上架商品
 */
export const reactivateListing = async (id: string | number): Promise<Listing> => {
  return apiClient.post(`/my/listings/${id}/reactivate/`);
};

/**
 * 上传商品图片 (使用 multipart/form-data，支持多文件，单次可传多张)
 */
export const uploadListingImage = async (
  id: string | number,
  formData: FormData
): Promise<any> => {
  return apiClient.post(`/my/listings/${id}/images/`, formData);
};

/**
 * 删除商品的指定图片
 */
export const deleteListingImage = async (
  listingId: string | number,
  imageId: string | number
): Promise<void> => {
  return apiClient.delete(`/my/listings/${listingId}/images/${imageId}/`);
};

/**
 * 重新排列商品的图片顺序
 */
export const reorderListingImages = async (
  id: string | number,
  imageIds: number[]
): Promise<any> => {
  return apiClient.post(`/my/listings/${id}/images/reorder/`, { image_ids: imageIds });
};
