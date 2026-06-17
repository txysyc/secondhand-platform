import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getUserPublicProfile } from '../../api/endpoints/users';
import { resolveAvatarUrl } from '../../utils/media';
import type { PublicProfileResponse } from '../../api/endpoints/users';

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
      } catch (err: any) {
        console.error(`无法加载公开用户资料 (ID: ${id})：`, err);
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
        <div className="spinner"></div>
        <p>正在获取用户公开主页...</p>
      </div>
    );
  }

  if (errorMsg || !profileData) {
    return (
      <div className="placeholder-card error-card">
        <h2>⚠️ 获取主页资料失败</h2>
        <p>{errorMsg || '加载信息出错，请重试。'}</p>
        <button onClick={() => navigate('/')} className="btn btn-primary btn-sm">
          返回首页
        </button>
      </div>
    );
  }

  return (
    <div className="public-profile-container fade-in" style={{ maxWidth: '800px', margin: '0 auto' }}>
      {/* 头部信息 */}
      <div className="profile-card" style={{ marginBottom: '32px', display: 'flex', gap: '24px', alignItems: 'center' }}>
        <img
          src={resolveAvatarUrl(profileData.profile.avatar_url, profileData.username)}
          alt={profileData.username}
          style={{ width: '80px', height: '80px', borderRadius: '50%', objectFit: 'cover', border: '2px solid var(--border-color)' }}
        />
        <div style={{ flexGrow: 1 }}>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '6px' }}>
            {profileData.profile.nickname || profileData.username}
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '8px' }}>
            用户名: @{profileData.username}
          </p>
          <p style={{ color: '#334155', fontSize: '0.95rem' }}>
            {profileData.profile.bio || '尚未设置个人简介'}
          </p>
        </div>
      </div>

      {/* 发布的商品 */}
      <div>
        <h3 className="detail-section-title" style={{ marginBottom: '20px' }}>
          发布的商品 ({profileData.listings.length})
        </h3>
        
        {profileData.listings.length === 0 ? (
          <div className="placeholder-card" style={{ padding: '32px' }}>
            <p>该用户当前没有发布任何商品。</p>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            {profileData.listings.map((item) => (
              <div
                key={item.id}
                className="listing-card"
                onClick={() => navigate(`/listings/${item.id}`)}
                style={{ cursor: 'pointer' }}
              >
                <div className="listing-card-image-wrapper" style={{ aspectRatio: '16/9' }}>
                  <div className="listing-card-placeholder">
                    <span className="listing-card-placeholder-icon">
                      {item.category_name.includes('数码') ? '💻' : item.category_name.includes('图书') ? '📚' : '👕'}
                    </span>
                    <span>{item.category_name}</span>
                  </div>
                  <div className="listing-card-badges">
                    <span className={`card-badge ${item.item_type === 'physical' ? 'card-badge-physical' : 'card-badge-virtual'}`}>
                      {item.item_type === 'physical' ? '实体' : '虚拟'}
                    </span>
                  </div>
                </div>
                <div className="listing-card-content" style={{ padding: '12px' }}>
                  <h4 className="listing-card-title" style={{ fontSize: '0.95rem', height: '2.8em', marginBottom: '6px' }}>
                    {item.title}
                  </h4>
                  <div className="listing-card-price-row" style={{ borderTop: 'none', paddingTop: 0 }}>
                    <span className="listing-card-price" style={{ fontSize: '1.1rem' }}>{item.price}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
