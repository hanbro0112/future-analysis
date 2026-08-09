'use client';

/**
 * PTT Stock 板盤中/盤後閒聊彈窗
 * 固定右下角，顯示後端每分鐘爬取的盤中/盤後閒聊推文，並記錄使用者捲動到的已讀位置
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useAuth } from '../lib/AuthContext';
import {
  subscribeToPttPosts,
  getPttReadState,
  savePttReadState,
  getPttWindowSize,
  savePttWindowSize,
} from '../lib/firestoreApi';
import { getCurrentPttSession, getPttSessionDate } from '../lib/pttSession';
import { parsePttContent, extractImageUrls } from '../lib/pttContent';
import type { PttPush, PttSession } from '../types/pttChat';

const SETTINGS_DEBOUNCE_MS = 10000;
const DEFAULT_WIDTH_PX = 640;
const DEFAULT_HEIGHT_PX = 600;
const MIN_WIDTH_PX = 320;
const MIN_HEIGHT_PX = 256;

const SESSION_LABEL: Record<PttSession, string> = {
  intraday: '盤中閒聊',
  afterhours: '盤後閒聊',
};

const PUSH_TAG_COLOR: Record<string, string> = {
  '推': 'text-green-600 dark:text-green-400',
  '噓': 'text-red-600 dark:text-red-400',
  '→': 'text-gray-500 dark:text-gray-400',
};

export default function PttChatWidget() {
  const { user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [session, setSession] = useState<PttSession>(() => getCurrentPttSession());
  const [posts, setPosts] = useState<PttPush[]>([]);
  const [lastReadIndex, setLastReadIndex] = useState(-1);
  const [isReadStateLoaded, setIsReadStateLoaded] = useState(false);
  const [size, setSize] = useState({ width: DEFAULT_WIDTH_PX, height: DEFAULT_HEIGHT_PX });

  const listRef = useRef<HTMLDivElement>(null);
  // 每個 session_date 各自獨立的 debounce timer，避免切分頁時互相取消對方還沒觸發的寫入
  const writeTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const sizeWriteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasRestoredScrollRef = useRef(false);
  const dragStartRef = useRef({ mouseX: 0, mouseY: 0, width: 0, height: 0 });
  const observerRef = useRef<IntersectionObserver | null>(null);
  const maxVisibleIndexRef = useRef(-1);

  const dateStr = useMemo(() => getPttSessionDate(session), [session]);
  const uid = user?.uid;

  // 登入後讀取使用者上次調整過的視窗大小（clamp 回目前螢幕可視範圍，避免換裝置後過大/過小）
  useEffect(() => {
    if (!uid) return;

    getPttWindowSize(uid).then((saved) => {
      if (!saved) return;
      const maxWidth = window.innerWidth * 0.9;
      const maxHeight = window.innerHeight * 0.85;
      setSize({
        width: Math.min(maxWidth, Math.max(MIN_WIDTH_PX, saved.width)),
        height: Math.min(maxHeight, Math.max(MIN_HEIGHT_PX, saved.height)),
      });
    });
  }, [uid]);

  // 切換分頁時重新讀取該分頁的已讀位置，並重置捲動還原狀態與新訊息基準
  useEffect(() => {
    if (!uid) return;

    hasRestoredScrollRef.current = false;
    setLastReadIndex(-1);
    setIsReadStateLoaded(false);
    getPttReadState(uid, session, dateStr).then((index) => {
      setLastReadIndex(index);
      setIsReadStateLoaded(true);
    });
  }, [uid, session, dateStr]);

  // 訂閱目前分頁的即時訊息（收合時仍持續訂閱，維持未讀提醒正確）
  useEffect(() => {
    if (!uid) return;

    return subscribeToPttPosts(session, dateStr, setPosts);
  }, [uid, session, dateStr]);

  // 每次展開時，重新捲動到上次已讀位置（若無記錄則捲到最新）
  useEffect(() => {
    if (isOpen) {
      hasRestoredScrollRef.current = false;
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !isReadStateLoaded || hasRestoredScrollRef.current || posts.length === 0) return;

    const container = listRef.current;
    if (!container) return;

    const targetIndex = lastReadIndex >= 0 && lastReadIndex < posts.length ? lastReadIndex : posts.length - 1;
    const targetEl = container.querySelector<HTMLElement>(`[data-push-index="${targetIndex}"]`);
    const nextUnreadEl =
      targetIndex < posts.length - 1
        ? container.querySelector<HTMLElement>(`[data-push-index="${targetIndex + 1}"]`)
        : null;

    if (nextUnreadEl) {
      // 有新訊息時只露出下一則的一半，使用者要往下捲動看到完整內容才會更新讀取進度
      const containerRect = container.getBoundingClientRect();
      const nextRect = nextUnreadEl.getBoundingClientRect();
      const nextTopInContent = nextRect.top - containerRect.top + container.scrollTop;
      container.scrollTop = Math.max(0, nextTopInContent + nextRect.height / 2 - container.clientHeight);
    } else {
      targetEl?.scrollIntoView({ block: 'end' });
    }
    hasRestoredScrollRef.current = true;
  }, [isOpen, isReadStateLoaded, posts, lastReadIndex]);

  useEffect(() => {
    return () => {
      writeTimersRef.current.forEach((timer) => clearTimeout(timer));
      writeTimersRef.current.clear();
      if (sizeWriteTimerRef.current) {
        clearTimeout(sizeWriteTimerRef.current);
      }
    };
  }, []);

  const persistReadIndex = useCallback((index: number) => {
    if (!uid) return;

    const key = `${session}_${dateStr}`;
    const existingTimer = writeTimersRef.current.get(key);
    if (existingTimer) {
      clearTimeout(existingTimer);
    }
    const timer = setTimeout(() => {
      savePttReadState(uid, session, dateStr, index);
      writeTimersRef.current.delete(key);
    }, SETTINGS_DEBOUNCE_MS);
    writeTimersRef.current.set(key, timer);
  }, [uid, session, dateStr]);

  const persistSize = useCallback((width: number, height: number) => {
    if (!uid) return;

    if (sizeWriteTimerRef.current) {
      clearTimeout(sizeWriteTimerRef.current);
    }
    sizeWriteTimerRef.current = setTimeout(() => {
      savePttWindowSize(uid, width, height);
    }, SETTINGS_DEBOUNCE_MS);
  }, [uid]);

  // 建立 IntersectionObserver 被動追蹤已捲動到的訊息，避免每次 scroll 事件都量測所有元素位置造成卡頓
  useEffect(() => {
    const container = listRef.current;
    if (!isOpen || !container) return;

    maxVisibleIndexRef.current = -1;

    const observer = new IntersectionObserver(
      (entries) => {
        let hasNewVisible = false;
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const index = Number((entry.target as HTMLElement).dataset.pushIndex);
          if (index > maxVisibleIndexRef.current) {
            maxVisibleIndexRef.current = index;
            hasNewVisible = true;
          }
        });

        if (hasNewVisible) {
          const index = maxVisibleIndexRef.current;
          setLastReadIndex((prev) => (index > prev ? index : prev));
          persistReadIndex(index);
        }
      },
      { root: container }
    );

    observerRef.current = observer;

    return () => {
      observer.disconnect();
      observerRef.current = null;
    };
  }, [isOpen, persistReadIndex]);

  // 訊息列表變化時，把目前所有推文元素交給 observer 觀察（對已觀察的元素是安全的 no-op）
  useEffect(() => {
    const container = listRef.current;
    const observer = observerRef.current;
    if (!isOpen || !container || !observer) return;

    container.querySelectorAll<HTMLElement>('[data-push-index]').forEach((item) => {
      observer.observe(item);
    });
  }, [isOpen, posts.length]);

  // 視窗固定在右下角，左上角把手往外拖會變大（維持右下角貼齊畫面角落）
  const handleResizeMouseDown = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    dragStartRef.current = { mouseX: event.clientX, mouseY: event.clientY, width: size.width, height: size.height };

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const { mouseX, mouseY, width, height } = dragStartRef.current;
      const deltaX = mouseX - moveEvent.clientX;
      const deltaY = mouseY - moveEvent.clientY;
      const maxWidth = window.innerWidth * 0.9;
      const maxHeight = window.innerHeight * 0.85;
      const nextWidth = Math.min(maxWidth, Math.max(MIN_WIDTH_PX, width + deltaX));
      const nextHeight = Math.min(maxHeight, Math.max(MIN_HEIGHT_PX, height + deltaY));

      setSize({ width: nextWidth, height: nextHeight });
      persistSize(nextWidth, nextHeight);
    };

    const handleMouseUp = () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  }, [size, persistSize]);

  if (!uid) return null;

  const hasUnread = posts.length > 0 && lastReadIndex < posts.length - 1;

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        aria-label="展開 PTT 閒聊"
        className="fixed bottom-4 right-4 z-50 flex h-16 w-16 items-center justify-center rounded-full bg-white dark:bg-gray-800 shadow-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
      >
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        {hasUnread && (
          <span
            data-testid="unread-indicator"
            className="absolute top-1.5 right-1.5 h-4 w-4 rounded-full bg-red-500 border-2 border-white dark:border-gray-800"
          />
        )}
      </button>
    );
  }

  return (
    <div
      data-testid="ptt-widget-panel"
      style={{ width: size.width, height: size.height }}
      className="fixed bottom-4 right-4 z-50 flex flex-col bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <div
        data-testid="ptt-resize-handle"
        onMouseDown={handleResizeMouseDown}
        aria-hidden="true"
        className="absolute top-0 left-0 w-4 h-4 cursor-nwse-resize rounded-br-lg bg-gray-300 dark:bg-gray-600 hover:bg-gray-400 dark:hover:bg-gray-500 transition-colors z-10"
      />
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-700">
        <div className="flex gap-1">
          {(Object.keys(SESSION_LABEL) as PttSession[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setSession(key)}
              className={`px-2 py-1 text-base rounded-md transition-colors ${
                session === key
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
              }`}
            >
              {SESSION_LABEL[key]}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setIsOpen(false)}
          aria-label="收合 PTT 閒聊"
          className="p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
          </svg>
        </button>
      </div>

      <div ref={listRef} data-testid="ptt-message-list" className="flex-1 overflow-y-auto px-3 py-2 space-y-1 text-base">
        {posts.length === 0 ? (
          <p className="text-gray-400 dark:text-gray-500 text-center mt-8">尚無訊息</p>
        ) : (
          posts.map((push, index) => {
            const imageUrls = extractImageUrls(push.content);
            return (
              <p key={index} data-push-index={index} className="leading-snug break-words">
                <span className={`font-medium ${PUSH_TAG_COLOR[push.push_tag] ?? 'text-gray-400'}`}>
                  {push.push_tag}
                </span>{' '}
                <span className="font-medium text-gray-700 dark:text-gray-300">{push.userid}:</span>{' '}
                <span className="text-gray-600 dark:text-gray-400">
                  {parsePttContent(push.content).map((segment, segmentIndex) =>
                    segment.type === 'link' ? (
                      <a
                        key={segmentIndex}
                        href={segment.value}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 dark:text-blue-400 underline break-all"
                      >
                        {segment.value}
                      </a>
                    ) : (
                      <span key={segmentIndex}>{segment.value}</span>
                    )
                  )}
                </span>
                <span className="float-right ml-2 text-sm text-gray-400 dark:text-gray-500">{push.time}</span>
                {imageUrls.length > 0 && (
                  <span className="block mt-1">
                    {imageUrls.map((url, urlIndex) => (
                      <a key={urlIndex} href={url} target="_blank" rel="noopener noreferrer">
                        <img
                          src={url}
                          alt="推文圖片"
                          loading="lazy"
                          className="max-w-full max-h-80 rounded border border-gray-200 dark:border-gray-700 mr-1 mb-1 inline-block align-top"
                          onError={(event) => {
                            event.currentTarget.style.display = 'none';
                          }}
                        />
                      </a>
                    ))}
                  </span>
                )}
              </p>
            );
          })
        )}
      </div>
    </div>
  );
}
