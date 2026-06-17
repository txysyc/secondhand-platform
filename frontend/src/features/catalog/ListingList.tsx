import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { getCategories, getListings } from '../../api/endpoints/listings';
import { resolveAvatarUrl, resolveMediaUrl } from '../../utils/media';
import type { Category, Listing } from '../../types/listings';

const CATEGORIES_CACHE_KEY = 'secondhand:categories';

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
  const currentSort = searchParams.get('sort') || 'newest';
  const currentPage = parseInt(searchParams.get('page') || '1', 10);

  // 临时输入的搜索文本和价格
  const [searchText, setSearchText] = useState(query);
  const [tempMinPrice, setTempMinPrice] = useState(minPrice);
  const [tempMaxPrice, setTempMaxPrice] = useState(maxPrice);

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
  useEffect(() => {
    setSearchText(query);
    setTempMinPrice(minPrice);
    setTempMaxPrice(maxPrice);
  }, [query, minPrice, maxPrice]);

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
      sort: currentSort,
      page: currentPage,
      page_size: ITEMS_PER_PAGE,
    };

    try {
      const response = await getListings(apiParams);
      setListings(response.results);
      setTotalCount(response.count);
    } catch (err: any) {
      console.error('获取商品列表失败', err);
      setErrorMsg(err.message || '获取商品列表失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchListings();
  }, [query, currentCategory, itemType, minPrice, maxPrice, currentSort, currentPage]);

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
      <div className="catalog-header" style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700 }}>商品浏览</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>发现优质闲置二手好物</p>
        </div>
      </div>

      <div className="catalog-layout">
        {/* 侧边栏筛选面板 */}
        <aside className="filter-panel">
          {/* 搜索 */}
          <div className="filter-section">
            <h3 className="filter-section-title">搜索</h3>
            <form onSubmit={handleSearchSubmit}>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input
                  type="text"
                  className="form-control"
                  style={{ padding: '8px 12px', fontSize: '0.9rem' }}
                  placeholder="搜索商品..."
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                />
                <button type="submit" className="btn btn-primary btn-sm" style={{ padding: '0 12px' }}>🔍</button>
              </div>
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
                    style={{ padding: '8px 8px 8px 20px', fontSize: '0.85rem' }}
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
                    style={{ padding: '8px 8px 8px 20px', fontSize: '0.85rem' }}
                    placeholder="最高"
                    value={tempMaxPrice}
                    onChange={(e) => setTempMaxPrice(e.target.value)}
                  />
                </div>
              </div>
              <button type="submit" className="btn btn-outline btn-sm btn-block" style={{ marginTop: '12px' }}>
                应用区间
              </button>
            </form>
          </div>

          {/* 排序 */}
          <div className="filter-section">
            <h3 className="filter-section-title">排序方式</h3>
            <select
              className="form-control"
              style={{ padding: '8px 12px', fontSize: '0.9rem', cursor: 'pointer' }}
              value={currentSort}
              onChange={(e) => updateQueryParam({ sort: e.target.value })}
            >
              <option value="newest">最新发布</option>
              <option value="oldest">时间最久</option>
              <option value="price_asc">价格从低到高</option>
              <option value="price_desc">价格从高到低</option>
            </select>
          </div>
        </aside>

        {/* 右侧商品网格 */}
        <main className="catalog-main" style={{ display: 'flex', flexDirection: 'column', minHeight: '400px' }}>
          {errorMsg && (
            <div className="alert alert-error" style={{ marginBottom: '24px' }}>
              <span>⚠️ {errorMsg}</span>
              <button onClick={fetchListings} className="btn btn-outline btn-sm" style={{ marginLeft: '16px' }}>重试连接</button>
            </div>
          )}

          {loading ? (
            renderListingSkeletons()
          ) : listings.length === 0 ? (
            <div className="placeholder-card" style={{ margin: 'auto', width: '100%' }}>
              <h2>🔍 未搜索到相关商品</h2>
              <p>尝试清除过滤条件或换个搜索关键词试试吧。</p>
              <button
                onClick={() => setSearchParams(new URLSearchParams())}
                className="btn btn-primary btn-sm"
              >
                重置所有筛选
              </button>
            </div>
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
                      style={{ cursor: 'pointer' }}
                    >
                      <div className="listing-card-image-wrapper">
                        {cover ? (
                          <img src={cover} alt={item.title} className="listing-card-image" loading="lazy" />
                        ) : (
                          <div className="listing-card-placeholder">
                            <span className="listing-card-placeholder-icon">
                              {item.category.id === 1 ? '💻' : item.category.id === 2 ? '📚' : item.category.id === 3 ? '👕' : '🏀'}
                            </span>
                            <span>{item.category.name}</span>
                          </div>
                        )}

                        <div className="listing-card-badges">
                          <span className={`card-badge ${item.item_type === 'physical' ? 'card-badge-physical' : 'card-badge-virtual'}`}>
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
                <div className="pagination">
                  <button
                    disabled={currentPage === 1}
                    onClick={() => updateQueryParam({ page: currentPage - 1 })}
                    className="page-btn"
                  >
                    上页
                  </button>

                  {pageNumbers.map((num) => (
                    <button
                      key={num}
                      onClick={() => updateQueryParam({ page: num })}
                      className={`page-btn ${currentPage === num ? 'active' : ''}`}
                    >
                      {num}
                    </button>
                  ))}

                  <button
                    disabled={currentPage === totalPages}
                    onClick={() => updateQueryParam({ page: currentPage + 1 })}
                    className="page-btn"
                  >
                    下页
                  </button>
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
};
