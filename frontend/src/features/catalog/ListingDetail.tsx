import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, AlertCircle, ImageIcon, MessageCircle, MapPin, Star } from 'lucide-react';
import { getListingDetail } from '../../api/endpoints/listings';
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
import { Button, Card, TextArea, ErrorState, Loading } from '../../components/ui';
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

  const renderCommentSkeletons = () => (
    <div className="comments-list" aria-hidden="true">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="comment-item-group">
          <div className="comment-item">
            <div className="skeleton-block comment-avatar" />
            <div className="comment-body">
              <div className="skeleton-line skeleton-line-short" style={{ height: '14px' }} />
              <div
                className="skeleton-line"
                style={{ width: index % 2 === 0 ? '78%' : '62%', height: '14px' }}
              />
              <div className="skeleton-line" style={{ width: '44%', height: '14px' }} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="detail-container fade-in">
      <div className="detail-back-action">
        <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} />
          返回上一页
        </Button>
      </div>

      <div className="detail-layout">
        {/* 左栏：图片画廊 */}
        <section className="detail-gallery">
          <div className="gallery-preview-wrapper">
            {activeImage ? (
              <img src={activeImage} alt={listing.title} className="gallery-preview-img" />
            ) : (
              <div className="listing-card-placeholder gallery-preview-placeholder">
                <ImageIcon className="listing-card-placeholder-icon" size={64} strokeWidth={1.5} />
                <span>{listing.category.name}</span>
              </div>
            )}

            <div className="listing-card-badges">
              <span
                className={`card-badge ${
                  listing.item_type === 'physical' ? 'card-badge-physical' : 'card-badge-virtual'
                }`}
              >
                {listing.item_type_display}
              </span>
            </div>
          </div>

          {/* 缩略图选择器 */}
          {sortedImages.length > 1 && (
            <div className="gallery-thumbnails">
              {sortedImages.map((img, idx) => (
                <button
                  key={img.id}
                  onClick={() => setActiveImageIndex(idx)}
                  className={`gallery-thumb-btn ${activeImageIndex === idx ? 'active' : ''}`}
                  aria-label={`查看第 ${idx + 1} 张图片`}
                >
                  <img src={resolveMediaUrl(img.image_url) || ''} alt={`缩略图 ${idx + 1}`} />
                </button>
              ))}
            </div>
          )}
        </section>

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

            {isOwner ? (
              <div className="owner-notice">
                这是您发布的商品。您可以到"我的商品"中进行编辑或下架管理。
              </div>
            ) : (
              <>
                {/* 实体商品地址选择面板 */}
                {showAddressPicker && (
                  <div className="address-picker">
                    <h4 className="address-picker-title">
                      <MapPin size={16} />
                      选择收货地址
                    </h4>
                    {loadingAddresses ? (
                      <div className="address-picker-loading">正在加载地址…</div>
                    ) : addresses.length === 0 ? (
                      <div className="address-picker-empty">
                        <p>您还没有收货地址</p>
                        <Link to="/me/addresses" className="btn-link">
                          前往添加
                        </Link>
                      </div>
                    ) : (
                      <div className="address-picker-list">
                        {addresses.map((addr) => (
                          <label
                            key={addr.id}
                            className={`address-picker-item ${selectedAddressId === addr.id ? 'selected' : ''}`}
                          >
                            <input
                              type="radio"
                              name="address"
                              value={addr.id}
                              checked={selectedAddressId === addr.id}
                              onChange={() => setSelectedAddressId(addr.id)}
                            />
                            <div className="address-picker-info">
                              <span className="address-picker-recipient">
                                {addr.recipient_name}
                                <span className="address-picker-phone">{addr.phone}</span>
                                {addr.is_default && (
                                  <span className="address-default-badge">
                                    <Star size={11} />
                                    默认
                                  </span>
                                )}
                              </span>
                              <span className="address-picker-text">
                                {addr.province} {addr.city} {addr.district} {addr.detail_address}
                              </span>
                            </div>
                          </label>
                        ))}
                        <Link to="/me/addresses" className="btn-link address-picker-manage">
                          管理地址
                        </Link>
                      </div>
                    )}
                    <div className="address-picker-actions">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowAddressPicker(false)}
                      >
                        取消
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleConfirmBuy}
                        loading={buySubmitting}
                        disabled={!selectedAddressId || loadingAddresses}
                      >
                        确认下单
                      </Button>
                    </div>
                  </div>
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

      {/* 评论互动区域 */}
      <Card padding="md" shadow="md" className="comments-section">
        <h3 className="comments-section-title">
          <MessageCircle size={22} />
          留言与互动 ({totalCommentsCount})
        </h3>

        {/* 操作反馈提示（评论/回复/删除失败） */}
        {actionError && (
          <div className="alert alert-error" role="alert">
            <AlertCircle size={18} />
            <span>{actionError}</span>
          </div>
        )}

        {/* 发表新留言 */}
        {user ? (
          <form onSubmit={handleCreateComment} className="comment-form">
            <TextArea
              id="comment"
              value={newCommentContent}
              onChange={(e) => setNewCommentContent(e.target.value)}
              placeholder="对这件宝贝感兴趣？在这里给卖家留言询问吧..."
              rows={3}
              required
              className="comment-textarea"
            />
            <div className="comment-form-actions">
              <Button
                type="submit"
                size="sm"
                disabled={submittingComment || !newCommentContent.trim()}
                loading={submittingComment}
              >
                发表留言
              </Button>
            </div>
          </form>
        ) : (
          <div className="comment-login-promo">
            <p>登录后即可留言或回复他人关于宝贝的问答</p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigate('/login', { state: { from: { pathname: `/listings/${id}` } } })}
            >
              立即登录
            </Button>
          </div>
        )}

        {/* 留言列表 */}
        {loadingComments ? (
          renderCommentSkeletons()
        ) : comments.length === 0 ? (
          <div className="comments-empty">
            <p>暂无留言，快来问问卖家关于宝贝的问题吧！</p>
          </div>
        ) : (
          <div className="comments-list">
            {comments.map((comment) => (
              <div key={comment.id} className="comment-item-group">
                {/* 顶层评论 */}
                <div className="comment-item">
                  <img
                    src={resolveAvatarUrl(comment.author.profile?.avatar_url, comment.author.username)}
                    alt={comment.author.username}
                    className="comment-avatar"
                  />
                  <div className="comment-body">
                    <div className="comment-header">
                      <span className="comment-author-name">
                        {comment.author.profile?.nickname || comment.author.username}
                        {comment.author.id === listing?.owner?.id && (
                          <span className="comment-seller-badge">卖家</span>
                        )}
                      </span>
                      <span className="comment-meta">
                        {new Date(comment.created_at).toLocaleString('zh-CN', {
                          dateStyle: 'short',
                          timeStyle: 'short',
                        })}
                      </span>
                    </div>
                    <p className="comment-content">{comment.content}</p>
                    <div className="comment-actions">
                      {user && (
                        <button
                          onClick={() => {
                            setReplyTargetId(replyTargetId === comment.id ? null : comment.id);
                            setReplyContent('');
                          }}
                          className="btn-link"
                        >
                          回复
                        </button>
                      )}
                      {user && user.id === comment.author.id && (
                        <button onClick={() => handleDeleteComment(comment.id)} className="btn-link btn-link-danger">
                          删除
                        </button>
                      )}
                    </div>

                    {/* 就地快捷回复表单 */}
                    {replyTargetId === comment.id && (
                      <div className="reply-form">
                        <TextArea
                          id={`reply-${comment.id}`}
                          value={replyContent}
                          onChange={(e) => setReplyContent(e.target.value)}
                          placeholder={`回复 @${comment.author.profile?.nickname || comment.author.username}...`}
                          rows={2}
                          required
                          className="reply-textarea"
                        />
                        <div className="reply-form-actions">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setReplyTargetId(null);
                              setReplyContent('');
                            }}
                          >
                            取消
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            disabled={submittingReply || !replyContent.trim()}
                            loading={submittingReply}
                            onClick={() => handleCreateReply(comment.id)}
                          >
                            发表回复
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* 子回复列表 */}
                {comment.replies && comment.replies.length > 0 && (
                  <div className="replies-container">
                    {comment.replies.map((reply) => (
                      <div key={reply.id} className="reply-item">
                        <img
                          src={resolveAvatarUrl(reply.author.profile?.avatar_url, reply.author.username)}
                          alt={reply.author.username}
                          className="reply-avatar"
                        />
                        <div className="reply-body">
                          <div className="reply-header">
                            <span className="reply-author-name">
                              {reply.author.profile?.nickname || reply.author.username}
                              {reply.author.id === listing?.owner?.id && (
                                <span className="comment-seller-badge">卖家</span>
                              )}
                            </span>
                            <span className="reply-meta">
                              {new Date(reply.created_at).toLocaleString('zh-CN', {
                                dateStyle: 'short',
                                timeStyle: 'short',
                              })}
                            </span>
                          </div>
                          <p className="reply-content">{reply.content}</p>
                          <div className="reply-actions">
                            {user && user.id === reply.author.id && (
                              <button
                                onClick={() => handleDeleteComment(reply.id)}
                                className="btn-link btn-link-danger"
                              >
                                删除
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};
