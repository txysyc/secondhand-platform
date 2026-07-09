import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  getOrderDetail,
  payOrder,
  confirmOrderDelivery,
  confirmOrderReceipt,
} from '../../api/endpoints/orders';
import { useAuth } from '../../app/providers';
import { resolveMediaUrl } from '../../utils/media';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Loading } from '../../components/ui/Loading';
import { ErrorState } from '../../components/ui/ErrorState';
import { ArrowLeft, Package, Check, CreditCard, Truck, PartyPopper, MapPin } from 'lucide-react';
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

  useEffect(() => {
    let cancel = false;

    Promise.resolve()
      .then(() => {
        if (cancel || !id) return;
        setLoading(true);
        setErrorMsg('');
        return getOrderDetail(id);
      })
      .then((data) => {
        if (data && !cancel) setOrder(data);
      })
      .catch((err) => {
        if (cancel) return;
        console.error('无法获取订单详情:', err);
        setErrorMsg('获取订单详情失败，请检查网络连接。');
      })
      .finally(() => {
        if (!cancel) setLoading(false);
      });

    return () => {
      cancel = true;
    };
  }, [id, user]);

  // 动作处理：支付
  const handlePay = async () => {
    if (!order) return;
    setSubmittingAction(true);
    try {
      const data = await payOrder(order.id);
      setOrder(data);
      alert('支付成功！');
    } catch (err: Error | unknown) {
      alert(err instanceof Error ? err.message : '支付失败，请重试');
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
      alert('发货处理成功！已通知买家确认收货。');
    } catch (err: Error | unknown) {
      alert(err instanceof Error ? err.message : '确认发货失败，请重试');
    } finally {
      setSubmittingAction(false);
    }
  };

  // 动作处理：确认收货
  const handleConfirmReceipt = async () => {
    if (!order) return;
    if (
      !window.confirm(
        '您收到闲置商品了吗？确认后将把订单交易款结算给卖家，该操作不可恢复。'
      )
    ) {
      return;
    }
    setSubmittingAction(true);
    try {
      const data = await confirmOrderReceipt(order.id);
      setOrder(data);
      alert('确认收货成功！这笔二货交易已经圆满完成。');
    } catch (err: Error | unknown) {
      alert(err instanceof Error ? err.message : '确认收货失败，请重试');
    } finally {
      setSubmittingAction(false);
    }
  };

  if (loading) {
    return <Loading text="正在努力获取交易订单详情..." />;
  }

  if (errorMsg || !order) {
    return (
      <ErrorState
        title="获取订单详情失败"
        message={errorMsg || '加载信息出错，请重试。'}
        onBack={() => navigate('/orders/buyer')}
      />
    );
  }

  const { status, viewer_role, available_actions, listing } = order;
  const displayStatus = order.is_expired ? '已过期' : order.status_display;
  const isBuyer = viewer_role === 'buyer';
  const firstListingImage = listing?.images
    ? [...listing.images].sort((left, right) => left.sort_order - right.sort_order)[0]
    : null;
  const snapshotImageUrl =
    resolveMediaUrl(order.listing_image_snapshot) || resolveMediaUrl(firstListingImage?.image_url);

  // 分类图标占位
  const getCategoryIcon = () => {
    const categoryId = listing?.category?.id;
    if (categoryId === 1) return <Package size={28} />;
    if (categoryId === 2) return <Package size={28} />;
    if (categoryId === 3) return <Package size={28} />;
    return <Package size={28} />;
  };

  // 状态巴尔姆映射（用于右上角或状态提示）
  const getStatusVariant = () => {
    if (order.is_expired) return 'error';
    if (status === 'cancelled') return 'error';
    if (status === 'pending_payment') return 'warning';
    if (status === 'awaiting_shipment' || status === 'awaiting_receipt') return 'primary';
    return 'secondary';
  };

  // 状态步骤决策 (待付款 -> 已付款 -> 已发货 -> 已完成)
  const stepIndex =
    order.completed_at || order.signed_at || status === 'completed' || status === 'signed'
      ? 4
      : order.shipped_at || status === 'awaiting_receipt'
      ? 3
      : order.paid_at || status === 'awaiting_shipment'
      ? 2
      : 1;

  // 时间轴节点数据
  const timelineSteps = [
    {
      label: '创建订单',
      date: order.created_at,
      fallback: '待创建',
      icon: <Check size={18} />,
    },
    {
      label: '买家付款',
      date: order.paid_at,
      fallback: '待付款',
      icon: <CreditCard size={18} />,
    },
    {
      label: '卖家发货',
      date: order.shipped_at,
      fallback: '待发货',
      icon: <Truck size={18} />,
    },
    {
      label: '交易完成',
      date: order.completed_at || order.signed_at,
      fallback: '待签收',
      icon: <PartyPopper size={18} />,
    },
  ];

  return (
    <div className="order-detail-container fade-in">
      <div className="order-detail-topbar">
        <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} />
          返回
        </Button>
        <div className="order-detail-meta">
          <span>订单类型: {listing?.item_type_display || '商品快照'}</span>
          <span>·</span>
          <span>
            状态:
            <Badge variant={getStatusVariant()} className="order-status-badge">
              {displayStatus}
            </Badge>
          </span>
        </div>
      </div>

      {/* 交易流转时间轴 */}
      <Card className="order-timeline-card" shadow="md">
        <h3 className="order-section-title">交易节点追踪</h3>

        <div className="order-timeline">
          <div
            className="timeline-progress"
            style={{ width: `${((stepIndex - 1) / 3) * 100}%` }}
          />
          {timelineSteps.map((step, index) => {
            const nodeIndex = index + 1;
            const isActive = stepIndex >= nodeIndex;
            const isCancelled = status === 'cancelled' && nodeIndex === 4;
            const finalActive = isActive && !isCancelled;

            return (
              <div
                key={step.label}
                className={`timeline-node ${finalActive ? 'active' : ''} ${
                  isCancelled ? 'cancelled' : ''
                }`}
              >
                <div className="timeline-marker">{finalActive ? step.icon : nodeIndex}</div>
                <span className="timeline-label">{step.label}</span>
                <span className="timeline-date">
                  {step.date
                    ? new Date(step.date).toLocaleDateString('zh-CN', {
                        month: 'numeric',
                        day: 'numeric',
                      })
                    : step.fallback}
                </span>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="order-detail-layout">
        {/* 左侧：商品详情快照及买卖双方板块 */}
        <div className="order-detail-main">
          {/* 商品信息快照 */}
          <Card className="order-snapshot-card" shadow="sm">
            <h3 className="order-section-title">宝贝快照</h3>

            <div
              className={`order-snapshot-body ${listing ? 'is-clickable' : ''}`}
              onClick={() => {
                if (listing) navigate(`/listings/${listing.id}`);
              }}
            >
              <div className="order-thumb-wrapper order-thumb-wrapper-sm">
                {snapshotImageUrl ? (
                  <img
                    src={snapshotImageUrl}
                    alt={order.listing_title_snapshot}
                    loading="lazy"
                    className="order-thumb-img"
                  />
                ) : (
                  <div className="order-thumb-placeholder">{getCategoryIcon()}</div>
                )}
              </div>
              <div className="order-snapshot-info">
                <h4 className="order-snapshot-title">{order.listing_title_snapshot}</h4>
                <p className="order-snapshot-meta">
                  分类: {listing?.category?.name || '历史快照'} · 类型:{' '}
                  {listing?.item_type_display || '未知'}
                </p>
              </div>
            </div>
          </Card>

          {/* 交易方信息卡片 */}
          <Card className="order-parties-card" shadow="sm">
            <h3 className="order-section-title">交易关联人</h3>

            <div className="order-parties-list">
              <div className="order-party-row">
                <span className="order-party-label">买家信息</span>
                <span className="order-party-value">
                  {order.buyer_display_name} (@{order.buyer?.username || '已注销'})
                </span>
              </div>
              <div className="order-party-divider" />
              <div className="order-party-row">
                <span className="order-party-label">卖家信息</span>
                <span className="order-party-value">
                  {order.seller_display_name} (@{order.seller?.username || '已注销'})
                </span>
              </div>
            </div>
          </Card>

          {/* 收货地址快照（仅实体商品有地址快照） */}
          {order.shipping_address_snapshot && (
            <Card className="order-shipping-card" shadow="sm">
              <h3 className="order-section-title">
                <MapPin size={16} />
                收货地址
              </h3>
              <div className="order-shipping-body">
                <div className="order-shipping-recipient">
                  <span className="order-shipping-name">
                    {order.shipping_address_snapshot.recipient_name}
                  </span>
                  <span className="order-shipping-phone">
                    {order.shipping_address_snapshot.phone}
                  </span>
                </div>
                <p className="order-shipping-address">
                  {order.shipping_address_snapshot.province}{' '}
                  {order.shipping_address_snapshot.city}{' '}
                  {order.shipping_address_snapshot.district}{' '}
                  {order.shipping_address_snapshot.detail_address}
                </p>
              </div>
            </Card>
          )}
        </div>

        {/* 右侧：交易结算面板与动作推进 */}
        <Card className="order-actions-card" shadow="md">
          <h3 className="order-section-title">交易结算</h3>

          <div className="order-price-block">
            <div className="order-price-label">实付金额</div>
            <div className="detail-price">{order.order_price}</div>
          </div>

          <div className="order-actions-divider" />

          {/* 动作按钮逻辑分支 */}
          <div className="order-action-stack">
            {/* 动作 1: 立即支付 */}
            {isBuyer && available_actions.includes('pay') && !order.is_expired && (
              <Button
                size="lg"
                fullWidth
                onClick={handlePay}
                loading={submittingAction}
              >
                立即支付
              </Button>
            )}

            {/* 动作 2: 卖家确认发货 */}
            {!isBuyer && available_actions.includes('confirm_delivery') && (
              <Button
                size="lg"
                fullWidth
                onClick={handleConfirmDelivery}
                loading={submittingAction}
              >
                确认发货
              </Button>
            )}

            {/* 动作 3: 买家确认收货 */}
            {isBuyer && available_actions.includes('confirm_receipt') && (
              <Button
                size="lg"
                fullWidth
                onClick={handleConfirmReceipt}
                loading={submittingAction}
              >
                确认收货
              </Button>
            )}

            {/* 过渡状态提示 */}
            {isBuyer && status === 'awaiting_shipment' && (
              <div className="alert alert-info">等待卖家确认发货…</div>
            )}

            {!isBuyer && status === 'awaiting_receipt' && (
              <div className="alert alert-info">已通知买家确认收货…</div>
            )}

            {!isBuyer && status === 'pending_payment' && (
              <div className="alert alert-warning">等待买家付款中…</div>
            )}

            {(status === 'completed' || status === 'signed') && (
              <div className="alert alert-success">交易已圆满完成</div>
            )}

            {order.is_expired && <div className="alert alert-error">订单已过期失效</div>}
          </div>
        </Card>
      </div>
    </div>
  );
};
