import type React from 'react';
import { AlertCircle, MessageCircle } from 'lucide-react';

import { Button, Card, TextArea } from '../../../components/ui';
import { resolveAvatarUrl } from '../../../utils/media';
import type { Comment } from '../../../types/comments';
import type { Listing } from '../../../types/listings';
import type { User } from '../../../types/auth';

interface ListingCommentsSectionProps {
  listing: Listing;
  comments: Comment[];
  totalCommentsCount: number;
  user: User | null;
  actionError: string | null;
  loadingComments: boolean;
  newCommentContent: string;
  replyTargetId: number | null;
  replyContent: string;
  submittingComment: boolean;
  submittingReply: boolean;
  onNewCommentContentChange: (value: string) => void;
  onReplyTargetIdChange: (value: number | null) => void;
  onReplyContentChange: (value: string) => void;
  onCreateComment: (event: React.FormEvent) => void;
  onCreateReply: (commentId: number) => void;
  onDeleteComment: (commentId: number) => void;
  onLoginClick: () => void;
}

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

export const ListingCommentsSection: React.FC<ListingCommentsSectionProps> = ({
  listing,
  comments,
  totalCommentsCount,
  user,
  actionError,
  loadingComments,
  newCommentContent,
  replyTargetId,
  replyContent,
  submittingComment,
  submittingReply,
  onNewCommentContentChange,
  onReplyTargetIdChange,
  onReplyContentChange,
  onCreateComment,
  onCreateReply,
  onDeleteComment,
  onLoginClick,
}) => (
  <Card padding="md" shadow="md" className="comments-section">
    <h3 className="comments-section-title">
      <MessageCircle size={22} />
      留言与互动 ({totalCommentsCount})
    </h3>

    {/* 操作反馈提示，覆盖评论、回复和删除失败。 */}
    {actionError && (
      <div className="alert alert-error" role="alert">
        <AlertCircle size={18} />
        <span>{actionError}</span>
      </div>
    )}

    {/* 发表新留言。 */}
    {user ? (
      <form onSubmit={onCreateComment} className="comment-form">
        <TextArea
          id="comment"
          value={newCommentContent}
          onChange={(e) => onNewCommentContentChange(e.target.value)}
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
        <Button size="sm" variant="outline" onClick={onLoginClick}>
          立即登录
        </Button>
      </div>
    )}

    {/* 留言列表。 */}
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
                    {comment.author.id === listing.owner.id && <span className="comment-seller-badge">卖家</span>}
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
                        onReplyTargetIdChange(replyTargetId === comment.id ? null : comment.id);
                        onReplyContentChange('');
                      }}
                      className="btn-link"
                    >
                      回复
                    </button>
                  )}
                  {user && user.id === comment.author.id && (
                    <button onClick={() => onDeleteComment(comment.id)} className="btn-link btn-link-danger">
                      删除
                    </button>
                  )}
                </div>

                {/* 就地快捷回复表单。 */}
                {replyTargetId === comment.id && (
                  <div className="reply-form">
                    <TextArea
                      id={`reply-${comment.id}`}
                      value={replyContent}
                      onChange={(e) => onReplyContentChange(e.target.value)}
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
                          onReplyTargetIdChange(null);
                          onReplyContentChange('');
                        }}
                      >
                        取消
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        disabled={submittingReply || !replyContent.trim()}
                        loading={submittingReply}
                        onClick={() => onCreateReply(comment.id)}
                      >
                        发表回复
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>

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
                          {reply.author.id === listing.owner.id && (
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
                          <button onClick={() => onDeleteComment(reply.id)} className="btn-link btn-link-danger">
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
);
