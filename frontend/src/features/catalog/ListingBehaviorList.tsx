import React, { useEffect, useState } from 'react';
import { Clock, Heart, ImageIcon, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import {
  getBrowseHistory,
  getMyFavorites,
  unfavoriteListing,
} from '../../api/endpoints/listings';
import { Button, EmptyState, Loading } from '../../components/ui';
import type {
  BrowseHistoryItem,
  FavoriteItem,
  Listing,
  PaginatedResponse,
} from '../../types/listings';
import { resolveMediaUrl } from '../../utils/media';

type BehaviorMode = 'favorites' | 'history';
type BehaviorItem = FavoriteItem | BrowseHistoryItem;

interface ListingBehaviorListProps {
  mode: BehaviorMode;
}

const PAGE_SIZE = 8;

const getErrorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return fallback;
};

const getCoverImage = (listing: Listing) => {
  // 优先使用商品排序最靠前的图片作为列表封面。
  if (listing.images && listing.images.length > 0) {
    const sortedImages = [...listing.images].sort((a, b) => a.sort_order - b.sort_order);
    return resolveMediaUrl(sortedImages[0].image_url);
  }
  return null;
};

const getItemTime = (item: BehaviorItem, mode: BehaviorMode) => {
  // 两类行为列表的时间字段不同，统一在展示层转换。
  return mode === 'favorites'
    ? (item as FavoriteItem).created_at
    : (item as BrowseHistoryItem).viewed_at;
};

export const ListingBehaviorList: React.FC<ListingBehaviorListProps> = ({ mode }) => {
  const navigate = useNavigate();
  const [items, setItems] = useState<BehaviorItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [actionListingId, setActionListingId] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  const isFavorites = mode === 'favorites';
  const title = isFavorites ? '我的收藏' : '浏览历史';
  const subtitle = isFavorites ? '集中查看您关注的闲置商品' : '回到最近看过的商品';
  const emptyTitle = isFavorites ? '还没有收藏商品' : '还没有浏览记录';
  const emptyDescription = isFavorites
    ? '在商品详情页点击心形按钮，即可把感兴趣的商品加入收藏。'
    : '打开商品详情后，系统会自动记录最近浏览过的商品。';

  const fetchItems = async (page = currentPage) => {
    setLoading(true);
    setErrorMsg('');
    try {
      const response: PaginatedResponse<BehaviorItem> = isFavorites
        ? await getMyFavorites({ page, page_size: PAGE_SIZE })
        : await getBrowseHistory({ page, page_size: PAGE_SIZE });
      setItems(response.results);
      setTotalCount(response.count);
    } catch (err) {
      setErrorMsg(getErrorMessage(err, `获取${title}失败，请稍后重试`));
    } finally {
      setLoading(false);
    }
  };

  /* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
  useEffect(() => {
    fetchItems(currentPage);
  }, [currentPage, mode]);
  /* eslint-enable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */

  const handleRemoveFavorite = async (listingId: number) => {
    // 取消收藏后直接移除当前列表项，避免用户等待整页刷新。
    setActionListingId(listingId);
    setErrorMsg('');
    try {
      await unfavoriteListing(listingId);
      setItems((prev) => prev.filter((item) => item.listing.id !== listingId));
      setTotalCount((prev) => Math.max(prev - 1, 0));
    } catch (err) {
      setErrorMsg(getErrorMessage(err, '取消收藏失败，请稍后重试'));
    } finally {
      setActionListingId(null);
    }
  };

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);
  const pageNumbers = Array.from({ length: totalPages }, (_, index) => index + 1);

  if (loading) {
    return <Loading text={`正在加载${title}...`} />;
  }

  return (
    <div className="behavior-page fade-in">
      <div className="page-header behavior-page-header">
        <div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        <Button variant="outline" onClick={() => navigate('/')}>
          继续浏览商品
        </Button>
      </div>

      {errorMsg && (
        <div className="alert alert-error behavior-alert" role="alert">
          <span>{errorMsg}</span>
          <Button variant="outline" size="sm" onClick={() => fetchItems(currentPage)}>
            重试
          </Button>
        </div>
      )}

      {items.length === 0 ? (
        <EmptyState
          icon={isFavorites ? <Heart size={48} /> : <Clock size={48} />}
          title={emptyTitle}
          description={emptyDescription}
          action={{
            label: '浏览商品',
            onClick: () => navigate('/'),
            variant: 'primary',
          }}
        />
      ) : (
        <>
          <div className="behavior-grid">
            {items.map((item) => {
              const cover = getCoverImage(item.listing);
              const actionTime = getItemTime(item, mode);
              return (
                <article key={item.id} className="behavior-card">
                  <button
                    type="button"
                    className="behavior-card-main"
                    onClick={() => navigate(`/listings/${item.listing.id}`)}
                  >
                    <div className="behavior-card-image-wrapper">
                      {cover ? (
                        <img src={cover} alt={item.listing.title} className="behavior-card-image" />
                      ) : (
                        <div className="behavior-card-placeholder">
                          <ImageIcon size={34} />
                          <span>{item.listing.category.name}</span>
                        </div>
                      )}
                    </div>
                    <div className="behavior-card-content">
                      <span className="behavior-card-category">{item.listing.category.name}</span>
                      <h2>{item.listing.title}</h2>
                      <div className="behavior-card-meta">
                        <span className="behavior-card-price">¥{item.listing.price}</span>
                        <span>{new Date(actionTime).toLocaleString('zh-CN')}</span>
                      </div>
                    </div>
                  </button>

                  {isFavorites && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="behavior-remove-btn"
                      loading={actionListingId === item.listing.id}
                      onClick={() => handleRemoveFavorite(item.listing.id)}
                    >
                      <Trash2 size={16} />
                      取消收藏
                    </Button>
                  )}
                </article>
              );
            })}
          </div>

          {totalPages > 1 && (
            <nav className="pagination" aria-label={`${title}分页`}>
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((prev) => Math.max(prev - 1, 1))}
                className="page-btn"
                aria-label="上一页"
              >
                上页
              </button>
              {pageNumbers.map((pageNumber) => (
                <button
                  key={pageNumber}
                  onClick={() => setCurrentPage(pageNumber)}
                  className={`page-btn ${currentPage === pageNumber ? 'active' : ''}`}
                  aria-label={`第 ${pageNumber} 页`}
                  aria-current={currentPage === pageNumber ? 'page' : undefined}
                >
                  {pageNumber}
                </button>
              ))}
              <button
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage((prev) => Math.min(prev + 1, totalPages))}
                className="page-btn"
                aria-label="下一页"
              >
                下页
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
};

export const MyFavorites: React.FC = () => <ListingBehaviorList mode="favorites" />;

export const BrowseHistory: React.FC = () => <ListingBehaviorList mode="history" />;
