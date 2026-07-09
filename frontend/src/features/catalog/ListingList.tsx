import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Search, AlertCircle } from 'lucide-react';
import { getCategories, getListings } from '../../api/endpoints/listings';
import { Button, EmptyState } from '../../components/ui';
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

  const ITEMS_PER_PAGE = 6;

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
  const pageNumbers = Array.from({ length: totalPages }, (_, i) => i + 1);

  return (
    <div className="catalog-container fade-in">
      <div className="page-header">
        <h1>商品浏览</h1>
        <p>发现优质闲置二手好物</p>
      </div>

      <div className="catalog-layout">
        {/* 侧边栏筛选面板：小屏幕下会随 catalog-layout 自动堆叠 */}
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
              {totalPages > 1 && (
                <nav className="pagination" aria-label="商品分页">
                  <button
                    disabled={currentPage === 1}
                    onClick={() => updateQueryParam({ page: currentPage - 1 })}
                    className="page-btn"
                    aria-label="上一页"
                  >
                    上页
                  </button>

                  {pageNumbers.map((num) => (
                    <button
                      key={num}
                      onClick={() => updateQueryParam({ page: num })}
                      className={`page-btn ${currentPage === num ? 'active' : ''}`}
                      aria-label={`第 ${num} 页`}
                      aria-current={currentPage === num ? 'page' : undefined}
                    >
                      {num}
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
            </>
          )}
        </main>
      </div>
    </div>
  );
};
