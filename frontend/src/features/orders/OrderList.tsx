import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { getBuyerOrders, getSellerOrders } from '../../api/endpoints/orders';
import { useAuth } from '../../app/providers';
import { resolveMediaUrl } from '../../utils/media';
import { Badge } from '../../components/ui/Badge';
import { Loading } from '../../components/ui/Loading';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Button, Input, Pagination, Select } from '../../components/ui';
import { Package, BookOpen, Shirt, CircleDot, Search } from 'lucide-react';
import type { Order } from '../../types/orders';

const ORDER_PAGE_SIZE = 10;

const ORDER_STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'pending_payment', label: '待支付' },
  { value: 'cancelled', label: '已取消' },
  { value: 'awaiting_shipment', label: '待发货' },
  { value: 'awaiting_receipt', label: '待收货' },
  { value: 'signed', label: '已签收' },
  { value: 'completed', label: '已完成' },
];

const ORDER_SORT_OPTIONS = [
  { value: 'newest', label: '最新创建' },
  { value: 'oldest', label: '最早创建' },
  { value: 'price_asc', label: '金额从低到高' },
  { value: 'price_desc', label: '金额从高到低' },
];

export const OrderList: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();

  // 根据当前路径判断是“我买到的”还是“我卖出的”。
  const isSellerTab = location.pathname.includes('/orders/seller');

  const [orders, setOrders] = useState<Order[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  // URL 参数是订单列表筛选和分页的唯一来源，刷新页面后仍能恢复状态。
  const query = searchParams.get('q') || '';
  const status = searchParams.get('status') || 'all';
  const minPrice = searchParams.get('min_price') || '';
  const maxPrice = searchParams.get('max_price') || '';
  const createdAfter = searchParams.get('created_after') || '';
  const createdBefore = searchParams.get('created_before') || '';
  const sort = searchParams.get('sort') || 'newest';
  const currentPage = parseInt(searchParams.get('page') || '1', 10);

  const [searchText, setSearchText] = useState(query);
  const [tempMinPrice, setTempMinPrice] = useState(minPrice);
  const [tempMaxPrice, setTempMaxPrice] = useState(maxPrice);
  const [tempCreatedAfter, setTempCreatedAfter] = useState(createdAfter);
  const [tempCreatedBefore, setTempCreatedBefore] = useState(createdBefore);

  const buildApiParams = () => ({
    q: query || undefined,
    status: status !== 'all' ? status : undefined,
    min_price: minPrice || undefined,
    max_price: maxPrice || undefined,
    created_after: createdAfter || undefined,
    created_before: createdBefore || undefined,
    sort,
    page: currentPage,
    page_size: ORDER_PAGE_SIZE,
  });

  // 加载订单列表（用于错误重试与 URL 参数变化后的自动刷新）。
  const fetchOrders = async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const data = isSellerTab
        ? await getSellerOrders(buildApiParams())
        : await getBuyerOrders(buildApiParams());
      setOrders(data.results);
      setTotalCount(data.count);
    } catch (err) {
      console.error('无法加载订单列表:', err);
      setErrorMsg('获取订单列表失败，请检查网络连接。');
    } finally {
      setLoading(false);
    }
  };

  /* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
  useEffect(() => {
    fetchOrders();
  }, [isSellerTab, user, query, status, minPrice, maxPrice, createdAfter, createdBefore, sort, currentPage]);
  /* eslint-enable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    setSearchText(query);
    setTempMinPrice(minPrice);
    setTempMaxPrice(maxPrice);
    setTempCreatedAfter(createdAfter);
    setTempCreatedBefore(createdBefore);
  }, [query, minPrice, maxPrice, createdAfter, createdBefore]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const orderList = orders;
  const totalPages = Math.ceil(totalCount / ORDER_PAGE_SIZE);

  // 更新筛选参数时默认回到第一页，避免旧页码造成空结果。
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
      created_after: tempCreatedAfter,
      created_before: tempCreatedBefore,
    });
  };

  const clearFilters = () => {
    setSearchParams(new URLSearchParams());
  };

  const navigateOrderTab = (path: string) => {
    const queryString = searchParams.toString();
    navigate(queryString ? `${path}?${queryString}` : path);
  };

  const getOrderImageUrl = (order: Order) => {
    if (order.listing_image_snapshot) {
      return resolveMediaUrl(order.listing_image_snapshot);
    }
    const firstImage = order.listing?.images
      ? [...order.listing.images].sort((a, b) => a.sort_order - b.sort_order)[0]
      : null;
    return resolveMediaUrl(firstImage?.image_url);
  };

  // 商品分类占位图标。
  const getCategoryIcon = (order: Order) => {
    const categoryId = order.listing?.category?.id;
    if (categoryId === 1) return <BookOpen size={28} />;
    if (categoryId === 2) return <Shirt size={28} />;
    if (categoryId === 3) return <CircleDot size={28} />;
    return <Package size={28} />;
  };

  // 订单状态映射到统一 Badge 视觉。
  const getStatusVariant = (order: Order) => {
    if (order.is_expired) return 'error';
    switch (order.status) {
      case 'pending_payment':
        return 'warning';
      case 'awaiting_shipment':
      case 'awaiting_receipt':
        return 'primary';
      case 'completed':
      case 'signed':
        return 'secondary';
      case 'cancelled':
        return 'error';
      default:
        return 'secondary';
    }
  };

  return (
    <div className="orders-container fade-in">
      <div className="page-header page-header-row">
        <div>
          <h1>订单管理中心</h1>
          <p>管理并推进您买入和卖出商品的所有交易流程</p>
        </div>
      </div>

      <div className="orders-tabs">
        <button
          type="button"
          onClick={() => navigateOrderTab('/orders/buyer')}
          className={`tab-btn ${!isSellerTab ? 'active' : ''}`}
        >
          我买到的闲置 ({isSellerTab ? '查看' : totalCount})
        </button>
        <button
          type="button"
          onClick={() => navigateOrderTab('/orders/seller')}
          className={`tab-btn ${isSellerTab ? 'active' : ''}`}
        >
          我卖出的闲置 ({isSellerTab ? totalCount : '查看'})
        </button>
      </div>

      <form className="order-filter-panel" onSubmit={handleFilterSubmit}>
        <Input
          id="order_search"
          icon={<Search size={16} />}
          label="搜索订单"
          placeholder="订单号、商品或交易方"
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
        />
        <Select
          id="order_status"
          label="订单状态"
          options={ORDER_STATUS_OPTIONS}
          value={status}
          onChange={(event) => updateQueryParam({ status: event.target.value })}
        />
        <Select
          id="order_sort"
          label="排序"
          options={ORDER_SORT_OPTIONS}
          value={sort}
          onChange={(event) => updateQueryParam({ sort: event.target.value })}
        />
        <Input
          id="order_min_price"
          label="最低金额"
          type="number"
          value={tempMinPrice}
          onChange={(event) => setTempMinPrice(event.target.value)}
        />
        <Input
          id="order_max_price"
          label="最高金额"
          type="number"
          value={tempMaxPrice}
          onChange={(event) => setTempMaxPrice(event.target.value)}
        />
        <Input
          id="order_created_after"
          label="创建起始"
          type="datetime-local"
          value={tempCreatedAfter}
          onChange={(event) => setTempCreatedAfter(event.target.value)}
        />
        <Input
          id="order_created_before"
          label="创建截止"
          type="datetime-local"
          value={tempCreatedBefore}
          onChange={(event) => setTempCreatedBefore(event.target.value)}
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

      {loading ? (
        <Loading text="正在加载订单列表..." />
      ) : errorMsg ? (
        <ErrorState
          title="加载订单列表失败"
          message={errorMsg}
          onRetry={fetchOrders}
        />
      ) : orderList.length === 0 ? (
        <EmptyState
          icon={<Package size={40} />}
          title="暂无相关订单"
          description="您当前在这个交易分类下还没有任何订单记录。"
          action={
            !isSellerTab
              ? {
                  label: '去首页逛逛',
                  onClick: () => navigate('/'),
                  variant: 'primary',
                }
              : undefined
          }
        />
      ) : (
        <div className="orders-list">
          {orderList.map((order) => {
            const displayStatus = order.is_expired ? '已过期' : order.status_display;
            const imageUrl = getOrderImageUrl(order);

            return (
              <div
                key={order.id}
                className="order-card-wrapper"
                onClick={() => navigate(`/orders/${order.id}`)}
              >
                <article className="order-card-inner">
                  <div className="order-thumb-wrapper">
                    {imageUrl ? (
                      <img
                        src={imageUrl}
                        alt={order.listing_title_snapshot}
                        loading="lazy"
                        className="order-thumb-img"
                      />
                    ) : (
                      <div className="order-thumb-placeholder">{getCategoryIcon(order)}</div>
                    )}
                  </div>

                  <div className="order-card-body">
                    <div className="order-card-row">
                      <span className="order-card-id">订单号: #{order.id}</span>
                      <Badge variant={getStatusVariant(order)}>{displayStatus}</Badge>
                    </div>

                    <h3 className="order-card-title">{order.listing_title_snapshot}</h3>

                    <div className="order-card-row order-card-footer">
                      <div className="order-card-meta">
                        {isSellerTab ? (
                          <span>
                            买家: <strong>{order.buyer_display_name}</strong> (@
                            {order.buyer?.username || '已注销'})
                          </span>
                        ) : (
                          <span>
                            卖家: <strong>{order.seller_display_name}</strong> (@
                            {order.seller?.username || '已注销'})
                          </span>
                        )}
                        <span className="order-meta-separator">·</span>
                        <span>
                          创建时间: {new Date(order.created_at).toLocaleDateString('zh-CN')}
                        </span>
                      </div>

                      <div className="order-card-price">
                        <span>¥</span>
                        {order.order_price}
                      </div>
                    </div>
                  </div>
                </article>
              </div>
            );
          })}
        </div>
      )}

      {!loading && !errorMsg && (
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={(page) => updateQueryParam({ page })}
          ariaLabel="订单分页"
        />
      )}
    </div>
  );
};
