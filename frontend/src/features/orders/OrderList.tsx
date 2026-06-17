import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { getBuyerOrders, getSellerOrders } from '../../api/endpoints/orders';
import { useAuth } from '../../app/providers';
import { resolveMediaUrl } from '../../utils/media';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Loading } from '../../components/ui/Loading';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Package, BookOpen, Shirt, CircleDot } from 'lucide-react';
import type { Order } from '../../types/orders';

export const OrderList: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();

  // 根据当前路径判断是“我买到的” (buyer) 还是“我卖出的” (seller)
  const isSellerTab = location.pathname.includes('/orders/seller');

  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  // 加载订单列表（用于错误重试与手动刷新）
  const fetchOrders = async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const data = isSellerTab ? await getSellerOrders() : await getBuyerOrders();
      setOrders(data.results);
    } catch (err) {
      console.error(`无法加载订单列表:`, err);
      setErrorMsg('获取订单列表失败，请检查网络连接。');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancel = false;

    Promise.resolve()
      .then(() => {
        if (cancel) return;
        setLoading(true);
        setErrorMsg('');
        return isSellerTab ? getSellerOrders() : getBuyerOrders();
      })
      .then((data) => {
        if (data && !cancel) setOrders(data.results);
      })
      .catch((err) => {
        if (cancel) return;
        console.error('无法加载订单列表:', err);
        setErrorMsg('获取订单列表失败，请检查网络连接。');
      })
      .finally(() => {
        if (!cancel) setLoading(false);
      });

    return () => {
      cancel = true;
    };
  }, [isSellerTab, user]);

  const orderList = orders;

  const getOrderImageUrl = (order: Order) => {
    if (order.listing_image_snapshot) {
      return resolveMediaUrl(order.listing_image_snapshot);
    }
    const firstImage = order.listing?.images
      ? [...order.listing.images].sort((a, b) => a.sort_order - b.sort_order)[0]
      : null;
    return resolveMediaUrl(firstImage?.image_url);
  };

  // 商品分类占位图标
  const getCategoryIcon = (order: Order) => {
    const categoryId = order.listing?.category?.id;
    if (categoryId === 1) return <BookOpen size={28} />;
    if (categoryId === 2) return <Shirt size={28} />;
    if (categoryId === 3) return <CircleDot size={28} />;
    return <Package size={28} />;
  };

  // 订单状态 → Badge 变体映射
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

      {/* Tabs */}
      <div className="orders-tabs">
        <button
          type="button"
          onClick={() => navigate('/orders/buyer')}
          className={`tab-btn ${!isSellerTab ? 'active' : ''}`}
        >
          我买到的闲置 ({isSellerTab ? '查看' : orderList.length})
        </button>
        <button
          type="button"
          onClick={() => navigate('/orders/seller')}
          className={`tab-btn ${isSellerTab ? 'active' : ''}`}
        >
          我卖出的闲置 ({isSellerTab ? orderList.length : '查看'})
        </button>
      </div>

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
                <Card hover shadow="sm" className="order-card-inner">
                  {/* 商品类占位图或实体首图 */}
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
                </Card>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
