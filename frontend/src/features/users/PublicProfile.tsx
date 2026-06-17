import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PackageOpen, Monitor, BookOpen, Shirt, Gift } from 'lucide-react';
import { getUserPublicProfile } from '../../api/endpoints/users';
import { resolveMediaUrl } from '../../utils/media';
import { Card } from '../../components/ui/Card';
import { Avatar } from '../../components/ui/Avatar';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import type { PublicProfileResponse, PublicProfileListingSummary } from '../../api/endpoints/users';

// 公开主页商品类型可能包含图片字段，对其做本地扩展以兼容类型
interface PublicProfileListingWithImages extends PublicProfileListingSummary {
  images?: Array<{ image_url: string; sort_order: number }>;
}

/**
 * 根据后端返回的图片信息获取商品封面。
 * 与 MyListings / ListingList 的 getCoverImage 逻辑保持一致。
 */
const getCoverImage = (item: PublicProfileListingWithImages): string | null => {
  if (item.images && item.images.length > 0) {
    const sorted = [...item.images].sort((a, b) => a.sort_order - b.sort_order);
    return resolveMediaUrl(sorted[0].image_url);
  }
  return null;
};

/**
 * 根据商品分类返回对应的 Lucide 图标占位。
 */
const getCategoryIcon = (categoryName: string) => {
  if (categoryName.includes('数码')) return <Monitor size={40} />;
  if (categoryName.includes('图书')) return <BookOpen size={40} />;
  if (categoryName.includes('服')) return <Shirt size={40} />;
  return <Gift size={40} />;
};

export const PublicProfile: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [profileData, setProfileData] = useState<PublicProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    const fetchPublicProfile = async () => {
      if (!id) return;
      setLoading(true);
      setErrorMsg('');

      try {
        const data = await getUserPublicProfile(id);
        setProfileData(data);
      } catch (err: unknown) {
        const error = err as { message?: string };
        console.error(`无法加载公开用户资料 (ID: ${id})：`, error);
        setErrorMsg('加载公开用户资料失败，请检查网络连接。');
      } finally {
        setLoading(false);
      }
    };

    fetchPublicProfile();
  }, [id]);

  if (loading) {
    return (
      <div className="loading-container">
        <div className="spinner" />
        <p>正在获取用户公开主页...</p>
      </div>
    );
  }

  if (errorMsg || !profileData) {
    return (
      <ErrorState
        title="获取主页资料失败"
        message={errorMsg || '加载信息出错，请重试。'}
        onBack={() => navigate('/')}
      />
    );
  }

  const listings = profileData.listings as PublicProfileListingWithImages[];

  return (
    <div className="public-profile-container fade-in">
      {/* 头部信息 */}
      <Card padding="lg" shadow="md" className="profile-header-card">
        <div className="profile-header-content">
          <Avatar
            src={profileData.profile.avatar_url}
            username={profileData.username}
            alt={profileData.profile.nickname || profileData.username}
            size="xl"
          />
          <div className="profile-header-info">
            <h2 className="profile-name">
              {profileData.profile.nickname || profileData.username}
            </h2>
            <p className="profile-username">用户名: @{profileData.username}</p>
            <p className="profile-bio">
              {profileData.profile.bio || '尚未设置个人简介'}
            </p>
          </div>
        </div>
      </Card>

      {/* 发布的商品 */}
      <section className="profile-listings-section" aria-labelledby="listings-heading">
        <h3 id="listings-heading" className="detail-section-title">
          发布的商品 ({listings.length})
        </h3>

        {listings.length === 0 ? (
          <EmptyState
            icon={<PackageOpen size={48} aria-hidden="true" />}
            title="该用户还没有发布商品"
            description="去看看其他卖家的闲置好物吧"
            action={{
              label: '浏览商品',
              onClick: () => navigate('/'),
              variant: 'primary',
            }}
          />
        ) : (
          <div className="public-profile-grid">
            {listings.map((item) => {
              const cover = getCoverImage(item);

              return (
                <article
                  key={item.id}
                  className="listing-card"
                  onClick={() => navigate(`/listings/${item.id}`)}
                  tabIndex={0}
                  role="button"
                  aria-label={`${item.title}，售价 ${item.price} 元`}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      navigate(`/listings/${item.id}`);
                    }
                  }}
                >
                  <div className="listing-card-image-wrapper">
                    {cover ? (
                      <img
                        src={cover}
                        alt={item.title}
                        className="listing-card-image"
                        loading="lazy"
                      />
                    ) : (
                      <div className="listing-card-placeholder">
                        <span className="listing-card-placeholder-icon">
                          {getCategoryIcon(item.category_name)}
                        </span>
                        <span>{item.category_name}</span>
                      </div>
                    )}
                    <div className="listing-card-badges">
                      <Badge
                        variant={item.item_type === 'physical' ? 'primary' : 'info'}
                        size="sm"
                      >
                        {item.item_type === 'physical' ? '实体' : '虚拟'}
                      </Badge>
                    </div>
                  </div>
                  <div className="listing-card-content">
                    <h4 className="listing-card-title">{item.title}</h4>
                    <div className="listing-card-price-row">
                      <span className="listing-card-price">{item.price}</span>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
};
