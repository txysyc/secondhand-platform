import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, AlertCircle, Heart, MessageCircle } from 'lucide-react';
import {
  favoriteListing,
  getListingDetail,
  unfavoriteListing,
} from '../../api/endpoints/listings';
import {
  getListingComments,
  createListingComment,
  createCommentReply,
  deleteComment,
} from '../../api/endpoints/comments';
import { createOrder } from '../../api/endpoints/orders';
import { getAddresses } from '../../api/endpoints/addresses';
import { createConversation } from '../../api/endpoints/messages';
import { useAuth } from '../../app/providers';
import { resolveAvatarUrl, resolveMediaUrl } from '../../utils/media';
import { Button, Card, ErrorState, Loading } from '../../components/ui';
import { AddressPickerPanel } from './detail/AddressPickerPanel';
import { ListingCommentsSection } from './detail/ListingCommentsSection';
import { ListingGallery } from './detail/ListingGallery';
import type { Listing } from '../../types/listings';
import type { Comment } from '../../types/comments';
import type { UserAddress } from '../../types/address';

const getErrorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return fallback;
};

export const ListingDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  // 状态管理
  const [listing, setListing] = useState<Listing | null>(null);
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  // 评论相关状态
  const [comments, setComments] = useState<Comment[]>([]);
  const [newCommentContent, setNewCommentContent] = useState('');
  const [replyTargetId, setReplyTargetId] = useState<number | null>(null);
  const [replyContent, setReplyContent] = useState('');
  const [loadingComments, setLoadingComments] = useState(true);
  const [submittingComment, setSubmittingComment] = useState(false);
  const [submittingReply, setSubmittingReply] = useState(false);

  // 操作反馈（替代 alert）
  const [showLoginPrompt, setShowLoginPrompt] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [favoriteSubmitting, setFavoriteSubmitting] = useState(false);

  // 实体商品下单：地址选择面板
  const [showAddressPicker, setShowAddressPicker] = useState(false);
  const [addresses, setAddresses] = useState<UserAddress[]>([]);
  const [selectedAddressId, setSelectedAddressId] = useState<number | null>(null);
  const [loadingAddresses, setLoadingAddresses] = useState(false);
  const [buySubmitting, setBuySubmitting] = useState(false);

  // 获取商品详情
  useEffect(() => {
    const fetchDetail = async () => {
      if (!id) return;
      setLoading(true);
      setErrorMsg('');

      try {
        const data = await getListingDetail(id);
        setListing(data);
      } catch (err) {
        console.error(`加载商品详情失败 (ID: ${id})`, err);
        setErrorMsg(getErrorMessage(err, '加载商品详情失败，请检查网络连接。'));
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
  }, [id]);

  // 加载商品评论列表
  const fetchComments = async () => {
    if (!id) return;
    setLoadingComments(true);
    try {
      const data = await getListingComments(id);
      setComments(data);
    } catch (err) {
      console.error(`无法加载商品评论 (ID: ${id})`, err);
    } finally {
      setLoadingComments(false);
    }
  };

  /* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
  useEffect(() => {
    fetchComments();
  }, [id]);
  /* eslint-enable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */

  const clearActionFeedback = () => {
    setActionError(null);
    setShowLoginPrompt(false);
  };

  // 检查登录状态并在未登录时给出友好的 inline 提示
  const ensureLoggedIn = () => {
    if (!user) {
      setShowLoginPrompt(true);
      return false;
    }
    clearActionFeedback();
    return true;
  };

  // 发表留言
  const handleCreateComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ensureLoggedIn()) return;
    if (!newCommentContent.trim()) return;

    setSubmittingComment(true);
    try {
      await createListingComment(id!, newCommentContent);
      setNewCommentContent('');
      await fetchComments();
    } catch (err) {
      setActionError(getErrorMessage(err, '发表留言失败，请稍后重试'));
    } finally {
      setSubmittingComment(false);
    }
  };

  // 回复留言
  const handleCreateReply = async (commentId: number) => {
    if (!ensureLoggedIn()) return;
    if (!replyContent.trim()) return;

    setSubmittingReply(true);
    try {
      await createCommentReply(commentId, replyContent);
      setReplyContent('');
      setReplyTargetId(null);
      await fetchComments();
    } catch (err) {
      setActionError(getErrorMessage(err, '发表回复失败，请稍后重试'));
    } finally {
      setSubmittingReply(false);
    }
  };

  // 删除留言
  const handleDeleteComment = async (commentId: number) => {
    if (!window.confirm('您确定要永久删除这条留言吗？该操作不可恢复。')) {
      return;
    }

    try {
      await deleteComment(commentId);
      await fetchComments();
    } catch (err) {
      setActionError(getErrorMessage(err, '删除留言失败，请稍后重试'));
    }
  };

  // 购买闲置商品逻辑
  const handleBuy = async () => {
    if (!ensureLoggedIn()) return;

    // 虚拟商品：直接下单
    if (listing!.item_type === 'virtual') {
      try {
        const data = await createOrder(listing!.id);
        navigate(`/orders/${data.id}`);
      } catch (err) {
        setActionError(getErrorMessage(err, '创建订单失败，请稍后重试'));
      }
      return;
    }

    // 实体商品：展示地址选择面板
    setLoadingAddresses(true);
    setShowAddressPicker(true);
    setActionError(null);
    try {
      const data = await getAddresses();
      setAddresses(data);
      // 自动选中默认地址
      const defaultAddr = data.find((a) => a.is_default);
      setSelectedAddressId(defaultAddr?.id ?? (data[0]?.id ?? null));
    } catch {
      setActionError('获取收货地址失败，请稍后重试');
      setShowAddressPicker(false);
    } finally {
      setLoadingAddresses(false);
    }
  };

  // 确认地址后提交订单
  const handleConfirmBuy = async () => {
    if (!selectedAddressId) {
      setActionError('请先选择收货地址');
      return;
    }
    setBuySubmitting(true);
    setActionError(null);
    try {
      const data = await createOrder(listing!.id, { address_id: selectedAddressId });
      navigate(`/orders/${data.id}`);
    } catch (err) {
      setActionError(getErrorMessage(err, '创建订单失败，请稍后重试'));
    } finally {
      setBuySubmitting(false);
    }
  };

  // 联系卖家会话创建与跳转
  const handleContactSeller = async () => {
    if (!ensureLoggedIn()) return;
    if (!listing) return;

    try {
      const conversation = await createConversation(listing.owner.id);
      navigate(`/messages?id=${conversation.id}`);
    } catch (err) {
      setActionError(getErrorMessage(err, '发起会话失败，请稍后重试'));
    }
  };

  // 收藏和取消收藏商品，成功后直接更新当前详情状态。
  const handleToggleFavorite = async () => {
    if (!ensureLoggedIn()) return;
    if (!listing) return;
    // 卖家不能收藏自己发布的商品，前端同步拦截以避免无效请求。
    if (user?.id === listing.owner.id) return;

    setFavoriteSubmitting(true);
    setActionError(null);
    try {
      if (listing.is_favorited) {
        await unfavoriteListing(listing.id);
        setListing((prev) => (prev ? { ...prev, is_favorited: false } : prev));
      } else {
        await favoriteListing(listing.id);
        setListing((prev) => (prev ? { ...prev, is_favorited: true } : prev));
      }
    } catch (err) {
      setActionError(getErrorMessage(err, '收藏操作失败，请稍后重试'));
    } finally {
      setFavoriteSubmitting(false);
    }
  };

  // 按钮登录拦截逻辑
  const handleActionIntercept = (actionType: 'buy' | 'message') => {
    if (!ensureLoggedIn()) return;
    if (actionType === 'buy') {
      handleBuy();
    } else {
      handleContactSeller();
    }
  };

  if (loading) {
    return <Loading text="正在努力加载商品详情..." />;
  }

  if (errorMsg || !listing) {
    return (
      <ErrorState
        title="获取商品信息失败"
        message={errorMsg || '加载商品详情失败，请检查您的网络连接。'}
        onRetry={() => window.location.reload()}
        onBack={() => navigate('/')}
      />
    );
  }

  // 排序图片
  const sortedImages = listing.images ? [...listing.images].sort((a, b) => a.sort_order - b.sort_order) : [];

  const activeImage = resolveMediaUrl(sortedImages[activeImageIndex]?.image_url);

  // 检查是否是当前登录用户发布的商品
  const isOwner = user && user.id === listing.owner.id;

  // 计算总评论数
  const totalCommentsCount =
    comments.length + comments.reduce((acc, c) => acc + (c.replies ? c.replies.length : 0), 0);

  return (
    <div className="detail-container fade-in">
      <div className="detail-back-action">
        <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} />
          返回上一页
        </Button>
      </div>

      <div className="detail-layout">
        <ListingGallery
          listing={listing}
          images={sortedImages}
          activeImageIndex={activeImageIndex}
          activeImage={activeImage}
          onActiveImageIndexChange={setActiveImageIndex}
        />

        {/* 右栏：详细信息面板 */}
        <Card padding="lg" shadow="md" className="detail-info">
          <span className="detail-category">{listing.category.name}</span>
          <h1 className="detail-title">{listing.title}</h1>

          <div className="detail-price">
            <span>{listing.price}</span>
          </div>

          {/* 核心规格属性参数展示 */}
          <div className="detail-specs-grid">
            <div className="spec-item">
              <span className="spec-label">交付类别</span>
              <span className="spec-value">{listing.item_type_display}</span>
            </div>

            <div className="spec-item">
              <span className="spec-label">商品状态</span>
              <span className={`spec-value ${listing.status === 'active' ? 'text-success' : 'text-muted'}`}>
                {listing.status_display}
              </span>
            </div>

            {listing.item_type === 'physical' ? (
              <>
                <div className="spec-item">
                  <span className="spec-label">商品成色</span>
                  <span className="spec-value text-warning">{listing.condition_display}</span>
                </div>
                <div className="spec-item">
                  <span className="spec-label">支持交付方式</span>
                  <span className="spec-value">{listing.physical_delivery_method_display}</span>
                </div>
              </>
            ) : (
              <div className="spec-item spec-item-wide">
                <span className="spec-label">虚拟凭证有效期至</span>
                <span className="spec-value">
                  {listing.virtual_valid_until
                    ? new Date(listing.virtual_valid_until).toLocaleString('zh-CN', {
                        dateStyle: 'long',
                        timeStyle: 'short',
                      })
                    : '永久有效'}
                </span>
              </div>
            )}
          </div>

          {/* 商品描述 */}
          <div className="detail-description-section">
            <h3 className="detail-section-title">商品描述</h3>
            <p className="detail-description-text">{listing.description}</p>
          </div>

          {/* 卖家交易说明 */}
          {listing.delivery_notes && (
            <div className="detail-description-section">
              <h3 className="detail-section-title">交易说明</h3>
              <p className="detail-description-text detail-description-muted">
                {listing.delivery_notes}
              </p>
            </div>
          )}

          {/* 卖家发布者信息卡片 */}
          <Link to={`/users/${listing.owner.id}`} className="detail-owner-widget">
            <img
              src={resolveAvatarUrl(listing.owner.profile?.avatar_url, listing.owner.username)}
              alt={listing.owner.username}
              className="owner-widget-avatar"
            />
            <div className="owner-widget-info">
              <span className="owner-widget-name">
                {listing.owner.profile?.nickname || listing.owner.username}
              </span>
              <span className="owner-widget-meta">
                发布于 {new Date(listing.created_at).toLocaleDateString('zh-CN')} ·{' '}
                {listing.owner.profile?.bio || '这家伙很懒，什么都没写'}
              </span>
            </div>
          </Link>

          {/* 动作按钮逻辑联动 */}
          <div className="detail-actions">
            {showLoginPrompt && (
              <div className="alert alert-info" role="alert">
                <span>该操作需要先登录您的账号。</span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => navigate('/login', { state: { from: { pathname: `/listings/${id}` } } })}
                >
                  立即登录
                </Button>
              </div>
            )}

            {actionError && (
              <div className="alert alert-error" role="alert">
                <AlertCircle size={18} />
                <span>{actionError}</span>
              </div>
            )}

            {!isOwner && (
              <Button
                onClick={handleToggleFavorite}
                variant={listing.is_favorited ? 'secondary' : 'outline'}
                size="lg"
                fullWidth
                loading={favoriteSubmitting}
                className={listing.is_favorited ? 'detail-favorite-btn active' : 'detail-favorite-btn'}
              >
                <Heart size={18} fill={listing.is_favorited ? 'currentColor' : 'none'} />
                {listing.is_favorited ? '已收藏' : '收藏商品'}
              </Button>
            )}

            {isOwner ? (
              <div className="owner-notice">
                这是您发布的商品。您可以到"我的商品"中进行编辑或下架管理。
              </div>
            ) : (
              <>
                {/* 实体商品地址选择面板 */}
                {showAddressPicker && (
                  <AddressPickerPanel
                    addresses={addresses}
                    selectedAddressId={selectedAddressId}
                    loadingAddresses={loadingAddresses}
                    buySubmitting={buySubmitting}
                    onSelectedAddressIdChange={setSelectedAddressId}
                    onCancel={() => setShowAddressPicker(false)}
                    onConfirm={handleConfirmBuy}
                  />
                )}

                {!showAddressPicker && (
                  <>
                    <Button
                      onClick={() => handleActionIntercept('buy')}
                      disabled={listing.status !== 'active'}
                      size="lg"
                      fullWidth
                    >
                      {listing.status === 'active' ? '立即购买' : `商品已${listing.status_display}`}
                    </Button>
                    <Button
                      onClick={() => handleActionIntercept('message')}
                      variant="outline"
                      size="lg"
                      fullWidth
                    >
                      <MessageCircle size={18} />
                      联系卖家
                    </Button>
                  </>
                )}
              </>
            )}
          </div>
        </Card>
      </div>

      <ListingCommentsSection
        listing={listing}
        comments={comments}
        totalCommentsCount={totalCommentsCount}
        user={user}
        actionError={actionError}
        loadingComments={loadingComments}
        newCommentContent={newCommentContent}
        replyTargetId={replyTargetId}
        replyContent={replyContent}
        submittingComment={submittingComment}
        submittingReply={submittingReply}
        onNewCommentContentChange={setNewCommentContent}
        onReplyTargetIdChange={setReplyTargetId}
        onReplyContentChange={setReplyContent}
        onCreateComment={handleCreateComment}
        onCreateReply={handleCreateReply}
        onDeleteComment={handleDeleteComment}
        onLoginClick={() => navigate('/login', { state: { from: { pathname: `/listings/${id}` } } })}
      />
    </div>
  );
};
