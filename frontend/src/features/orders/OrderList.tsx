import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { getBuyerOrders, getSellerOrders } from '../../api/endpoints/orders';
import { useAuth } from '../../app/providers';
import { resolveMediaUrl } from '../../utils/media';
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

  // 加载订单列表
  const fetchOrders = async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const data = isSellerTab ? await getSellerOrders() : await getBuyerOrders();
      setOrders(data.results);
    } catch (err: any) {
      console.error(`无法加载订单列表:`, err);
      setErrorMsg('获取订单列表失败，请检查网络连接。');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
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

  const getOrderCategoryIcon = (order: Order) => {
    const categoryId = order.listing?.category?.id;
    if (categoryId === 1) return '💻';
    if (categoryId === 2) return '📚';
    if (categoryId === 3) return '👕';
    return '🏀';
  };

  return (
    <div className="orders-container fade-in" style={{ maxWidth: '900px', margin: '0 auto' }}>
      <div className="orders-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-main)' }}>订单管理中心</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: '4px' }}>
            管理并推进您买入和卖出商品的所有交易流程
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="orders-tabs" style={{ display: 'flex', borderBottom: '2px solid var(--border-color)', marginBottom: '24px' }}>
        <button
          onClick={() => navigate('/orders/buyer')}
          className={`tab-btn ${!isSellerTab ? 'active' : ''}`}
          style={{
            padding: '12px 24px',
            background: 'transparent',
            border: 'none',
            fontSize: '1rem',
            fontWeight: !isSellerTab ? 600 : 500,
            color: !isSellerTab ? 'var(--primary-color)' : 'var(--text-muted)',
            borderBottom: !isSellerTab ? '3px solid var(--primary-color)' : '3px solid transparent',
            marginBottom: '-2px',
            cursor: 'pointer',
            transition: 'var(--transition-fast)'
          }}
        >
          我买到的闲置 ({isSellerTab ? '查看' : orderList.length})
        </button>
        <button
          onClick={() => navigate('/orders/seller')}
          className={`tab-btn ${isSellerTab ? 'active' : ''}`}
          style={{
            padding: '12px 24px',
            background: 'transparent',
            border: 'none',
            fontSize: '1rem',
            fontWeight: isSellerTab ? 600 : 500,
            color: isSellerTab ? 'var(--primary-color)' : 'var(--text-muted)',
            borderBottom: isSellerTab ? '3px solid var(--primary-color)' : '3px solid transparent',
            marginBottom: '-2px',
            cursor: 'pointer',
            transition: 'var(--transition-fast)'
          }}
        >
          我卖出的闲置 ({isSellerTab ? orderList.length : '查看'})
        </button>
      </div>

      {loading ? (
        <div className="loading-container">
          <div className="spinner"></div>
          <p>正在加载订单列表...</p>
        </div>
      ) : errorMsg ? (
        <div className="placeholder-card error-card">
          <h2>⚠️ 加载订单列表失败</h2>
          <p>{errorMsg}</p>
          <button onClick={fetchOrders} className="btn btn-primary btn-sm">
            重新加载
          </button>
        </div>
      ) : orderList.length === 0 ? (
        <div className="placeholder-card" style={{ padding: '48px 24px' }}>
          <span style={{ fontSize: '3rem', display: 'block', marginBottom: '16px' }}>📦</span>
          <h2>暂无相关订单</h2>
          <p>您当前在这个交易分类下还没有任何订单记录。</p>
          {!isSellerTab && (
            <button onClick={() => navigate('/')} className="btn btn-primary btn-sm">
              去首页逛逛
            </button>
          )}
        </div>
      ) : (
        <div className="orders-list" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {orderList.map((order) => {
            const displayStatus = order.is_expired ? '已过期' : order.status_display;
            const imageUrl = getOrderImageUrl(order);
            // 计算当前状态样式类
            let badgeClass = 'badge-draft';
            if (order.status === 'pending_payment') badgeClass = 'badge-protected'; // 黄色待支付
            if (order.status === 'awaiting_shipment') badgeClass = 'badge-active'; // 绿色待发货
            if (order.status === 'awaiting_receipt') badgeClass = 'badge-active'; // 绿色待收货
            if (order.status === 'completed' || order.status === 'signed') badgeClass = 'badge-draft'; // 灰色已完成
            if (order.status === 'cancelled') badgeClass = 'badge-inactive'; // 红色已取消
            if (order.is_expired) badgeClass = 'badge-inactive';

            return (
              <div
                key={order.id}
                onClick={() => navigate(`/orders/${order.id}`)}
                className="order-card-wrapper card-glass-glass"
                style={{
                  display: 'flex',
                  border: '1px solid var(--border-color)',
                  borderRadius: '12px',
                  padding: '20px',
                  cursor: 'pointer',
                  backgroundColor: 'var(--bg-card)',
                  transition: 'var(--transition-normal)',
                  gap: '20px'
                }}
              >
                {/* 商品类占位图或实体首图 */}
                <div style={{ width: '100px', height: '100px', borderRadius: '8px', overflow: 'hidden', flexShrink: 0 }}>
                  {imageUrl ? (
                    <img
                      src={imageUrl}
                      alt={order.listing_title_snapshot}
                      loading="lazy"
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    />
                  ) : (
                    <div className="listing-card-placeholder" style={{ width: '100%', height: '100%', fontSize: '0.8rem' }}>
                      <span className="listing-card-placeholder-icon" style={{ fontSize: '2rem' }}>
                        {getOrderCategoryIcon(order)}
                      </span>
                    </div>
                  )}
                </div>

                <div style={{ flexGrow: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      订单号: #{order.id}
                    </span>
                    <span className={`badge ${badgeClass}`}>
                      {displayStatus}
                    </span>
                  </div>

                  <h3
                    style={{
                      fontSize: '1.05rem',
                      fontWeight: 600,
                      color: 'var(--text-main)',
                      marginBottom: '12px',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis'
                    }}
                  >
                    {order.listing_title_snapshot}
                  </h3>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      {isSellerTab ? (
                        <span>买家: <strong>{order.buyer_display_name}</strong> (@{order.buyer?.username || '已注销'})</span>
                      ) : (
                        <span>卖家: <strong>{order.seller_display_name}</strong> (@{order.seller?.username || '已注销'})</span>
                      )}
                      <span style={{ margin: '0 8px' }}>·</span>
                      <span>创建时间: {new Date(order.created_at).toLocaleDateString('zh-CN')}</span>
                    </div>

                    <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--error-color)' }}>
                      ¥ {order.order_price}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
