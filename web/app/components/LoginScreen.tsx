'use client';

/**
 * 登入畫面
 * 未登入時顯示，提供 Google 登入
 */

import { useState, type ReactNode } from 'react';
import { useAuth } from '../lib/AuthContext';

interface Feature {
  title: string;
  description: string;
  icon: ReactNode;
}

interface FeatureColors {
  bg: string;
  text: string;
}

const FEATURES: (Feature & { colors: FeatureColors })[] = [
  {
    title: '即時報價',
    description: '台指期分鐘級走勢即時更新',
    icon: (
      <path d="M3 12h4l2 6 4-14 2 8h6" />
    ),
    colors: { bg: 'bg-emerald-50 dark:bg-emerald-500/10', text: 'text-emerald-600 dark:text-emerald-400' },
  },
  {
    title: '多空分析',
    description: '自動產生每日多空情勢報告',
    icon: (
      <>
        <line x1="6" y1="20" x2="6" y2="12" />
        <line x1="12" y1="20" x2="12" y2="6" />
        <line x1="18" y1="20" x2="18" y2="10" />
      </>
    ),
    colors: { bg: 'bg-amber-50 dark:bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400' },
  },
  {
    title: '籌碼動向',
    description: '三大法人籌碼變化一次掌握',
    icon: (
      <>
        <path d="M12 3 3 8l9 5 9-5-9-5Z" />
        <path d="M3 16l9 5 9-5" />
        <path d="M3 12l9 5 9-5" />
      </>
    ),
    colors: { bg: 'bg-rose-50 dark:bg-rose-500/10', text: 'text-rose-600 dark:text-rose-400' },
  },
];

export default function LoginScreen() {
  const { signInWithGoogle, error } = useAuth();
  const [isSigningIn, setIsSigningIn] = useState(false);

  const handleSignIn = async () => {
    setIsSigningIn(true);
    try {
      await signInWithGoogle();
    } catch {
      // 錯誤訊息已透過 useAuth().error 呈現
    } finally {
      setIsSigningIn(false);
    }
  };

  return (
    <div className="flex min-h-screen w-full">
      {/* 左側：期貨風格插圖（手機隱藏，桌面顯示） */}
      {/* 圖片為橫幅構圖，面板多為直式比例，改用 object-contain 並以同色背景鋪底，避免左右內容被裁切 */}
      <div className="relative hidden items-center justify-center overflow-hidden bg-[#f5f4f0] md:flex md:w-[46%] lg:w-[54%]">
        <img
          src="/images/login-hero.jpg"
          alt=""
          className="h-full w-full object-contain"
        />
      </div>

      {/* 右側：登入視窗，佔滿右半版面 */}
      <div className="relative flex-1 bg-white dark:bg-gray-900">
        {/* 斜線交界：疊在左側圖片右緣，製造右上左下的斜切效果 */}
        <div
          className="absolute inset-y-0 -left-[220px] hidden w-[220px] bg-white dark:bg-gray-900 md:block [clip-path:polygon(100%_0,100%_100%,0_100%)]"
          aria-hidden="true"
        />

        <div className="relative grid h-full grid-rows-[1fr_auto] px-8 py-10 sm:px-16 lg:px-20">
          {/* 中央登入區塊 */}
          <div className="flex items-center justify-center">
            <div className="w-full max-w-sm">
              <span className="mb-4 inline-block h-1 w-10 rounded-full bg-gradient-to-r from-blue-500 via-emerald-500 to-amber-500" />
              <h1 className="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">
                歡迎回來
              </h1>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                請登入以檢視即時報價與分析資料
              </p>

              <ul className="mt-8 space-y-1">
                {FEATURES.map((feature) => (
                  <li
                    key={feature.title}
                    className="flex items-start gap-3 rounded-xl p-2 -mx-2 transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/60"
                  >
                    <div
                      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${feature.colors.bg}`}
                    >
                      <svg
                        className={`h-5 w-5 ${feature.colors.text}`}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        {feature.icon}
                      </svg>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-100">
                        {feature.title}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {feature.description}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>

              <div className="my-8 h-px bg-gradient-to-r from-transparent via-gray-200 to-transparent dark:via-gray-700" />

              <button
                onClick={handleSignIn}
                disabled={isSigningIn}
                className="flex w-full items-center justify-center gap-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 shadow-sm transition-all hover:bg-gray-50 hover:shadow-md dark:hover:bg-gray-700 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100"
              >
                <svg className="h-5 w-5" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M23.49 12.27c0-.79-.07-1.54-.19-2.27H12v4.51h6.47a5.54 5.54 0 01-2.4 3.63v3h3.87c2.26-2.09 3.55-5.17 3.55-8.87z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 24c3.24 0 5.95-1.08 7.94-2.92l-3.87-3c-1.08.72-2.45 1.15-4.07 1.15-3.13 0-5.78-2.11-6.73-4.96H1.28v3.11A11.997 11.997 0 0012 24z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.27 14.27a7.2 7.2 0 010-4.54v-3.1H1.28a12 12 0 000 10.75l3.99-3.11z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 4.75c1.76 0 3.35.6 4.6 1.8l3.42-3.42C17.94 1.19 15.24 0 12 0 7.31 0 3.26 2.69 1.28 6.63l3.99 3.1c.95-2.85 3.6-4.98 6.73-4.98z"
                  />
                </svg>
                {isSigningIn ? '登入中...' : '使用 Google 登入'}
              </button>

              {error && (
                <p className="mt-4 text-sm text-red-500">{error}</p>
              )}
            </div>
          </div>

          {/* 底部說明 */}
          <p className="text-center text-xs text-gray-400 dark:text-gray-500">
            台指期 · 即時報價與多空分析
          </p>
        </div>
      </div>
    </div>
  );
}
