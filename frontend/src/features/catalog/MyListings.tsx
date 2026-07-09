import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, Package, AlertCircle, ImageIcon, Search } from 'lucide-react';
import {
  getCategories,
  getMyListings,
  publishListing,
  deactivateListing,
  reactivateListing,
  deleteListing,
} from '../../api/endpoints/listings';
import { useAuth } from '../../app/providers';
import { resolveMediaUrl } from '../../utils/media';
import { Button, Badge, EmptyState, Loading, ErrorState, Input, Select } from '../../components/ui';
import type { Category, Listing, ListingStatus } from '../../types/listings';
import type { BadgeVariant } from '../../components/ui';

type ActionType = 'publish' | 'deactivate' | 'reactivate' | 'delete';

const MY_LISTING_PAGE_SIZE = 10;

const STATUS_VARIANT_MAP: Record<ListingStatus, BadgeVariant> = {
  draft: 'draft',
  active: 'active',
  reserved: 'warning',
  sold: 'sold',
  withdrawn: 'inactive',
};

const STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'active', label: '在售' },
  { value: 'reserved', label: '交易占用' },
  { value: 'sold', label: '已售出' },
  { value: 'withdrawn', label: '已下架' },
];

const ITEM_TYPE_OPTIONS = [
  { value: 'all', label: '全部类型' },
  { value: 'physical', label: '实体商品' },
  { value: 'virtual', label: '虚拟商品' },
];

const SORT_OPTIONS = [
  { value: 'updated_desc', label: '最近更新' },
  { value: 'updated_asc', label: '最早更新' },
  { value: 'published_desc', label: '最近发布' },
  { value: 'published_asc', label: '最早发布' },
  { value: 'price_asc', label: '价格从低到高' },
  { value: 'price_desc', label: '价格从高到低' },
];

const getErrorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return fallback;
};

export const MyListings: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();

  const [categories, setCategories] = useState<Category[]>([]);
  const [listings, setListings] = useState<Listing[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // URL 参数是我的商品筛选和分页的唯一来源。
  const query = searchParams.get('q') || '';
  const status = searchParams.get('status') || 'all';
  const category = searchParams.get('category') || 'all';
  const itemType = searchParams.get('item_type') || 'all';
  const minPrice = searchParams.get('min_price') || '';
  const maxPrice = searchParams.get('max_price') || '';
  const sort = searchParams.get('sort') || 'updated_desc';
  const currentPage = parseInt(searchParams.get('page') || '1', 10);

  const [searchText, setSearchText] = useState(query);
  const [tempMinPrice, setTempMinPrice] = useState(minPrice);
  const [tempMaxPrice, setTempMaxPrice] = useState(maxPrice);

  const buildApiParams = () => ({
    q: query || undefined,
    status: status !== 'all' ? status : undefined,
    category: category !== 'all' ? category : undefined,
    item_type: itemType !== 'all' ? itemType : undefined,
    min_price: minPrice || undefined,
    max_price: maxPrice || undefined,
    sort,
    page: currentPage,
    page_size: MY_LISTING_PAGE_SIZE,
  });

  // 加载分类选项，供当前用户商品筛选使用。
  useEffect(() => {
    let cancel = false;
    getCategories()
      .then((items) => {
        if (!cancel) setCategories(items);
      })
      .catch((err) => console.error('加载分类失败', err));
    return () => {
      cancel = true;
    };
  }, []);

  // 加载当前筛选条件下的商品列表。
  const loadListings = async () => {
    if (!user) return null;
    setLoading(true);
    setError('');

    try {
      const data = await getMyListings(buildApiParams());
      setListings(data.results);
      setTotalCount(data.count);
      return data;
    } catch {
      setError('获取我的商品列表失败，请检查后端服务连接。');
      return null;
    } finally {
      setLoading(false);
    }
  };

  /* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
  useEffect(() => {
    loadListings();
  }, [user, query, status, category, itemType, minPrice, maxPrice, sort, currentPage]);
  /* eslint-enable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    setSearchText(query);
    setTempMinPrice(minPrice);
    setTempMaxPrice(maxPrice);
  }, [query, minPrice, maxPrice]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const totalPages = Math.ceil(totalCount / MY_LISTING_PAGE_SIZE);
  const pageNumbers = Array.from({ length: totalPages }, (_, index) => index + 1);

  const updateQueryParam = (newParams: Record<string, string | number | null>) => {
    const nextParams = new URLSearchParams(searchParams);
    if (!('page' in newParams)) {
      nextParams.set('page', '1');
    }
    Object.entries(newParams).forEach(([key, value]) => {
      if (value === null || value === '' || value === 'all') {
        nextParams.delete(key);
      } else {
        nextParams.set(key, String(value));
      }
    });
    setSearchParams(nextParams);
  };

  const handleFilterSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    updateQueryParam({
      q: searchText,
      min_price: tempMinPrice,
      max_price: tempMaxPrice,
    });
  };

  const clearFilters = () => {
    setSearchParams(new URLSearchParams());
  };

  const openListing = (item: Listing) => {
    if (item.status === 'draft') {
      navigate(`/me/listings/${item.id}/edit`);
      return;
    }
    navigate(`/listings/${item.id}`);
  };

  // 修改状态动作后重新拉取当前筛选；当前页被删空时回退上一页。
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
      const data = await loadListings();
      if (data && data.results.length === 0 && currentPage > 1) {
        updateQueryParam({ page: currentPage - 1 });
      }
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

  // 获取封面展示图。
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

      <form className="my-listing-filter-panel" onSubmit={handleFilterSubmit}>
        <Input
          id="my_listing_search"
          icon={<Search size={16} />}
          label="搜索商品"
          placeholder="标题或描述"
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
        />
        <Select
          id="my_listing_status"
          label="商品状态"
          options={STATUS_OPTIONS}
          value={status}
          onChange={(event) => updateQueryParam({ status: event.target.value })}
        />
        <Select
          id="my_listing_category"
          label="分类"
          options={[{ value: 'all', label: '全部分类' }, ...categories.map((item) => ({ value: item.id, label: item.name }))]}
          value={category}
          onChange={(event) => updateQueryParam({ category: event.target.value })}
        />
        <Select
          id="my_listing_item_type"
          label="类型"
          options={ITEM_TYPE_OPTIONS}
          value={itemType}
          onChange={(event) => updateQueryParam({ item_type: event.target.value })}
        />
        <Select
          id="my_listing_sort"
          label="排序"
          options={SORT_OPTIONS}
          value={sort}
          onChange={(event) => updateQueryParam({ sort: event.target.value })}
        />
        <Input
          id="my_listing_min_price"
          label="最低价格"
          type="number"
          value={tempMinPrice}
          onChange={(event) => setTempMinPrice(event.target.value)}
        />
        <Input
          id="my_listing_max_price"
          label="最高价格"
          type="number"
          value={tempMaxPrice}
          onChange={(event) => setTempMaxPrice(event.target.value)}
        />
        <div className="filter-actions-row">
          <Button type="submit" size="sm">
            应用筛选
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={clearFilters}>
            清空
          </Button>
        </div>
      </form>

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
          title="没有符合条件的商品"
          description="调整筛选条件，或发布新的二手闲置商品。"
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
                <div className="my-listing-thumb-wrapper">
                  {cover ? (
                    <img src={cover} alt={item.title} className="my-listing-thumb" loading="lazy" />
                  ) : (
                    <ImageIcon className="my-listing-thumb-icon" size={36} strokeWidth={1.5} />
                  )}
                </div>

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

      {!loading && !error && totalPages > 1 && (
        <nav className="pagination" aria-label="我的商品分页">
          <button
            disabled={currentPage === 1}
            onClick={() => updateQueryParam({ page: currentPage - 1 })}
            className="page-btn"
            aria-label="上一页"
          >
            上页
          </button>
          {pageNumbers.map((page) => (
            <button
              key={page}
              onClick={() => updateQueryParam({ page })}
              className={`page-btn ${currentPage === page ? 'active' : ''}`}
              aria-label={`第 ${page} 页`}
              aria-current={currentPage === page ? 'page' : undefined}
            >
              {page}
            </button>
          ))}
          <button
            disabled={currentPage === totalPages}
            onClick={() => updateQueryParam({ page: currentPage + 1 })}
            className="page-btn"
            aria-label="下一页"
          >
            下页
          </button>
        </nav>
      )}
    </div>
  );
};
