import React, { useState, useEffect, useLayoutEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  getConversations,
  getConversationMessages,
  getConversationMessagesAfter,
  getConversationMessagesBefore,
  sendMessageViaHttp,
  markConversationAsRead
} from '../../api/endpoints/messages';
import { useAuth } from '../../app/providers';
import { resolveAvatarUrl } from '../../utils/media';
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

  // 通道连接状态：'connecting' | 'connected' | 'disconnected_fallback'
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

  // 1. 初始化及加载会话列表
  const fetchConversations = async () => {
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
      // 会话缓存只是首屏体验优化，读取失败时继续走实时接口。
    }

    try {
      const data = await getConversations();
      const list = data.results;
      setConversations(list);
      try {
        localStorage.setItem(CONVERSATIONS_CACHE_KEY, JSON.stringify(list));
      } catch {
        // 缓存写入失败不影响私信功能。
      }
    } catch (err: any) {
      console.error('无法加载会话列表：', err);
      setErrorMsg('加载会话列表失败，请检查后端连接。');
    } finally {
      setLoadingList(false);
    }
  };

  useEffect(() => {
    fetchConversations();
  }, [user]);

  // 2. 加载选中会话的最新一屏消息
  const fetchMessages = async (convId: string) => {
    setLoadingChat(true);
    try {
      const data = await getConversationMessages(convId);
      shouldScrollToBottomRef.current = true;
      setMessages(data);
      setHasMoreHistory(data.length >= 20);
      await handleMarkRead(convId);
    } catch (err: any) {
      console.error(`无法加载历史消息 (会话ID: ${convId})：`, err);
      alert('加载历史消息失败，请刷新重试。');
    } finally {
      setLoadingChat(false);
    }
  };

  // 向上加载更早历史，不影响新消息的实时追加。
  const loadEarlierMessages = async () => {
    if (!activeConvId || loadingHistory || messages.length === 0) return;

    setLoadingHistory(true);
    try {
      const earlierMessages = await getConversationMessagesBefore(activeConvId, messages[0].id);
      shouldScrollToBottomRef.current = false;
      setMessages((prev) => mergeMessages([...earlierMessages, ...prev]));
      setHasMoreHistory(earlierMessages.length >= 20);
    } catch (err) {
      console.error('加载更早历史消息失败：', err);
      alert('加载更早历史消息失败，请稍后重试。');
    } finally {
      setLoadingHistory(false);
    }
  };

  // WebSocket 断线重连后按当前最后一条消息补齐遗漏，避免重新拉取整屏历史。
  const syncMessagesAfterLatest = async (convId: string) => {
    const currentMessages = messagesRef.current;
    const latestMessageId = currentMessages[currentMessages.length - 1]?.id;
    if (!latestMessageId) return;

    try {
      const newMessages = await getConversationMessagesAfter(convId, latestMessageId);
      if (newMessages.length > 0) {
        shouldScrollToBottomRef.current = true;
        setMessages((prev) => mergeMessages([...prev, ...newMessages]));
      }
    } catch (err) {
      console.error('增量同步新消息失败：', err);
    }
  };

  // 3. 标记会话已读
  const handleMarkRead = async (convId: string) => {
    try {
      await markConversationAsRead(convId);
      setConversations((prev) =>
        prev.map((conversation) =>
          String(conversation.id) === convId
            ? { ...conversation, unread_count: 0 }
            : conversation
        )
      );
    } catch (err) {
      console.error('标记已读失败：', err);
    }
  };

  // 4. 建立 WebSocket 连接
  const connectWebSocket = (convId: string): WebSocket | null => {
    // 每次切换会话，关闭前一个 socket
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
      // 建立长连接
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
          // 收到新消息，追加
          shouldScrollToBottomRef.current = true;
          setMessages((prev) => mergeMessages([...prev, data.message]));
          // 如果正在查看此窗口，标记已读
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
    } catch (e) {
      setChannelStatus('disconnected_fallback');
      return null;
    }
  };

  // 监听会话切换
  useEffect(() => {
    let activeSocket: WebSocket | null = null;

    if (activeConvId) {
      fetchMessages(activeConvId);
      activeSocket = connectWebSocket(activeConvId);
    } else {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      setMessages([]);
      setInputText('');
      setHasMoreHistory(false);
      setChannelStatus('disconnected_fallback');
    }
    return () => {
      if (activeSocket && activeSocket.readyState !== WebSocket.CLOSED) {
        activeSocket.close();
      }
      if (socketRef.current === activeSocket) {
        socketRef.current = null;
      }
    };
  }, [activeConvId]);

  // 5. 发送消息
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || !activeConvId) return;

    const msgContent = inputText.trim();
    setInputText('');

    if (channelStatus === 'connected' && socketRef.current) {
      // 如果 WebSocket 连接，走 WebSocket 发送
      socketRef.current.send(JSON.stringify({ content: msgContent }));
    } else {
      // 否则走 HTTP 接口发送并降级
      try {
        const data = await sendMessageViaHttp(activeConvId, msgContent);
        shouldScrollToBottomRef.current = true;
        setMessages((prev) => mergeMessages([...prev, data]));
      } catch (err: any) {
        alert(err.message || '发送消息失败，请稍后重试');
      }
    }
  };

  // 6. 自动滚动到底部；进入会话时要等消息列表真正渲染后再定位。
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

  const renderConversationSkeletons = () => (
    <div style={{ padding: '8px 0' }} aria-hidden="true">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="conversation-item" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className="skeleton-block" style={{ width: '44px', height: '44px', borderRadius: '50%', flexShrink: 0 }} />
          <div style={{ flexGrow: 1 }}>
            <div className="skeleton-line" style={{ width: '46%', height: '14px', marginBottom: '10px' }} />
            <div className="skeleton-line" style={{ width: index % 2 === 0 ? '72%' : '58%', height: '12px' }} />
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
          <div key={index} style={{ display: 'flex', flexDirection: isMe ? 'row-reverse' : 'row', alignItems: 'flex-start', gap: '12px' }}>
            <div className="skeleton-block" style={{ width: '36px', height: '36px', borderRadius: '50%', flexShrink: 0 }} />
            <div
              className="skeleton-block"
              style={{
                width: index % 3 === 0 ? '46%' : '62%',
                height: index % 2 === 0 ? '44px' : '64px',
                borderRadius: '12px',
              }}
            />
          </div>
        );
      })}
    </div>
  );

  return (
    <div className="messages-layout-wrapper fade-in" style={{ height: 'calc(100vh - 220px)', maxWidth: '1100px', margin: '0 auto', display: 'flex', border: '1px solid var(--border-color)', borderRadius: '12px', overflow: 'hidden', backgroundColor: 'var(--bg-card)', boxShadow: 'var(--shadow-md)' }}>
      {/* 左栏：会话列表 */}
      <aside className="messages-sidebar" style={{ width: '320px', borderRight: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', backgroundColor: '#ffffff' }}>
        <div style={{ padding: '20px', borderBottom: '1px solid var(--border-color)' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)' }}>私信会话</h2>
          {errorMsg && (
            <div style={{ color: 'var(--error-color)', fontSize: '0.8rem', marginTop: '8px' }}>
              ⚠️ {errorMsg}
            </div>
          )}
        </div>

        <div className="conversation-list-container" style={{ flexGrow: 1, overflowY: 'auto' }}>
          {loadingList ? (
            renderConversationSkeletons()
          ) : conversations.length === 0 ? (
            <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              📭 暂无会话。快去商品详情页发起聊天吧！
            </div>
          ) : (
            conversations.map((conv) => {
              const isActive = String(conv.id) === activeConvId;
              const formattedTime = conv.latest_message_created_at
                ? new Date(conv.latest_message_created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
                : '';

              return (
                <div
                  key={conv.id}
                  onClick={() => setSearchParams({ id: String(conv.id) })}
                  className={`conversation-item ${isActive ? 'active' : ''}`}
                  style={{
                    padding: '16px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    cursor: 'pointer',
                    borderBottom: '1px solid var(--bg-main)',
                    backgroundColor: isActive ? 'var(--primary-light)' : 'transparent',
                    transition: 'var(--transition-fast)'
                  }}
                >
                  <img
                    src={resolveAvatarUrl(conv.other_participant.profile.avatar_url, conv.other_participant.username)}
                    alt={conv.other_participant.username}
                    style={{ width: '44px', height: '44px', borderRadius: '50%', objectFit: 'cover', border: '1px solid var(--border-color)' }}
                  />
                  <div style={{ flexGrow: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '4px' }}>
                      <span style={{ fontWeight: 600, fontSize: '0.95rem', color: isActive ? 'var(--primary-color)' : 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {conv.other_participant.profile.nickname || conv.other_participant.username}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {formattedTime}
                      </span>
                    </div>
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', margin: 0, flexGrow: 1, marginRight: '8px' }}>
                        {conv.latest_message_content || '暂无内容'}
                      </p>
                      {conv.unread_count > 0 && (
                        <span style={{ minWidth: '18px', height: '18px', borderRadius: '9px', backgroundColor: 'var(--error-color)', color: '#ffffff', fontSize: '0.7rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 5px' }}>
                          {conv.unread_count}
                        </span>
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
      <section className="chat-window" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-main)' }}>
        {activeConversation ? (
          <>
            {/* 聊天窗头部 */}
            <header className="chat-header" style={{ padding: '16px 24px', backgroundColor: '#ffffff', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <span style={{ fontWeight: 700, fontSize: '1.05rem', color: 'var(--text-main)' }}>
                  {activeConversation.other_participant.profile.nickname || activeConversation.other_participant.username}
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginLeft: '8px' }}>
                  @{activeConversation.other_participant.username}
                </span>
              </div>

              {/* 连接通道指示器 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span
                  style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    backgroundColor: channelStatus === 'connected' ? 'var(--success-color)' : channelStatus === 'connecting' ? 'var(--warning-color)' : '#f59e0b',
                    display: 'inline-block'
                  }}
                />
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {channelStatus === 'connected' ? 'WebSocket 实时' : channelStatus === 'connecting' ? '正在建立连接...' : 'HTTP 兜底通道开启'}
                </span>
              </div>
            </header>

            {/* 消息历史滚动区 */}
            <div ref={chatMessagesRef} className="chat-messages-container" style={{ flexGrow: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {loadingChat ? (
                renderMessageSkeletons()
              ) : messageList.length === 0 ? (
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '40px', fontSize: '0.9rem' }}>
                  💬 彼此信任是流转闲置的第一步，在这里发条消息向他打个招呼吧。
                </div>
              ) : (
                <>
                  {hasMoreHistory && (
                    <button
                      type="button"
                      onClick={loadEarlierMessages}
                      disabled={loadingHistory}
                      className="btn btn-secondary btn-sm"
                      style={{ alignSelf: 'center', padding: '8px 14px' }}
                    >
                      {loadingHistory ? '加载中...' : '加载更早消息'}
                    </button>
                  )}

                  {messageList.map((msg) => {
                    const isMe = msg.sender.id === (user?.id || 1);
                    return (
                      <div
                        key={msg.id}
                        style={{
                          display: 'flex',
                          flexDirection: isMe ? 'row-reverse' : 'row',
                          alignItems: 'flex-start',
                          gap: '12px'
                        }}
                      >
                        <img
                          src={resolveAvatarUrl(msg.sender.profile.avatar_url, msg.sender.username)}
                          alt={msg.sender.username}
                          style={{ width: '36px', height: '36px', borderRadius: '50%', objectFit: 'cover', border: '1px solid var(--border-color)', flexShrink: 0 }}
                        />
                        <div style={{ maxWidth: '65%', display: 'flex', flexDirection: 'column', alignItems: isMe ? 'flex-end' : 'flex-start' }}>
                          <div
                            className={`chat-bubble ${isMe ? 'chat-bubble-me' : 'chat-bubble-other'}`}
                            style={{
                              padding: '12px 16px',
                              borderRadius: '12px',
                              borderTopLeftRadius: !isMe ? '2px' : '12px',
                              borderTopRightRadius: isMe ? '2px' : '12px',
                              backgroundColor: isMe ? 'var(--primary-color)' : '#ffffff',
                              color: isMe ? '#ffffff' : 'var(--text-main)',
                              fontSize: '0.95rem',
                              lineHeight: 1.5,
                              border: isMe ? 'none' : '1px solid var(--border-color)',
                              boxShadow: 'var(--shadow-sm)',
                              wordBreak: 'break-word',
                              whiteSpace: 'pre-wrap'
                            }}
                          >
                            {msg.content}
                          </div>
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                            {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
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
            <form onSubmit={handleSendMessage} className="chat-input-form" style={{ padding: '20px 24px', backgroundColor: '#ffffff', borderTop: '1px solid var(--border-color)', display: 'flex', gap: '16px' }}>
              <input
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder={`向 @${activeConversation.other_participant.profile.nickname || activeConversation.other_participant.username} 发送私信...`}
                style={{
                  flexGrow: 1,
                  padding: '12px 16px',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  backgroundColor: 'var(--bg-main)',
                  color: 'var(--text-main)',
                  outline: 'none',
                  fontSize: '0.95rem',
                  transition: 'var(--transition-fast)'
                }}
                className="chat-input"
              />
              <button
                type="submit"
                disabled={!inputText.trim()}
                className="btn btn-primary btn-sm"
                style={{ padding: '0 20px' }}
              >
                发送
              </button>
            </form>
          </>
        ) : (
          <div style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px', color: 'var(--text-muted)' }}>
            <span style={{ fontSize: '4rem', marginBottom: '16px' }}>✉️</span>
            <h3>私信聊天中心</h3>
            <p style={{ marginTop: '8px', fontSize: '0.9rem' }}>
              请在左侧列表中点击选择一个二货伙伴进行聊天，或者在商品详情页点击“联系卖家”发起会话。
            </p>
          </div>
        )}
      </section>
    </div>
  );
};
