import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Package, AlertCircle, ImageIcon } from 'lucide-react';
import {
  getMyListings,
  publishListing,
  deactivateListing,
  reactivateListing,
  deleteListing,
} from '../../api/endpoints/listings';
import { useAuth } from '../../app/providers';
import { resolveMediaUrl } from '../../utils/media';
import { Button, Badge, EmptyState, Loading, ErrorState } from '../../components/ui';
import type { Listing, ListingStatus } from '../../types/listings';
import type { BadgeVariant } from '../../components/ui';

type ActionType = 'publish' | 'deactivate' | 'reactivate' | 'delete';

const STATUS_VARIANT_MAP: Record<ListingStatus, BadgeVariant> = {
  draft: 'draft',
  active: 'active',
  reserved: 'warning',
  sold: 'sold',
  withdrawn: 'inactive',
};

const getErrorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return fallback;
};

export const MyListings: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 加载数据
  const loadListings = async () => {
    if (!user) return;
    setLoading(true);
    setError('');
    setActionMessage(null);

    try {
      const data = await getMyListings();
      setListings(data.results);
    } catch {
      setError('获取我的商品列表失败，请检查后端服务连接。');
    } finally {
      setLoading(false);
    }
  };

  /* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
  useEffect(() => {
    loadListings();
  }, [user]);
  /* eslint-enable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */

  const openListing = (item: Listing) => {
    if (item.status === 'draft') {
      navigate(`/me/listings/${item.id}/edit`);
      return;
    }
    navigate(`/listings/${item.id}`);
  };

  // 修改状态动作 (发布、下架、重新上架、删除)
  const handleAction = async (id: number, actionType: ActionType) => {
    if (actionType === 'delete' && !window.confirm('您确定要永久删除这件商品吗？该操作不可恢复。')) {
      return;
    }

    setActionLoadingId(id);
    setActionMessage(null);
    try {
      if (actionType === 'publish') await publishListing(id);
      else if (actionType === 'deactivate') await deactivateListing(id);
      else if (actionType === 'reactivate') await reactivateListing(id);
      else if (actionType === 'delete') await deleteListing(id);

      setActionMessage({ type: 'success', text: '操作成功' });
      await loadListings();
    } catch (err) {
      setActionMessage({ type: 'error', text: getErrorMessage(err, '操作失败，请重试') });
    } finally {
      setActionLoadingId(null);
    }
  };

  if (!user) {
    return (
      <ErrorState
        title="您尚未登录"
        message="必须登录才能管理您的商品发布。"
        onBack={() => navigate('/login')}
      />
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
      <div className="page-header my-listings-page-header">
        <div>
          <h1>我的商品管理</h1>
          <p>在此管理您发布、下架及草稿状态的所有商品</p>
        </div>
        <Button variant="primary" onClick={() => navigate('/me/listings/new')}>
          <Plus size={18} />
          发布新商品
        </Button>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {actionMessage && (
        <div className={`alert alert-${actionMessage.type === 'success' ? 'success' : 'error'}`} role="alert">
          {actionMessage.type === 'error' ? <AlertCircle size={18} /> : <Package size={18} />}
          <span>{actionMessage.text}</span>
        </div>
      )}

      {loading ? (
        <Loading text="正在拉取商品列表..." />
      ) : listings.length === 0 ? (
        <EmptyState
          icon={<Package size={48} />}
          title="还没有发布过商品"
          description="快去发布您的第一件二手闲置好物吧！"
          action={{
            label: '立即发布商品',
            onClick: () => navigate('/me/listings/new'),
            variant: 'primary',
          }}
        />
      ) : (
        <div className="my-listings-list">
          {listings.map((item) => {
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
              >
                {/* 封面缩略图 */}
                <div className="my-listing-thumb-wrapper">
                  {cover ? (
                    <img src={cover} alt={item.title} className="my-listing-thumb" loading="lazy" />
                  ) : (
                    <ImageIcon className="my-listing-thumb-icon" size={36} strokeWidth={1.5} />
                  )}
                </div>

                {/* 商品简要信息 */}
                <div className="my-listing-info">
                  <div className="my-listing-title-row">
                    <Badge variant={STATUS_VARIANT_MAP[item.status]} size="sm">
                      {item.status_display}
                    </Badge>
                    <h3 className="my-listing-title" title={item.title}>
                      {item.title}
                    </h3>
                  </div>
                  <div className="my-listing-meta">
                    <span className="my-listing-price">¥ {item.price}</span>
                    <span>分类: {item.category.name}</span>
                    <span>类别: {item.item_type_display}</span>
                    <span>更新: {new Date(item.updated_at).toLocaleDateString('zh-CN')}</span>
                  </div>
                </div>

                {/* 操作动作组合 */}
                <div className="my-listing-actions" onClick={(event) => event.stopPropagation()} role="group">
                  {item.status === 'draft' && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={isActionBusy}
                        onClick={() => navigate(`/me/listings/${item.id}/edit`)}
                      >
                        编辑
                      </Button>
                      <Button
                        variant="primary"
                        size="sm"
                        disabled={isActionBusy}
                        loading={isActionBusy}
                        onClick={() => handleAction(item.id, 'publish')}
                      >
                        发布
                      </Button>
                    </>
                  )}

                  {item.status === 'active' && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={isActionBusy}
                        onClick={() => navigate(`/me/listings/${item.id}/edit`)}
                      >
                        编辑/多图
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        disabled={isActionBusy}
                        loading={isActionBusy}
                        onClick={() => handleAction(item.id, 'deactivate')}
                      >
                        下架
                      </Button>
                    </>
                  )}

                  {item.status === 'withdrawn' && (
                    <>
                      <Button
                        variant="primary"
                        size="sm"
                        disabled={isActionBusy}
                        loading={isActionBusy}
                        onClick={() => handleAction(item.id, 'reactivate')}
                      >
                        重新上架
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        disabled={isActionBusy}
                        loading={isActionBusy}
                        onClick={() => handleAction(item.id, 'delete')}
                      >
                        删除
                      </Button>
                    </>
                  )}

                  {item.status === 'sold' && (
                    <span className="my-listing-status-note">交易已完成</span>
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
