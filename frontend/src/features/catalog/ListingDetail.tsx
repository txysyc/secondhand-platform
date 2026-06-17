import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { getListingDetail } from '../../api/endpoints/listings';
import {
  getListingComments,
  createListingComment,
  createCommentReply,
  deleteComment
} from '../../api/endpoints/comments';
import { createOrder } from '../../api/endpoints/orders';
import { createConversation } from '../../api/endpoints/messages';

import { useAuth } from '../../app/providers';
import { resolveAvatarUrl, resolveMediaUrl } from '../../utils/media';
import type { Listing } from '../../types/listings';
import type { Comment } from '../../types/comments';

// --- 与列表页共享的 Mock 数据集 (做降级展示用) ---
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

  // 获取商品详情
  useEffect(() => {
    const fetchDetail = async () => {
      if (!id) return;
      setLoading(true);
      setErrorMsg('');

      try {
        const data = await getListingDetail(id);
        setListing(data);
      } catch (err: any) {
        console.error(`加载商品详情失败 (ID: ${id})`, err);
        setErrorMsg(err.message || '加载商品详情失败，请检查网络连接。');
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

  useEffect(() => {
    fetchComments();
  }, [id]);

  // 发表留言
  const handleCreateComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) {
      alert('请先登录后再发表留言！');
      navigate('/login', { state: { from: { pathname: `/listings/${id}` } } });
      return;
    }
    if (!newCommentContent.trim()) return;

    setSubmittingComment(true);
    try {
      await createListingComment(id!, newCommentContent);
      setNewCommentContent('');
      await fetchComments();
    } catch (err: any) {
      alert(err.message || '发表留言失败，请稍后重试');
    } finally {
      setSubmittingComment(false);
    }
  };

  // 回复留言
  const handleCreateReply = async (commentId: number) => {
    if (!user) {
      alert('请先登录后再回复留言！');
      navigate('/login', { state: { from: { pathname: `/listings/${id}` } } });
      return;
    }
    if (!replyContent.trim()) return;

    setSubmittingReply(true);
    try {
      await createCommentReply(commentId, replyContent);
      setReplyContent('');
      setReplyTargetId(null);
      await fetchComments();
    } catch (err: any) {
      alert(err.message || '发表回复失败，请稍后重试');
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
    } catch (err: any) {
      alert(err.message || '删除留言失败，请稍后重试');
    }
  };

  // 购买闲置商品逻辑
  const handleBuy = async () => {
    if (!user) {
      alert('该操作需要先登录您的账号！将为您跳转至登录页。');
      navigate('/login', { state: { from: { pathname: `/listings/${id}` } } });
      return;
    }

    try {
      const data = await createOrder(listing!.id);
      navigate(`/orders/${data.id}`);
    } catch (err: any) {
      alert(err.message || '创建订单失败，请稍后重试');
    }
  };

  // 联系卖家会话创建与跳转
  const handleContactSeller = async () => {
    if (!listing) return;
    try {
      const conversation = await createConversation(listing.owner.id);
      navigate(`/messages?id=${conversation.id}`);
    } catch (err: any) {
      alert(err.message || '发起会话失败，请稍后重试');
    }
  };

  // 按钮登录拦截逻辑
  const handleActionIntercept = (actionType: 'buy' | 'message') => {
    if (!user) {
      // 未登录，拦截并重定向
      alert('该操作需要先登录您的账号！将为您跳转至登录页。');
      navigate('/login', { state: { from: { pathname: `/listings/${id}` } } });
    } else {
      if (actionType === 'buy') {
        handleBuy();
      } else {
        handleContactSeller();
      }
    }
  };


  if (loading) {
    return (
      <div className="loading-container">
        <div className="spinner"></div>
        <p>正在努力加载商品详情...</p>
      </div>
    );
  }

  if (errorMsg || !listing) {
    return (
      <div className="placeholder-card error-card fade-in">
        <h2>⚠️ 获取商品信息失败</h2>
        <p>{errorMsg || '加载商品详情失败，请检查您的网络连接。'}</p>
        <button onClick={() => navigate('/')} className="btn btn-primary btn-sm">
          返回商品列表
        </button>
      </div>
    );
  }

  // 排序图片
  const sortedImages = listing.images
    ? [...listing.images].sort((a, b) => a.sort_order - b.sort_order)
    : [];

  const activeImage = resolveMediaUrl(sortedImages[activeImageIndex]?.image_url);

  // 检查是否是当前登录用户发布的商品
  const isOwner = user && user.id === listing.owner.id;

  // 计算总评论数
  const totalCommentsCount = comments.length + comments.reduce((acc, c) => acc + (c.replies ? c.replies.length : 0), 0);

  const renderCommentSkeletons = () => (
    <div className="comments-list" aria-hidden="true">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="comment-item-group">
          <div className="comment-item">
            <div className="skeleton-block comment-avatar" />
            <div className="comment-body">
              <div className="skeleton-line" style={{ width: '32%', height: '14px', marginBottom: '12px' }} />
              <div className="skeleton-line" style={{ width: index % 2 === 0 ? '78%' : '62%', height: '14px', marginBottom: '10px' }} />
              <div className="skeleton-line" style={{ width: '44%', height: '14px' }} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="detail-container fade-in">
      <div style={{ marginBottom: '20px' }}>
        <button onClick={() => navigate(-1)} className="btn btn-outline btn-sm">
          ← 返回上一页
        </button>
      </div>

      <div className="detail-layout">
        {/* 左栏：图片画廊 */}
        <section className="detail-gallery">
          <div className="gallery-preview-wrapper">
            {activeImage ? (
              <img src={activeImage} alt={listing.title} className="gallery-preview-img" />
            ) : (
              <div className="listing-card-placeholder" style={{ borderRadius: '12px' }}>
                <span className="listing-card-placeholder-icon" style={{ fontSize: '4rem' }}>
                  {listing.category.id === 1 ? '💻' : listing.category.id === 2 ? '📚' : listing.category.id === 3 ? '👕' : '🏀'}
                </span>
                <span style={{ fontSize: '1.2rem', fontWeight: 600 }}>{listing.category.name}占位图片</span>
              </div>
            )}

            <div className="listing-card-badges">
              <span className={`card-badge ${listing.item_type === 'physical' ? 'card-badge-physical' : 'card-badge-virtual'}`} style={{ fontSize: '0.85rem' }}>
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
                >
                  <img src={resolveMediaUrl(img.image_url) || ''} alt={`缩略图 ${idx + 1}`} />
                </button>
              ))}
            </div>
          )}
        </section>

        {/* 右栏：详细信息面板 */}
        <section className="detail-info">
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
              <span className="spec-value" style={{ color: listing.status === 'active' ? 'var(--success-color)' : 'var(--text-muted)' }}>
                {listing.status_display}
              </span>
            </div>

            {listing.item_type === 'physical' ? (
              <>
                <div className="spec-item">
                  <span className="spec-label">商品成色</span>
                  <span className="spec-value" style={{ color: 'var(--warning-color)' }}>{listing.condition_display}</span>
                </div>
                <div className="spec-item">
                  <span className="spec-label">支持交付方式</span>
                  <span className="spec-value">{listing.physical_delivery_method_display}</span>
                </div>
              </>
            ) : (
              <div className="spec-item" style={{ gridColumn: 'span 2' }}>
                <span className="spec-label">虚拟凭证有效期至</span>
                <span className="spec-value">
                  {listing.virtual_valid_until
                    ? new Date(listing.virtual_valid_until).toLocaleString('zh-CN', { dateStyle: 'long', timeStyle: 'short' })
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
              <p className="detail-description-text" style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
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
              <span className="owner-widget-name">{listing.owner.profile?.nickname || listing.owner.username}</span>
              <span className="owner-widget-meta">
                发布于 {new Date(listing.created_at).toLocaleDateString('zh-CN')} · {listing.owner.profile?.bio || '这家伙很懒，什么都没写'}
              </span>
            </div>
          </Link>

          {/* 动作按钮逻辑联动 */}
          <div className="detail-actions">
            {isOwner ? (
              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--primary-light)', color: 'var(--primary-color)', textAlign: 'center', fontWeight: 600 }}>
                这是您发布的商品。您可以到“我的商品”中进行编辑或下架管理。
              </div>
            ) : (
              <>
                <button
                  onClick={() => handleActionIntercept('buy')}
                  disabled={listing.status !== 'active'}
                  className="btn btn-primary btn-block btn-lg"
                >
                  {listing.status === 'active' ? '立即购买' : `商品已${listing.status_display}`}
                </button>
                <button
                  onClick={() => handleActionIntercept('message')}
                  className="btn btn-outline btn-block btn-lg"
                >
                  💬 联系卖家
                </button>
              </>
            )}
          </div>
        </section>
      </div>

      {/* 评论互动区域 */}
      <section className="comments-section card-glass-glass">
        <h3 className="comments-section-title">💬 留言与互动 ({totalCommentsCount})</h3>

        {/* 发表新留言 */}
        {user ? (
          <form onSubmit={handleCreateComment} className="comment-form">
            <textarea
              value={newCommentContent}
              onChange={(e) => setNewCommentContent(e.target.value)}
              placeholder="对这件宝贝感兴趣？在这里给卖家留言询问吧..."
              rows={3}
              required
              className="comment-textarea"
            />
            <div className="comment-form-actions">
              <button
                type="submit"
                disabled={submittingComment || !newCommentContent.trim()}
                className="btn btn-primary btn-sm"
              >
                {submittingComment ? '正在发表...' : '发表留言'}
              </button>
            </div>
          </form>
        ) : (
          <div className="comment-login-promo">
            <p>登录后即可留言或回复他人关于宝贝的问答</p>
            <button
              onClick={() => navigate('/login', { state: { from: { pathname: `/listings/${id}` } } })}
              className="btn btn-outline btn-sm"
            >
              立即登录
            </button>
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
                        {new Date(comment.created_at).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })}
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
                        <button
                          onClick={() => handleDeleteComment(comment.id)}
                          className="btn-link btn-link-danger"
                        >
                          删除
                        </button>
                      )}
                    </div>

                    {/* 就地快捷回复表单 */}
                    {replyTargetId === comment.id && (
                      <div className="reply-form">
                        <textarea
                          value={replyContent}
                          onChange={(e) => setReplyContent(e.target.value)}
                          placeholder={`回复 @${comment.author.profile?.nickname || comment.author.username}...`}
                          rows={2}
                          required
                          className="reply-textarea"
                        />
                        <div className="reply-form-actions">
                          <button
                            type="button"
                            onClick={() => {
                              setReplyTargetId(null);
                              setReplyContent('');
                            }}
                            className="btn btn-outline btn-xs"
                          >
                            取消
                          </button>
                          <button
                            type="button"
                            disabled={submittingReply || !replyContent.trim()}
                            onClick={() => handleCreateReply(comment.id)}
                            className="btn btn-primary btn-xs"
                          >
                            {submittingReply ? '发表中...' : '发表回复'}
                          </button>
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
                              {new Date(reply.created_at).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })}
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
      </section>
    </div>
  );
};
