import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Search, AlertCircle, SlidersHorizontal } from 'lucide-react';
import { getCategories, getListings } from '../../api/endpoints/listings';
import { Button, EmptyState, PageHeader, Pagination } from '../../components/ui';
import { ListingGrid } from './list/ListingGrid';
import { ListingListFilterPanel } from './list/ListingListFilterPanel';
import type { Category, Listing } from '../../types/listings';

const CATEGORIES_CACHE_KEY = 'secondhand:categories';

const getErrorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return fallback;
};

export const ListingList: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // 状态绑定
  const [categories, setCategories] = useState<Category[]>([]);
  const [listings, setListings] = useState<Listing[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);

  // 解析 URL 参数用于筛选
  const query = searchParams.get('q') || '';
  const currentCategory = searchParams.get('category') || 'all';
  const itemType = searchParams.get('item_type') || 'all';
  const minPrice = searchParams.get('min_price') || '';
  const maxPrice = searchParams.get('max_price') || '';
  const publishedAfter = searchParams.get('published_after') || '';
  const publishedBefore = searchParams.get('published_before') || '';
  const currentSort = searchParams.get('sort') || 'newest';
  const currentPage = parseInt(searchParams.get('page') || '1', 10);

  // 临时输入的搜索文本、价格和发布时间区间
  const [searchText, setSearchText] = useState(query);
  const [tempMinPrice, setTempMinPrice] = useState(minPrice);
  const [tempMaxPrice, setTempMaxPrice] = useState(maxPrice);
  const [tempPublishedAfter, setTempPublishedAfter] = useState(publishedAfter);
  const [tempPublishedBefore, setTempPublishedBefore] = useState(publishedBefore);

  // 桌面端四列网格使用 12 条数据，减少分页频率并提高浏览效率。
  const ITEMS_PER_PAGE = 12;

  const readCachedCategories = () => {
    try {
      const cached = localStorage.getItem(CATEGORIES_CACHE_KEY);
      return cached ? (JSON.parse(cached) as Category[]) : [];
    } catch {
      return [];
    }
  };

  const writeCachedCategories = (items: Category[]) => {
    try {
      localStorage.setItem(CATEGORIES_CACHE_KEY, JSON.stringify(items));
    } catch {
      // 分类缓存只是体验优化，写入失败不影响正常浏览。
    }
  };

  const renderListingSkeletons = () => (
    <div className="listings-grid">
      {Array.from({ length: ITEMS_PER_PAGE }).map((_, index) => (
        <article key={index} className="listing-card listing-card-skeleton" aria-hidden="true">
          <div className="listing-card-image-wrapper skeleton-block" />
          <div className="listing-card-content">
            <div className="skeleton-line skeleton-line-short" />
            <div className="skeleton-line skeleton-line-title" />
            <div className="skeleton-line skeleton-line-title skeleton-line-narrow" />
            <div className="listing-card-price-row">
              <div className="skeleton-line skeleton-line-price" />
              <div className="skeleton-line skeleton-line-chip" />
            </div>
          </div>
          <div className="listing-card-footer">
            <div className="skeleton-line skeleton-line-owner" />
            <div className="skeleton-line skeleton-line-date" />
          </div>
        </article>
      ))}
    </div>
  );

  // 同步 URL 参数变化至临时搜索文本
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    setSearchText(query);
    setTempMinPrice(minPrice);
    setTempMaxPrice(maxPrice);
    setTempPublishedAfter(publishedAfter);
    setTempPublishedBefore(publishedBefore);
  }, [query, minPrice, maxPrice, publishedAfter, publishedBefore]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // 加载分类列表
  useEffect(() => {
    const fetchCategories = async () => {
      const cachedCategories = readCachedCategories();
      if (cachedCategories.length > 0) {
        setCategories(cachedCategories);
      }

      try {
        const data = await getCategories();
        setCategories(data);
        writeCachedCategories(data);
      } catch (err) {
        console.error('加载分类失败', err);
      }
    };
    fetchCategories();
  }, []);

  // 加载商品列表
  const fetchListings = async () => {
    setLoading(true);
    setErrorMsg('');

    const apiParams = {
      q: query || undefined,
      category: currentCategory !== 'all' ? currentCategory : undefined,
      item_type: itemType !== 'all' ? itemType : undefined,
      min_price: minPrice || undefined,
      max_price: maxPrice || undefined,
      published_after: publishedAfter || undefined,
      published_before: publishedBefore || undefined,
      sort: currentSort,
      page: currentPage,
      page_size: ITEMS_PER_PAGE,
    };

    try {
      const response = await getListings(apiParams);
      setListings(response.results);
      setTotalCount(response.count);
    } catch (err) {
      console.error('获取商品列表失败', err);
      setErrorMsg(getErrorMessage(err, '获取商品列表失败，请稍后重试'));
    } finally {
      setLoading(false);
    }
  };

  /* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
  useEffect(() => {
    fetchListings();
  }, [
    query,
    currentCategory,
    itemType,
    minPrice,
    maxPrice,
    publishedAfter,
    publishedBefore,
    currentSort,
    currentPage,
  ]);
  /* eslint-enable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */

  // 修改单个 URL 查询参数
  const updateQueryParam = (newParams: Record<string, string | number | null>) => {
    const nextParams = new URLSearchParams(searchParams);

    // 如果修改了检索参数，默认重置页码回第 1 页
    if (!('page' in newParams)) {
      nextParams.set('page', '1');
    }

    Object.entries(newParams).forEach(([key, val]) => {
      if (val === null || val === 'all' || val === '') {
        nextParams.delete(key);
      } else {
        nextParams.set(key, String(val));
      }
    });

    setSearchParams(nextParams);
  };

  // 提交搜索框
  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateQueryParam({ q: searchText });
  };

  // 提交价格过滤
  const handlePriceSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateQueryParam({
      min_price: tempMinPrice,
      max_price: tempMaxPrice,
    });
  };

  // 提交发布时间过滤
  const handlePublishedSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateQueryParam({
      published_after: tempPublishedAfter,
      published_before: tempPublishedBefore,
    });
  };

  // 渲染分页器
  const totalPages = Math.ceil(totalCount / ITEMS_PER_PAGE);

  return (
    <div className="catalog-container fade-in">
      <PageHeader
        eyebrow="闲置市集"
        title="发现值得再次使用的好物"
        description="按类别、价格和发布时间快速筛选，找到更适合你的闲置商品。"
        actions={
          <span className="catalog-result-count">
            <strong>{loading ? '—' : totalCount}</strong>
            件商品
          </span>
        }
      />

      {/* 小屏幕通过按钮展开筛选，桌面端筛选栏始终可见。 */}
      <div className="catalog-mobile-toolbar">
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-expanded={filtersOpen}
          onClick={() => setFiltersOpen((current) => !current)}
        >
          <SlidersHorizontal size={16} />
          {filtersOpen ? '收起筛选' : '筛选与排序'}
        </Button>
        <span>共 {totalCount} 件</span>
      </div>

      <div className="catalog-layout">
        <div className={`catalog-filter-shell ${filtersOpen ? 'is-open' : ''}`}>
          <ListingListFilterPanel
            categories={categories}
            searchText={searchText}
            currentCategory={currentCategory}
            itemType={itemType}
            tempMinPrice={tempMinPrice}
            tempMaxPrice={tempMaxPrice}
            tempPublishedAfter={tempPublishedAfter}
            tempPublishedBefore={tempPublishedBefore}
            currentSort={currentSort}
            onSearchTextChange={setSearchText}
            onTempMinPriceChange={setTempMinPrice}
            onTempMaxPriceChange={setTempMaxPrice}
            onTempPublishedAfterChange={setTempPublishedAfter}
            onTempPublishedBeforeChange={setTempPublishedBefore}
            onSearchSubmit={handleSearchSubmit}
            onPriceSubmit={handlePriceSubmit}
            onPublishedSubmit={handlePublishedSubmit}
            onUpdateQueryParam={updateQueryParam}
          />
        </div>

        {/* 右侧商品网格 */}
        <main className="catalog-main">
          {errorMsg && (
            <div className="alert alert-error" role="alert">
              <AlertCircle size={18} />
              <span>{errorMsg}</span>
              <Button variant="outline" size="sm" onClick={fetchListings}>
                重试连接
              </Button>
            </div>
          )}

          {loading ? (
            renderListingSkeletons()
          ) : listings.length === 0 ? (
            <EmptyState
              icon={<Search size={48} />}
              title="未搜索到相关商品"
              description="尝试清除过滤条件或换个搜索关键词试试吧。"
              action={{
                label: '重置所有筛选',
                onClick: () => setSearchParams(new URLSearchParams()),
                variant: 'primary',
              }}
            />
          ) : (
            <>
              <ListingGrid listings={listings} onOpenListing={(listingId) => navigate(`/listings/${listingId}`)} />

              {/* 分页 */}
              <Pagination
                currentPage={currentPage}
                totalPages={totalPages}
                onPageChange={(page) => updateQueryParam({ page })}
                ariaLabel="商品分页"
              />
            </>
          )}
        </main>
      </div>
    </div>
  );
};
