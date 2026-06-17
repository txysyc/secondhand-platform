import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  getOrderDetail,
  payOrder,
  confirmOrderDelivery,
  confirmOrderReceipt
} from '../../api/endpoints/orders';
import { useAuth } from '../../app/providers';
import { resolveMediaUrl } from '../../utils/media';
import type { Order } from '../../types/orders';

export const OrderDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  
  // 提交状态
  const [submittingAction, setSubmittingAction] = useState(false);

  // 加载订单详情
  const fetchOrderDetail = async () => {
    if (!id) return;
    setLoading(true);
    setErrorMsg('');
    try {
      const data = await getOrderDetail(id);
      setOrder(data);
    } catch (err: any) {
      console.error(`无法获取订单详情:`, err);
      setErrorMsg('获取订单详情失败，请检查网络连接。');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrderDetail();
  }, [id, user]);

  // 动作处理：支付
  const handlePay = async () => {
    if (!order) return;
    setSubmittingAction(true);
    try {
      const data = await payOrder(order.id);
      setOrder(data);
      alert('💰 支付成功！');
    } catch (err: any) {
      alert(err.message || '支付失败，请重试');
    } finally {
      setSubmittingAction(false);
    }
  };

  // 动作处理：确认发货
  const handleConfirmDelivery = async () => {
    if (!order) return;
    setSubmittingAction(true);
    try {
      const data = await confirmOrderDelivery(order.id);
      setOrder(data);
      alert('🚚 发货处理成功！已通知买家确认收货。');
    } catch (err: any) {
      alert(err.message || '确认发货失败，请重试');
    } finally {
      setSubmittingAction(false);
    }
  };

  // 动作处理：确认收货
  const handleConfirmReceipt = async () => {
    if (!order) return;
    if (!window.confirm('您收到闲置商品了吗？确认后将把订单交易款结算给卖家，该操作不可恢复。')) {
      return;
    }
    setSubmittingAction(true);
    try {
      const data = await confirmOrderReceipt(order.id);
      setOrder(data);
      alert('🎉 确认收货成功！这笔二货交易已经圆满完成。');
    } catch (err: any) {
      alert(err.message || '确认收货失败，请重试');
    } finally {
      setSubmittingAction(false);
    }
  };

  if (loading) {
    return (
      <div className="loading-container">
        <div className="spinner"></div>
        <p>正在努力获取交易订单详情...</p>
      </div>
    );
  }

  if (errorMsg || !order) {
    return (
      <div className="placeholder-card error-card fade-in">
        <h2>⚠️ 获取订单详情失败</h2>
        <p>{errorMsg || '加载信息出错，请重试。'}</p>
        <button onClick={() => navigate('/orders/buyer')} className="btn btn-primary btn-sm">
          返回订单中心
        </button>
      </div>
    );
  }

  const { status, viewer_role, available_actions, listing } = order;
  const displayStatus = order.is_expired ? '已过期' : order.status_display;
  const isBuyer = viewer_role === 'buyer';
  const firstListingImage = listing?.images
    ? [...listing.images].sort((left, right) => left.sort_order - right.sort_order)[0]
    : null;
  const snapshotImageUrl = resolveMediaUrl(order.listing_image_snapshot) || resolveMediaUrl(firstListingImage?.image_url);
  const categoryId = listing?.category?.id;
  const categoryIcon = categoryId === 1 ? '💻' : categoryId === 2 ? '📚' : categoryId === 3 ? '👕' : '🏀';

  // 状态步骤样式决策 (待付款 -> 已付款 -> 已发货 -> 已完成)
  const stepIndex = 
    (order.completed_at || order.signed_at || status === 'completed' || status === 'signed') ? 4 :
    (order.shipped_at || status === 'awaiting_receipt') ? 3 :
    (order.paid_at || status === 'awaiting_shipment') ? 2 : 1;

  return (
    <div className="order-detail-container fade-in" style={{ maxWidth: '800px', margin: '0 auto' }}>
      <div style={{ marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button onClick={() => navigate(-1)} className="btn btn-outline btn-sm">
          ← 返回上一页
        </button>
        <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
          订单类型: {listing?.item_type_display || '商品快照'} · 状态: <strong style={{ color: order.is_expired ? 'var(--error-color)' : 'var(--primary-color)' }}>{displayStatus}</strong>
        </span>
      </div>

      {/* 交易流转时间轴 (Timeline) */}
      <section className="timeline-card card-glass-glass" style={{ padding: '32px', borderRadius: '12px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-card)', marginBottom: '32px' }}>
        <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '24px', color: 'var(--text-main)' }}>交易节点追踪</h3>
        
        <div className="order-timeline" style={{ display: 'flex', justifyContent: 'space-between', position: 'relative', padding: '0 10px' }}>
          {/* 引线定位容器 (精确定位于两端节点圆圈中心) */}
          <div style={{ position: 'absolute', top: '20px', left: '50px', right: '50px', height: '3px', zIndex: 1 }}>
            {/* 背景引线 */}
            <div style={{ width: '100%', height: '100%', backgroundColor: 'var(--border-color)' }} />
            {/* 进度激活线 */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: `${((stepIndex - 1) / 3) * 100}%`,
                height: '100%',
                backgroundColor: 'var(--primary-color)',
                zIndex: 2,
                transition: 'width 0.4s ease'
              }}
            />
          </div>

          {/* 节点 1: 创建 */}
          <div className="timeline-node" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative', zIndex: 3, width: '80px' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                backgroundColor: stepIndex >= 1 ? 'var(--primary-color)' : '#ffffff',
                border: '3px solid var(--primary-color)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: stepIndex >= 1 ? '#ffffff' : 'var(--primary-color)',
                fontWeight: 'bold',
                fontSize: '0.9rem',
                lineHeight: '34px',
                textAlign: 'center'
              }}
            >
              ✓
            </div>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, marginTop: '8px', color: stepIndex >= 1 ? 'var(--text-main)' : 'var(--text-muted)' }}>创建订单</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              {new Date(order.created_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })}
            </span>
          </div>

          {/* 节点 2: 付款 */}
          <div className="timeline-node" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative', zIndex: 3, width: '80px' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                backgroundColor: stepIndex >= 2 ? 'var(--primary-color)' : '#ffffff',
                border: `3px solid ${stepIndex >= 2 ? 'var(--primary-color)' : 'var(--border-color)'}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: stepIndex >= 2 ? '#ffffff' : 'var(--text-muted)',
                fontWeight: 'bold',
                fontSize: '0.9rem',
                lineHeight: '34px',
                textAlign: 'center'
              }}
            >
              {stepIndex >= 2 ? '✓' : '2'}
            </div>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, marginTop: '8px', color: stepIndex >= 2 ? 'var(--text-main)' : 'var(--text-muted)' }}>买家付款</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              {order.paid_at ? new Date(order.paid_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }) : '待付款'}
            </span>
          </div>

          {/* 节点 3: 发货 */}
          <div className="timeline-node" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative', zIndex: 3, width: '80px' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                backgroundColor: stepIndex >= 3 ? 'var(--primary-color)' : '#ffffff',
                border: `3px solid ${stepIndex >= 3 ? 'var(--primary-color)' : 'var(--border-color)'}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: stepIndex >= 3 ? '#ffffff' : 'var(--text-muted)',
                fontWeight: 'bold',
                fontSize: '0.9rem',
                lineHeight: '34px',
                textAlign: 'center'
              }}
            >
              {stepIndex >= 3 ? '✓' : '3'}
            </div>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, marginTop: '8px', color: stepIndex >= 3 ? 'var(--text-main)' : 'var(--text-muted)' }}>卖家发货</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              {order.shipped_at ? new Date(order.shipped_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }) : '待发货'}
            </span>
          </div>

          {/* 节点 4: 完成 */}
          <div className="timeline-node" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative', zIndex: 3, width: '80px' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                backgroundColor: stepIndex >= 4 && status !== 'cancelled' ? 'var(--primary-color)' : '#ffffff',
                border: `3px solid ${stepIndex >= 4 && status !== 'cancelled' ? 'var(--primary-color)' : 'var(--border-color)'}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: stepIndex >= 4 && status !== 'cancelled' ? '#ffffff' : 'var(--text-muted)',
                fontWeight: 'bold',
                fontSize: '0.9rem',
                lineHeight: '34px',
                textAlign: 'center'
              }}
            >
              {stepIndex >= 4 && status !== 'cancelled' ? '✓' : '4'}
            </div>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, marginTop: '8px', color: stepIndex >= 4 && status !== 'cancelled' ? 'var(--text-main)' : 'var(--text-muted)' }}>交易完成</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              {order.completed_at ? new Date(order.completed_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }) : '待签收'}
            </span>
          </div>
        </div>
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: '32px', alignItems: 'start' }}>
        {/* 左侧：商品详情快照及买卖双方板块 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* 商品信息快照 */}
          <div className="card-glass-glass" style={{ border: '1px solid var(--border-color)', borderRadius: '12px', padding: '24px', backgroundColor: 'var(--bg-card)' }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '16px', color: 'var(--text-main)' }}>宝贝快照</h3>
            
            <div
              style={{ display: 'flex', gap: '16px', cursor: listing ? 'pointer' : 'default' }}
              onClick={() => {
                if (listing) navigate(`/listings/${listing.id}`);
              }}
            >
              <div style={{ width: '80px', height: '80px', borderRadius: '8px', overflow: 'hidden', backgroundColor: 'var(--bg-main)', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {snapshotImageUrl ? (
                  <img
                    src={snapshotImageUrl}
                    alt={order.listing_title_snapshot}
                    loading="lazy"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                ) : (
                  <span style={{ fontSize: '2rem' }}>
                    {categoryIcon}
                  </span>
                )}
              </div>
              <div>
                <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '8px', lineHeight: 1.4 }}>
                  {order.listing_title_snapshot}
                </h4>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  分类: {listing?.category?.name || '历史快照'} · 类型: {listing?.item_type_display || '未知'}
                </p>
              </div>
            </div>
          </div>

          {/* 交易方信息卡片 */}
          <div className="card-glass-glass" style={{ border: '1px solid var(--border-color)', borderRadius: '12px', padding: '24px', backgroundColor: 'var(--bg-card)' }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '16px', color: 'var(--text-main)' }}>交易关联人</h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>买家信息</span>
                <span style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-main)' }}>
                  {order.buyer_display_name} (@{order.buyer?.username || '已注销'})
                </span>
              </div>
              <div style={{ height: '1px', backgroundColor: 'var(--border-color)' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>卖家信息</span>
                <span style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-main)' }}>
                  {order.seller_display_name} (@{order.seller?.username || '已注销'})
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* 右侧：交易结算结算面板与动作推进 */}
        <div className="card-glass-glass" style={{ border: '1px solid var(--border-color)', borderRadius: '12px', padding: '24px', backgroundColor: 'var(--bg-card)', position: 'sticky', top: '100px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '16px', color: 'var(--text-main)' }}>交易结算</h3>
          
          <div style={{ marginBottom: '24px' }}>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '4px' }}>实付金额</div>
            <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--error-color)' }}>
              ¥ {order.order_price}
            </div>
          </div>

          <div style={{ height: '1px', backgroundColor: 'var(--border-color)', marginBottom: '24px' }} />

          {/* 动作按钮逻辑分支 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* 动作 1: 立即支付 (针对买家且订单有 pay 动作) */}
            {isBuyer && available_actions.includes('pay') && !order.is_expired && (
              <button
                onClick={handlePay}
                disabled={submittingAction}
                className="btn btn-primary btn-block btn-lg"
              >
                {submittingAction ? '正在推进...' : '立即支付'}
              </button>
            )}

            {/* 动作 2: 卖家确认发货 (针对卖家且有 confirm_delivery) */}
            {!isBuyer && available_actions.includes('confirm_delivery') && (
              <button
                onClick={handleConfirmDelivery}
                disabled={submittingAction}
                className="btn btn-primary btn-block btn-lg"
              >
                {submittingAction ? '正在发货...' : '确认发货'}
              </button>
            )}

            {/* 动作 3: 买家确认收货 (针对买家且有 confirm_receipt) */}
            {isBuyer && available_actions.includes('confirm_receipt') && (
              <button
                onClick={handleConfirmReceipt}
                disabled={submittingAction}
                className="btn btn-primary btn-block btn-lg"
              >
                {submittingAction ? '确认收货中...' : '确认收货'}
              </button>
            )}

            {/* 各类过渡状态提示占位展示 */}
            {/* 状态 A: 买家付款后，等待卖家发货 */}
            {isBuyer && status === 'awaiting_shipment' && (
              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--primary-light)', color: 'var(--primary-color)', textAlign: 'center', fontSize: '0.9rem', fontWeight: 600 }}>
                等待卖家确认发货...
              </div>
            )}

            {/* 状态 B: 卖家发货后，等待买家收货 */}
            {!isBuyer && status === 'awaiting_receipt' && (
              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--primary-light)', color: 'var(--primary-color)', textAlign: 'center', fontSize: '0.9rem', fontWeight: 600 }}>
                已通知买家确认收货...
              </div>
            )}

            {/* 状态 C: 卖家在付款前，等待买家付款 */}
            {!isBuyer && status === 'pending_payment' && (
              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: '#fef3c7', color: '#d97706', textAlign: 'center', fontSize: '0.9rem', fontWeight: 600 }}>
                等待买家付款中...
              </div>
            )}

            {/* 状态 D: 交易完成 */}
            {(status === 'completed' || status === 'signed') && (
              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--success-bg)', color: 'var(--success-color)', textAlign: 'center', fontSize: '0.9rem', fontWeight: 600 }}>
                交易已圆满完成 ✓
              </div>
            )}

            {/* 状态 E: 过期 */}
            {order.is_expired && (
              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--error-bg)', color: 'var(--error-color)', textAlign: 'center', fontSize: '0.9rem', fontWeight: 600 }}>
                订单已过期失效
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
