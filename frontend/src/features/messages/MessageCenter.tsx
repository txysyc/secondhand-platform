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
import { useAuth } from '../../app/auth';
import { ChatWindow } from './ChatWindow';
import { ConversationSidebar } from './ConversationSidebar';
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

  return (
    <div className="messages-layout-wrapper fade-in">
      <ConversationSidebar
        showSidebar={showSidebar}
        errorMsg={errorMsg}
        loadingList={loadingList}
        conversations={conversations}
        activeConvId={activeConvId}
        onSelectConversation={(conversationId) => setSearchParams({ id: conversationId })}
      />

      <ChatWindow
        activeConversation={activeConversation}
        showSidebar={showSidebar}
        channelStatus={channelStatus}
        chatMessagesRef={chatMessagesRef}
        scrollRef={scrollRef}
        loadingChat={loadingChat}
        messageList={messageList}
        user={user}
        hasMoreHistory={hasMoreHistory}
        loadingHistory={loadingHistory}
        inputText={inputText}
        sendingMessage={sendingMessage}
        onBack={() => {
          setSearchParams({});
          setShowSidebar(true);
        }}
        onLoadEarlierMessages={loadEarlierMessages}
        onSendMessage={handleSendMessage}
        onInputTextChange={setInputText}
      />
    </div>
  );
};
