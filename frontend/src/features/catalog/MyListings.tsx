import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, Package, AlertCircle } from 'lucide-react';
import {
  getCategories,
  getMyListings,
  publishListing,
  deactivateListing,
  reactivateListing,
  deleteListing,
} from '../../api/endpoints/listings';
import { useAuth } from '../../app/providers';
import { Button, EmptyState, Loading, ErrorState, Pagination } from '../../components/ui';
import { MyListingsFilterPanel } from './my/MyListingsFilterPanel';
import { MyListingsRows } from './my/MyListingsRows';
import type { Category, Listing } from '../../types/listings';

type ActionType = 'publish' | 'deactivate' | 'reactivate' | 'delete';

const MY_LISTING_PAGE_SIZE = 10;

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
  const rawStatus = searchParams.get('status') || 'all';
  // 已售出商品不进入我的商品管理，兼容旧链接中的 status=sold 参数。
  const status = rawStatus === 'sold' ? 'all' : rawStatus;
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

      <MyListingsFilterPanel
        categories={categories}
        searchText={searchText}
        status={status}
        category={category}
        itemType={itemType}
        sort={sort}
        tempMinPrice={tempMinPrice}
        tempMaxPrice={tempMaxPrice}
        onSearchTextChange={setSearchText}
        onTempMinPriceChange={setTempMinPrice}
        onTempMaxPriceChange={setTempMaxPrice}
        onFilterSubmit={handleFilterSubmit}
        onClearFilters={clearFilters}
        onUpdateQueryParam={updateQueryParam}
      />

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
        <>
          <MyListingsRows
            listings={listings}
            actionLoadingId={actionLoadingId}
            onOpenListing={openListing}
            onEditListing={(listingId) => navigate(`/me/listings/${listingId}/edit`)}
            onAction={handleAction}
          />

          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            onPageChange={(page) => updateQueryParam({ page })}
            ariaLabel="我的商品分页"
          />
        </>
      )}
    </div>
  );
};
