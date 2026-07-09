import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Search, AlertCircle, ImageIcon } from 'lucide-react';
import { getCategories, getListings } from '../../api/endpoints/listings';
import { resolveAvatarUrl, resolveMediaUrl } from '../../utils/media';
import { Button, Input, Select, EmptyState } from '../../components/ui';
import type { Category, Listing } from '../../types/listings';

const CATEGORIES_CACHE_KEY = 'secondhand:categories';

const SORT_OPTIONS = [
  { value: 'newest', label: '最新发布' },
  { value: 'oldest', label: '时间最久' },
  { value: 'price_asc', label: '价格从低到高' },
  { value: 'price_desc', label: '价格从高到低' },
];

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

  // 获取封面展示图
  const getCoverImage = (item: Listing) => {
    if (item.images && item.images.length > 0) {
      // 优先显示排在首位的图片
      const sorted = [...item.images].sort((a, b) => a.sort_order - b.sort_order);
      return resolveMediaUrl(sorted[0].image_url);
    }
    return null;
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
        <aside className="filter-panel">
          {/* 搜索 */}
          <div className="filter-section">
            <h3 className="filter-section-title">搜索</h3>
            <form onSubmit={handleSearchSubmit} className="filter-search-form">
              <Input
                id="search"
                icon={<Search size={18} />}
                placeholder="搜索商品..."
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
              />
              <Button type="submit" variant="primary" size="sm" aria-label="搜索">
                <Search size={16} />
              </Button>
            </form>
          </div>

          {/* 分类 */}
          <div className="filter-section">
            <h3 className="filter-section-title">商品分类</h3>
            <ul className="category-list">
              <li>
                <button
                  onClick={() => updateQueryParam({ category: 'all' })}
                  className={`category-item-btn ${currentCategory === 'all' ? 'active' : ''}`}
                >
                  全部商品
                </button>
              </li>
              {categories.map((cat) => (
                <li key={cat.id}>
                  <button
                    onClick={() => updateQueryParam({ category: cat.id })}
                    className={`category-item-btn ${currentCategory === String(cat.id) ? 'active' : ''}`}
                  >
                    {cat.name}
                  </button>
                </li>
              ))}
            </ul>
          </div>

          {/* 商品类型 */}
          <div className="filter-section">
            <h3 className="filter-section-title">交付类别</h3>
            <div className="segmented-control">
              <button
                onClick={() => updateQueryParam({ item_type: 'all' })}
                className={`segment-btn ${itemType === 'all' ? 'active' : ''}`}
              >
                全部
              </button>
              <button
                onClick={() => updateQueryParam({ item_type: 'physical' })}
                className={`segment-btn ${itemType === 'physical' ? 'active' : ''}`}
              >
                实体
              </button>
              <button
                onClick={() => updateQueryParam({ item_type: 'virtual' })}
                className={`segment-btn ${itemType === 'virtual' ? 'active' : ''}`}
              >
                虚拟
              </button>
            </div>
          </div>

          {/* 价格区间 */}
          <div className="filter-section">
            <h3 className="filter-section-title">价格区间 (元)</h3>
            <form onSubmit={handlePriceSubmit}>
              <div className="price-range-inputs">
                <div className="price-input-wrapper">
                  <span className="price-currency">¥</span>
                  <input
                    type="number"
                    className="form-control price-control"
                    placeholder="最低"
                    value={tempMinPrice}
                    onChange={(e) => setTempMinPrice(e.target.value)}
                  />
                </div>
                <span className="price-range-divider">-</span>
                <div className="price-input-wrapper">
                  <span className="price-currency">¥</span>
                  <input
                    type="number"
                    className="form-control price-control"
                    placeholder="最高"
                    value={tempMaxPrice}
                    onChange={(e) => setTempMaxPrice(e.target.value)}
                  />
                </div>
              </div>
              <Button type="submit" variant="outline" size="sm" fullWidth className="price-apply-btn">
                应用区间
              </Button>
            </form>
          </div>

          {/* 发布时间区间 */}
          <div className="filter-section">
            <h3 className="filter-section-title">发布时间</h3>
            <form onSubmit={handlePublishedSubmit}>
              <div className="published-range-inputs">
                <label className="filter-field-label" htmlFor="published_after">
                  起始时间
                </label>
                <input
                  id="published_after"
                  type="datetime-local"
                  className="form-control"
                  value={tempPublishedAfter}
                  onChange={(e) => setTempPublishedAfter(e.target.value)}
                />
                <label className="filter-field-label" htmlFor="published_before">
                  截止时间
                </label>
                <input
                  id="published_before"
                  type="datetime-local"
                  className="form-control"
                  value={tempPublishedBefore}
                  onChange={(e) => setTempPublishedBefore(e.target.value)}
                />
              </div>
              <Button type="submit" variant="outline" size="sm" fullWidth className="published-apply-btn">
                应用时间
              </Button>
            </form>
          </div>

          {/* 排序 */}
          <div className="filter-section">
            <h3 className="filter-section-title">排序方式</h3>
            <div className="filter-sort-select">
              <Select
                id="sort"
                options={SORT_OPTIONS}
                value={currentSort}
                onChange={(e) => updateQueryParam({ sort: e.target.value })}
              />
            </div>
          </div>
        </aside>

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
              <div className="listings-grid">
                {listings.map((item) => {
                  const cover = getCoverImage(item);
                  return (
                    <article
                      key={item.id}
                      className="listing-card"
                      onClick={() => navigate(`/listings/${item.id}`)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          navigate(`/listings/${item.id}`);
                        }
                      }}
                      aria-label={`查看商品：${item.title}`}
                    >
                      <div className="listing-card-image-wrapper">
                        {cover ? (
                          <img src={cover} alt={item.title} className="listing-card-image" loading="lazy" />
                        ) : (
                          <div className="listing-card-placeholder">
                            <ImageIcon className="listing-card-placeholder-icon" size={48} strokeWidth={1.5} />
                            <span>{item.category.name}</span>
                          </div>
                        )}

                        <div className="listing-card-badges">
                          <span
                            className={`card-badge ${
                              item.item_type === 'physical' ? 'card-badge-physical' : 'card-badge-virtual'
                            }`}
                          >
                            {item.item_type_display}
                          </span>
                        </div>

                        {item.status !== 'active' && (
                          <span className="card-badge-status">{item.status_display}</span>
                        )}
                      </div>

                      <div className="listing-card-content">
                        <span className="listing-card-category">{item.category.name}</span>
                        <h2 className="listing-card-title">{item.title}</h2>

                        <div className="listing-card-price-row">
                          <span className="listing-card-price">{item.price}</span>
                          {item.item_type === 'physical' && item.condition_display && (
                            <span className="listing-card-condition">{item.condition_display}</span>
                          )}
                        </div>
                      </div>

                      <div className="listing-card-footer">
                        <div className="listing-card-owner">
                          <img
                            src={resolveAvatarUrl(item.owner.profile?.avatar_url, item.owner.username)}
                            alt={item.owner.username}
                            className="listing-card-avatar"
                          />
                          <span>{item.owner.profile?.nickname || item.owner.username}</span>
                        </div>
                        <span>
                          {new Date(item.created_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })}
                        </span>
                      </div>
                    </article>
                  );
                })}
              </div>

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
