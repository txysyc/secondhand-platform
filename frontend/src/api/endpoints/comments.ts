import { apiClient } from '../client';
import type { Comment } from '../../types/comments';

/**
 * 获取指定商品的评论列表 (包含单层回复)
 */
export const getListingComments = async (
  listingId: string | number
): Promise<Comment[]> => {
  return apiClient.get(`/listings/${listingId}/comments/`);
};

/**
 * 在指定商品下发表顶层评论
 */
export const createListingComment = async (
  listingId: string | number,
  content: string
): Promise<Comment> => {
  return apiClient.post(`/listings/${listingId}/comments/`, { content });
};

/**
 * 回复一条评论 (创建二级评论)
 */
export const createCommentReply = async (
  commentId: string | number,
  content: string
): Promise<Comment> => {
  return apiClient.post(`/comments/${commentId}/replies/`, { content });
};

/**
 * 删除评论 (只能删除自己发表的评论)
 */
export const deleteComment = async (
  commentId: string | number
): Promise<void> => {
  return apiClient.delete(`/comments/${commentId}/`);
};
