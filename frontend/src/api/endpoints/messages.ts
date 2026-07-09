import { apiClient } from '../client';
import type { Conversation, Message } from '../../types/messages';
import type { PaginatedResponse } from '../../types/listings';

export interface CursorPaginatedMessages {
  results: Message[];
  before_cursor: number | null;
  after_cursor: number | null;
  has_more_before: boolean;
  has_more_after: boolean;
  page_size: number;
}

/**
 * 获取当前用户的会话列表
 */
export const getConversations = async (): Promise<PaginatedResponse<Conversation>> => {
  return apiClient.get('/conversations/');
};

/**
 * 发起或复用会话
 */
export const createConversation = async (
  targetUserId: string | number
): Promise<Conversation> => {
  return apiClient.post('/conversations/', { target_user_id: targetUserId });
};

/**
 * 获取会话最新一屏消息
 */
export const getConversationMessages = async (
  convId: string | number,
  limit = 20
): Promise<CursorPaginatedMessages> => {
  return apiClient.get(`/conversations/${convId}/messages/?limit=${limit}`);
};

/**
 * 获取指定消息之前的一屏历史
 */
export const getConversationMessagesBefore = async (
  convId: string | number,
  beforeId: string | number,
  limit = 20
): Promise<CursorPaginatedMessages> => {
  return apiClient.get(`/conversations/${convId}/messages/?before_id=${beforeId}&limit=${limit}`);
};

/**
 * 获取指定消息之后的新消息，用于断线重连后的增量补齐
 */
export const getConversationMessagesAfter = async (
  convId: string | number,
  afterId: string | number,
  limit = 100
): Promise<CursorPaginatedMessages> => {
  return apiClient.get(`/conversations/${convId}/messages/?after_id=${afterId}&limit=${limit}`);
};

/**
 * 通过 HTTP 发送消息 (WebSocket 故障时的兜底手段)
 */
export const sendMessageViaHttp = async (
  convId: string | number,
  content: string
): Promise<Message> => {
  return apiClient.post(`/conversations/${convId}/messages/`, { content });
};

/**
 * 标记会话中的所有消息为已读
 */
export const markConversationAsRead = async (
  convId: string | number
): Promise<{ updated_count: number }> => {
  return apiClient.post(`/conversations/${convId}/read/`);
};
