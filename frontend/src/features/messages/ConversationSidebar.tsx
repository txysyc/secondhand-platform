import type React from 'react';
import { Mail } from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { resolveAvatarUrl } from '../../utils/media';
import type { Conversation } from '../../types/messages';

interface ConversationSidebarProps {
  showSidebar: boolean;
  errorMsg: string;
  loadingList: boolean;
  conversations: Conversation[];
  activeConvId: string | null;
  onSelectConversation: (conversationId: string) => void;
}

const formattedTime = (dateString: string | null) =>
  dateString
    ? new Date(dateString).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    : '';

const renderConversationSkeletons = () => (
  <div className="conversation-skeleton-list" aria-hidden="true">
    {Array.from({ length: 6 }).map((_, index) => (
      <div key={index} className="conversation-item">
        <div className="skeleton-block conversation-skeleton-avatar" />
        <div className="conversation-skeleton-lines">
          <div className="skeleton-line" style={{ width: '46%' }} />
          <div className="skeleton-line" style={{ width: index % 2 === 0 ? '72%' : '58%' }} />
        </div>
      </div>
    ))}
  </div>
);

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({
  showSidebar,
  errorMsg,
  loadingList,
  conversations,
  activeConvId,
  onSelectConversation,
}) => (
  <aside className={`messages-sidebar ${showSidebar ? 'is-visible' : 'is-hidden'}`}>
    <div className="messages-sidebar-header">
      <h2>私信会话</h2>
      {errorMsg && <div className="messages-sidebar-error">{errorMsg}</div>}
    </div>

    <div className="conversation-list-container">
      {loadingList ? (
        renderConversationSkeletons()
      ) : conversations.length === 0 ? (
        <EmptyState
          icon={<Mail size={40} />}
          title="暂无会话"
          description="快去商品详情页发起聊天吧！"
          className="messages-empty-inside"
        />
      ) : (
        conversations.map((conv) => {
          const isActive = String(conv.id) === activeConvId;

          return (
            <div
              key={conv.id}
              onClick={() => onSelectConversation(String(conv.id))}
              className={`conversation-item ${isActive ? 'active' : ''}`}
            >
              <img
                src={resolveAvatarUrl(
                  conv.other_participant.profile.avatar_url,
                  conv.other_participant.username
                )}
                alt={conv.other_participant.username}
                className="conversation-avatar"
              />
              <div className="conversation-body">
                <div className="conversation-top">
                  <span className="conversation-name">
                    {conv.other_participant.profile.nickname || conv.other_participant.username}
                  </span>
                  <span className="conversation-time">
                    {formattedTime(conv.latest_message_created_at)}
                  </span>
                </div>

                <div className="conversation-bottom">
                  <p className="conversation-preview">
                    {conv.latest_message_content || '暂无内容'}
                  </p>
                  {conv.unread_count > 0 && (
                    <Badge variant="error" size="sm">
                      {conv.unread_count}
                    </Badge>
                  )}
                </div>
              </div>
            </div>
          );
        })
      )}
    </div>
  </aside>
);
