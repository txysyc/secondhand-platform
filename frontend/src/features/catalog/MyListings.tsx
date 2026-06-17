import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getMyListings, publishListing, deactivateListing, reactivateListing, deleteListing } from '../../api/endpoints/listings';
import { useAuth } from '../../app/providers';
import { resolveMediaUrl } from '../../utils/media';
import type { Listing } from '../../types/listings';

export const MyListings: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);
  const [error, setError] = useState('');

  // 加载数据
  const loadListings = async () => {
    if (!user) return;
    setLoading(true);
    setError('');

    try {
      const data = await getMyListings();
      setListings(data.results);
    } catch (err: any) {
      setError('获取我的商品列表失败，请检查后端服务连接。');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadListings();
  }, [user]);

  const listingList = listings;

  const openListing = (item: Listing) => {
    if (item.status === 'draft') {
      navigate(`/me/listings/${item.id}/edit`);
      return;
    }
    navigate(`/listings/${item.id}`);
  };

  // 修改状态动作 (发布、下架、重新上架、删除)
  const handleAction = async (id: number, actionType: 'publish' | 'deactivate' | 'reactivate' | 'delete') => {
    if (actionType === 'delete' && !window.confirm('您确定要永久删除这件商品吗？该操作不可恢复。')) {
      return;
    }

    setActionLoadingId(id);
    try {
      // 调用真实后端
      if (actionType === 'publish') await publishListing(id);
      else if (actionType === 'deactivate') await deactivateListing(id);
      else if (actionType === 'reactivate') await reactivateListing(id);
      else if (actionType === 'delete') await deleteListing(id);

      alert('操作成功！');
      await loadListings();
    } catch (err: any) {
      alert(err.message || '操作失败，请重试');
    } finally {
      setActionLoadingId(null);
    }
  };

  if (!user) {
    return (
      <div className="placeholder-card error-card">
        <h2>⚠️ 您尚未登录</h2>
        <p>必须登录才能管理您的商品发布。</p>
      </div>
    );
  }

  // 获取封面展示图
  const getCoverImage = (item: Listing) => {
    if (item.images && item.images.length > 0) {
      const sorted = [...item.images].sort((a, b) => a.sort_order - b.sort_order);
      return resolveMediaUrl(sorted[0].image_url);
    }
    return null;
  };

  return (
    <div className="my-listings-container fade-in">
      <div className="my-listings-header">
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700 }}>我的商品管理</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>在此管理您发布、下架及草稿状态的所有商品</p>
        </div>
        <button onClick={() => navigate('/me/listings/new')} className="btn btn-primary">
          ➕ 发布新商品
        </button>
      </div>

      {error && (
        <div className="alert alert-error" style={{ marginBottom: '20px' }}>
          <span>⚠️ {error}</span>
        </div>
      )}

      {loading ? (
        <div className="loading-container">
          <div className="spinner"></div>
          <p>正在拉取商品列表...</p>
        </div>
      ) : listingList.length === 0 ? (
        <div className="placeholder-card">
          <h2>📦 还没有发布过商品</h2>
          <p>快去发布您的第一件二手闲置好物吧！</p>
          <button onClick={() => navigate('/me/listings/new')} className="btn btn-primary btn-sm">
            立即发布商品
          </button>
        </div>
      ) : (
        <div className="my-listings-list">
          {listingList.map((item) => {
            const cover = getCoverImage(item);
            const isActionBusy = actionLoadingId === item.id;

            return (
              <div
                key={item.id}
                className="my-listing-row"
                onClick={() => openListing(item)}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    openListing(item);
                  }
                }}
                title={item.status === 'draft' ? '编辑草稿' : '查看商品详情'}
                style={{ cursor: 'pointer' }}
              >
                {/* 封面缩略图 */}
                <div className="my-listing-thumb-wrapper">
                  {cover ? (
                    <img src={cover} alt={item.title} className="my-listing-thumb" loading="lazy" />
                  ) : (
                    <span className="my-listing-thumb-icon">
                      {item.category.id === 1 ? '💻' : item.category.id === 2 ? '📚' : item.category.id === 3 ? '👕' : '🏀'}
                    </span>
                  )}
                </div>

                {/* 商品简要信息 */}
                <div className="my-listing-info">
                  <div className="my-listing-title-row">
                    <span className={`badge badge-sm badge-${item.status}`}>
                      {item.status_display}
                    </span>
                    <h3 className="my-listing-title" title={item.title}>{item.title}</h3>
                  </div>
                  <div className="my-listing-meta">
                    <span className="my-listing-price">¥ {item.price}</span>
                    <span>分类: {item.category.name}</span>
                    <span>类别: {item.item_type_display}</span>
                    <span>更新: {new Date(item.updated_at).toLocaleDateString('zh-CN')}</span>
                  </div>
                </div>

                {/* 操作动作组合 */}
                <div className="my-listing-actions">
                  {item.status === 'draft' && (
                    <>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          navigate(`/me/listings/${item.id}/edit`);
                        }}
                        disabled={isActionBusy}
                        className="btn btn-outline btn-sm"
                      >
                        编辑
                      </button>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          handleAction(item.id, 'publish');
                        }}
                        disabled={isActionBusy}
                        className="btn btn-primary btn-sm"
                      >
                        {isActionBusy ? '...' : '发布'}
                      </button>
                    </>
                  )}

                  {item.status === 'active' && (
                    <>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          navigate(`/me/listings/${item.id}/edit`);
                        }}
                        disabled={isActionBusy}
                        className="btn btn-outline btn-sm"
                      >
                        编辑/多图
                      </button>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          handleAction(item.id, 'deactivate');
                        }}
                        disabled={isActionBusy}
                        className="btn btn-outline btn-sm"
                        style={{ color: '#dc2626', borderColor: '#fecaca' }}
                      >
                        {isActionBusy ? '...' : '下架'}
                      </button>
                    </>
                  )}

                  {item.status === 'withdrawn' && (
                    <>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          handleAction(item.id, 'reactivate');
                        }}
                        disabled={isActionBusy}
                        className="btn btn-primary btn-sm"
                      >
                        {isActionBusy ? '...' : '重新上架'}
                      </button>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          handleAction(item.id, 'delete');
                        }}
                        disabled={isActionBusy}
                        className="btn btn-outline btn-sm"
                        style={{ color: '#dc2626', borderColor: '#fecaca' }}
                      >
                        {isActionBusy ? '...' : '删除'}
                      </button>
                    </>
                  )}

                  {item.status === 'sold' && (
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 500, alignSelf: 'center', paddingRight: '12px' }}>
                      交易已完成
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
