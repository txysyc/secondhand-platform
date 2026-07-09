import type React from 'react';
import { ArrowLeft, Mail, MessageCircle, Send } from 'lucide-react';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { Input } from '../../components/ui/Input';
import { resolveAvatarUrl } from '../../utils/media';
import type { User } from '../../types/auth';
import type { Conversation, Message } from '../../types/messages';

interface ChatWindowProps {
  activeConversation?: Conversation;
  showSidebar: boolean;
  channelStatus: 'connecting' | 'connected' | 'disconnected_fallback';
  chatMessagesRef: React.RefObject<HTMLDivElement | null>;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  loadingChat: boolean;
  messageList: Message[];
  user: User | null;
  hasMoreHistory: boolean;
  loadingHistory: boolean;
  inputText: string;
  sendingMessage: boolean;
  onBack: () => void;
  onLoadEarlierMessages: () => void;
  onSendMessage: (event: React.FormEvent) => void;
  onInputTextChange: (value: string) => void;
}

const renderMessageSkeletons = () => (
  <div className="message-skeleton-list" aria-hidden="true">
    {Array.from({ length: 6 }).map((_, index) => {
      const isMe = index % 2 === 1;
      return (
        <div key={index} className={`message-skeleton-row ${isMe ? 'me' : ''}`}>
          <div className="skeleton-block message-skeleton-avatar" />
          <div
            className="skeleton-block message-skeleton-bubble"
            style={{
              width: index % 3 === 0 ? '46%' : '62%',
              height: index % 2 === 0 ? '44px' : '64px',
            }}
          />
        </div>
      );
    })}
  </div>
);

export const ChatWindow: React.FC<ChatWindowProps> = ({
  activeConversation,
  showSidebar,
  channelStatus,
  chatMessagesRef,
  scrollRef,
  loadingChat,
  messageList,
  user,
  hasMoreHistory,
  loadingHistory,
  inputText,
  sendingMessage,
  onBack,
  onLoadEarlierMessages,
  onSendMessage,
  onInputTextChange,
}) => (
  <section className={`chat-window ${!showSidebar ? 'is-visible' : 'is-hidden'}`}>
    {activeConversation ? (
      <>
        <header className="chat-header">
          <div className="chat-header-user">
            <button
              type="button"
              className="chat-back-btn"
              onClick={onBack}
              aria-label="返回会话列表"
            >
              <ArrowLeft size={18} />
            </button>
            <span className="chat-header-name">
              {activeConversation.other_participant.profile.nickname ||
                activeConversation.other_participant.username}
            </span>
            <span className="chat-header-username">
              @{activeConversation.other_participant.username}
            </span>
          </div>

          {/* 连接通道指示器。 */}
          <div className="chat-status">
            <span className={`chat-status-dot chat-status-${channelStatus}`} aria-hidden="true" />
            <Badge variant={channelStatus === 'connected' ? 'success' : 'warning'} size="sm">
              {channelStatus === 'connected'
                ? 'WebSocket 实时'
                : channelStatus === 'connecting'
                ? '正在建立连接'
                : 'HTTP 兜底通道'}
            </Badge>
          </div>
        </header>

        <div ref={chatMessagesRef} className="chat-messages-container">
          {loadingChat ? (
            renderMessageSkeletons()
          ) : messageList.length === 0 ? (
            <EmptyState
              icon={<MessageCircle size={40} />}
              title="开始聊天"
              description="彼此信任是流转闲置的第一步，在这里发条消息向他打个招呼吧。"
              className="messages-empty-inside"
            />
          ) : (
            <>
              {hasMoreHistory && (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={onLoadEarlierMessages}
                  loading={loadingHistory}
                  className="load-history-btn"
                >
                  加载更早消息
                </Button>
              )}

              {messageList.map((msg) => {
                const isMe = msg.sender.id === (user?.id ?? 0);
                return (
                  <div key={msg.id} className={`chat-message-row ${isMe ? 'me' : ''}`}>
                    <img
                      src={resolveAvatarUrl(msg.sender.profile.avatar_url, msg.sender.username)}
                      alt={msg.sender.username}
                      className="chat-message-avatar"
                    />
                    <div className="chat-message-content">
                      <div className={`chat-bubble ${isMe ? 'chat-bubble-me' : 'chat-bubble-other'}`}>
                        {msg.content}
                      </div>
                      <span className="chat-message-time">
                        {new Date(msg.created_at).toLocaleTimeString('zh-CN', {
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })}
                      </span>
                    </div>
                  </div>
                );
              })}
            </>
          )}
          <div ref={scrollRef} />
        </div>

        <form onSubmit={onSendMessage} className="chat-input-form">
          <Input
            type="text"
            value={inputText}
            onChange={(e) => onInputTextChange(e.target.value)}
            placeholder={`向 @${
              activeConversation.other_participant.profile.nickname ||
              activeConversation.other_participant.username
            } 发送私信...`}
            className="chat-input"
          />
          <Button type="submit" disabled={!inputText.trim()} loading={sendingMessage} size="sm">
            <Send size={16} />
            发送
          </Button>
        </form>
      </>
    ) : (
      <EmptyState
        icon={<Mail size={48} />}
        title="私信聊天中心"
        description="请在左侧列表中点击选择一个二货伙伴进行聊天，或者在商品详情页点击“联系卖家”发起会话。"
        className="messages-empty-inside"
      />
    )}
  </section>
);
