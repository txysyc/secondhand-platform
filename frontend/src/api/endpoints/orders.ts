import { apiClient } from '../client';
import type { Order } from '../../types/orders';
import type { PaginatedResponse } from '../../types/listings';

/**
 * 创建订单
 */
export const createOrder = async (
  listingId: string | number
): Promise<Order> => {
  return apiClient.post(`/listings/${listingId}/orders/`);
};

/**
 * 获取买家订单列表
 */
export const getBuyerOrders = async (): Promise<PaginatedResponse<Order>> => {
  return apiClient.get('/orders/buyer/');
};

/**
 * 获取卖家订单列表
 */
export const getSellerOrders = async (): Promise<PaginatedResponse<Order>> => {
  return apiClient.get('/orders/seller/');
};

/**
 * 获取订单详情
 */
export const getOrderDetail = async (
  id: string | number
): Promise<Order> => {
  return apiClient.get(`/orders/${id}/`);
};

/**
 * 模拟支付订单 (买家动作)
 */
export const payOrder = async (
  id: string | number
): Promise<Order> => {
  return apiClient.post(`/orders/${id}/pay/`);
};

/**
 * 卖家确认发货 (卖家动作)
 */
export const confirmOrderDelivery = async (
  id: string | number
): Promise<Order> => {
  return apiClient.post(`/orders/${id}/confirm-delivery/`);
};

/**
 * 买家确认收货 (买家动作)
 */
export const confirmOrderReceipt = async (
  id: string | number
): Promise<Order> => {
  return apiClient.post(`/orders/${id}/confirm-receipt/`);
};
