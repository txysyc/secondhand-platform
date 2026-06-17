import { apiClient } from '../client';
import type { User } from '../../types/auth';

export interface PublicProfileListingSummary {
  id: number;
  title: string;
  price: string;
  item_type: 'physical' | 'virtual';
  category_name: string;
}

export interface PublicProfileResponse {
  id: number;
  username: string;
  profile: {
    nickname: string;
    avatar: string | null;
    avatar_url: string | null;
    bio: string;
  };
  listings: PublicProfileListingSummary[];
}

/**
 * 更新当前登录用户的个人资料 (支持头像图片上传，使用 multipart/form-data)
 */
export const updateProfile = async (formData: FormData): Promise<User> => {
  return apiClient.patch('/users/me/', formData);
};

/**
 * 获取公开的用户主页资料与发布的商品摘要
 */
export const getUserPublicProfile = async (id: string | number): Promise<PublicProfileResponse> => {
  return apiClient.get(`/users/${id}/`);
};
