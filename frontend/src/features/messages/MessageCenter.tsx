import React, { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  getConversations,
  getConversationMessages,
  getConversationMessagesAfter,
  getConversationMessagesBefore,
  sendMessageViaHttp,
  markConversationAsRead,
} from '../../api/endpoints/messages';
import { useAuth } from '../../app/providers';
import { resolveAvatarUrl } from '../../utils/media';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { Mail, ArrowLeft, Send, MessageCircle } from 'lucide-react';
import type { Conversation, Message } from '../../types/messages';

const CONVERSATIONS_CACHE_KEY = 'secondhand:conversations';

const mergeMessages = (items: Message[]): Message[] => {
  const messageMap = new Map<number, Message>();
  items.forEach((item) => {
    messageMap.set(item.id, item);
  });
  return Array.from(messageMap.values()).sort((left, right) => {
    const timeDiff = new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
    return timeDiff === 0 ? left.id - right.id : timeDiff;
  });
};

export const MessageCenter: React.FC = () => {
  const { user } = useAuth();

  // 使用 React Router 的 searchParams 管理当前选中的会话 ID，实现刷新不丢失
  const [searchParams, setSearchParams] = useSearchParams();
  const activeConvId = searchParams.get('id');

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');

  const [loadingList, setLoadingList] = useState(true);
  const [loadingChat, setLoadingChat] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [hasMoreHistory, setHasMoreHistory] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // 发送中状态
  const [sendingMessage, setSendingMessage] = useState(false);

  // 移动端会话列表显隐
  const [showSidebar, setShowSidebar] = useState(true);

  // 通道连接状态
  const [channelStatus, setChannelStatus] = useState<'connecting' | 'connected' | 'disconnected_fallback'>('connecting');

  // WebSocket 引用与消息滚动引用
  const socketRef = useRef<WebSocket | null>(null);
  const chatMessagesRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const messagesRef = useRef<Message[]>([]);
  const shouldScrollToBottomRef = useRef(true);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    let cancel = false;

    Promise.resolve()
      .then(() => {
        if (cancel) return;
        setErrorMsg('');
        try {
          const cached = localStorage.getItem(CONVERSATIONS_CACHE_KEY);
          if (cached) {
            const cachedList = JSON.parse(cached) as Conversation[];
            if (cachedList.length > 0) {
              setConversations(cachedList);
              setLoadingList(false);
            }
          }
        } catch {
          // 缓存读取失败继续走接口
        }
        return getConversations();
      })
      .then((data) => {
        if (!data || cancel) return;
        const list = data.results;
        setConversations(list);
        try {
          localStorage.setItem(CONVERSATIONS_CACHE_KEY, JSON.stringify(list));
        } catch {
          // 缓存写入失败不影响私信功能
        }
      })
      .catch((err) => {
        if (cancel) return;
        console.error('无法加载会话列表：', err);
        setErrorMsg('加载会话列表失败，请检查后端连接。');
      })
      .finally(() => {
        if (!cancel) setLoadingList(false);
      });

    return () => {
      cancel = true;
    };
  }, [user]);

  // 3. 标记会话已读
  const handleMarkRead = useCallback(async (convId: string) => {
    try {
      await markConversationAsRead(convId);
      setConversations((prev) =>
        prev.map((conversation) =>
          String(conversation.id) === convId ? { ...conversation, unread_count: 0 } : conversation
        )
      );
    } catch (err) {
      console.error('标记已读失败：', err);
    }
  }, []);

  // WebSocket 断线重连后按当前最后一条消息补齐遗漏
  const syncMessagesAfterLatest = useCallback(async (convId: string) => {
    const currentMessages = messagesRef.current;
    const latestMessageId = currentMessages[currentMessages.length - 1]?.id;
    if (!latestMessageId) return;

    try {
      const newMessages = await getConversationMessagesAfter(convId, latestMessageId);
      if (newMessages.results.length > 0) {
        shouldScrollToBottomRef.current = true;
        setMessages((prev) => mergeMessages([...prev, ...newMessages.results]));
      }
    } catch (err) {
      console.error('增量同步新消息失败：', err);
    }
  }, []);

  // 2. 加载选中会话的最新一屏消息
  const fetchMessages = useCallback(async (convId: string) => {
    setLoadingChat(true);
    try {
      const data = await getConversationMessages(convId);
      shouldScrollToBottomRef.current = true;
      setMessages(data.results);
      setHasMoreHistory(data.has_more_before);
      await handleMarkRead(convId);
    } catch (err) {
      console.error(`无法加载历史消息 (会话ID: ${convId})：`, err);
      alert('加载历史消息失败，请刷新重试。');
    } finally {
      setLoadingChat(false);
    }
  }, [handleMarkRead]);

  // 向上加载更早历史，不影响新消息的实时追加。
  const loadEarlierMessages = async () => {
    if (!activeConvId || loadingHistory || messages.length === 0) return;

    setLoadingHistory(true);
    try {
      const earlierMessages = await getConversationMessagesBefore(activeConvId, messages[0].id);
      shouldScrollToBottomRef.current = false;
      setMessages((prev) => mergeMessages([...earlierMessages.results, ...prev]));
      setHasMoreHistory(earlierMessages.has_more_before);
    } catch (err) {
      console.error('加载更早历史消息失败：', err);
      alert('加载更早历史消息失败，请稍后重试。');
    } finally {
      setLoadingHistory(false);
    }
  };

  // 4. 建立 WebSocket 连接
  const connectWebSocket = useCallback((convId: string): WebSocket | null => {
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }

    setChannelStatus('connecting');

    const token = localStorage.getItem('access_token');
    if (!token) {
      setChannelStatus('disconnected_fallback');
      return null;
    }

    try {
      const fallbackWsBaseUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
      const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL || fallbackWsBaseUrl;
      const wsUrl = `${wsBaseUrl}/ws/messages/${convId}/?token=${encodeURIComponent(token)}`;
      const socket = new WebSocket(wsUrl);

      socketRef.current = socket;

      socket.onopen = () => {
        if (socketRef.current !== socket) return;
        setChannelStatus('connected');
        syncMessagesAfterLatest(convId);
      };

      socket.onmessage = (event) => {
        if (socketRef.current !== socket) return;
        const data = JSON.parse(event.data);
        if (data.type === 'message') {
          shouldScrollToBottomRef.current = true;
          setMessages((prev) => mergeMessages([...prev, data.message]));
          handleMarkRead(convId);
        }
      };

      socket.onclose = () => {
        if (socketRef.current !== socket) return;
        setChannelStatus('disconnected_fallback');
      };

      socket.onerror = () => {
        if (socketRef.current !== socket) return;
        setChannelStatus('disconnected_fallback');
      };
      return socket;
    } catch {
      setChannelStatus('disconnected_fallback');
      return null;
    }
  }, [syncMessagesAfterLatest, handleMarkRead]);

  // 监听会话切换
  useEffect(() => {
    let activeSocket: WebSocket | null = null;
    let cancel = false;

    Promise.resolve()
      .then(() => {
        if (cancel) return;
        if (activeConvId) {
          setShowSidebar(false);
          activeSocket = connectWebSocket(activeConvId);
          return fetchMessages(activeConvId);
        }
        if (socketRef.current) {
          socketRef.current.close();
          socketRef.current = null;
        }
        setMessages([]);
        setInputText('');
        setHasMoreHistory(false);
        setChannelStatus('disconnected_fallback');
        setShowSidebar(true);
      });

    return () => {
      cancel = true;
      if (activeSocket && activeSocket.readyState !== WebSocket.CLOSED) {
        activeSocket.close();
      }
      if (socketRef.current === activeSocket) {
        socketRef.current = null;
      }
    };
  }, [activeConvId, connectWebSocket, fetchMessages]);

  // 5. 发送消息
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || !activeConvId) return;

    const msgContent = inputText.trim();
    setInputText('');
    setSendingMessage(true);

    if (channelStatus === 'connected' && socketRef.current) {
      socketRef.current.send(JSON.stringify({ content: msgContent }));
      setSendingMessage(false);
    } else {
      try {
        const data = await sendMessageViaHttp(activeConvId, msgContent);
        shouldScrollToBottomRef.current = true;
        setMessages((prev) => mergeMessages([...prev, data]));
      } catch (err: Error | unknown) {
        alert(err instanceof Error ? err.message : '发送消息失败，请稍后重试');
      } finally {
        setSendingMessage(false);
      }
    }
  };

  // 6. 自动滚动到底部
  useLayoutEffect(() => {
    if (!shouldScrollToBottomRef.current || loadingChat) return;

    window.requestAnimationFrame(() => {
      if (chatMessagesRef.current) {
        chatMessagesRef.current.scrollTop = chatMessagesRef.current.scrollHeight;
      }
      scrollRef.current?.scrollIntoView({ block: 'end' });
    });
  }, [messages, loadingChat]);

  // 查找当前选中的会话信息
  const activeConversation = conversations.find((c) => String(c.id) === activeConvId);

  const messageList = messages;

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

  return (
    <div className="messages-layout-wrapper fade-in">
      {/* 左栏：会话列表 */}
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
                  onClick={() => setSearchParams({ id: String(conv.id) })}
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

      {/* 右侧：聊天窗口 */}
      <section className={`chat-window ${!showSidebar ? 'is-visible' : 'is-hidden'}`}>
        {activeConversation ? (
          <>
            {/* 聊天窗头部 */}
            <header className="chat-header">
              <div className="chat-header-user">
                <button
                  type="button"
                  className="chat-back-btn"
                  onClick={() => {
                    setSearchParams({});
                    setShowSidebar(true);
                  }}
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

              {/* 连接通道指示器 */}
              <div className="chat-status">
                <span
                  className={`chat-status-dot chat-status-${channelStatus}`}
                  aria-hidden="true"
                />
                <Badge variant={channelStatus === 'connected' ? 'success' : 'warning'} size="sm">
                  {channelStatus === 'connected'
                    ? 'WebSocket 实时'
                    : channelStatus === 'connecting'
                    ? '正在建立连接'
                    : 'HTTP 兜底通道'}
                </Badge>
              </div>
            </header>

            {/* 消息历史滚动区 */}
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
                      onClick={loadEarlierMessages}
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
                          src={resolveAvatarUrl(
                            msg.sender.profile.avatar_url,
                            msg.sender.username
                          )}
                          alt={msg.sender.username}
                          className="chat-message-avatar"
                        />
                        <div className="chat-message-content">
                          <div
                            className={`chat-bubble ${
                              isMe ? 'chat-bubble-me' : 'chat-bubble-other'
                            }`}
                          >
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
              {/* 用于自动滚动的底部锚点 */}
              <div ref={scrollRef} />
            </div>

            {/* 输入表单 */}
            <form onSubmit={handleSendMessage} className="chat-input-form">
              <Input
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder={`向 @${
                  activeConversation.other_participant.profile.nickname ||
                  activeConversation.other_participant.username
                } 发送私信...`}
                className="chat-input"
              />
              <Button
                type="submit"
                disabled={!inputText.trim()}
                loading={sendingMessage}
                size="sm"
              >
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
    </div>
  );
};
