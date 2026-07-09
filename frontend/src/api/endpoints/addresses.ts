import { apiClient } from '../client';
import type { UserAddress } from '../../types/address';

/**
 * 获取当前用户的收货地址列表
 */
export const getAddresses = async (): Promise<UserAddress[]> => {
  return apiClient.get('/users/me/addresses/');
};

/**
 * 新增收货地址
 */
export const createAddress = async (
  data: Omit<UserAddress, 'id' | 'created_at' | 'updated_at'>
): Promise<UserAddress> => {
  return apiClient.post('/users/me/addresses/', data);
};

/**
 * 获取单个收货地址详情
 */
export const getAddress = async (id: number): Promise<UserAddress> => {
  return apiClient.get(`/users/me/addresses/${id}/`);
};

/**
 * 修改收货地址（partial update）
 */
export const updateAddress = async (
  id: number,
  data: Partial<Omit<UserAddress, 'id' | 'created_at' | 'updated_at'>>
): Promise<UserAddress> => {
  return apiClient.patch(`/users/me/addresses/${id}/`, data);
};

/**
 * 删除收货地址
 */
export const deleteAddress = async (id: number): Promise<null> => {
  return apiClient.delete(`/users/me/addresses/${id}/`);
};

/**
 * 将指定地址设为默认地址
 */
export const setDefaultAddress = async (id: number): Promise<UserAddress> => {
  return apiClient.post(`/users/me/addresses/${id}/set-default/`);
};
