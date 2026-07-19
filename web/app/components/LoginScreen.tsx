'use client';

/**
 * 登入畫面
 * 未登入時顯示，提供 Google 登入
 */

import { useState } from 'react';
import { useAuth } from '../lib/AuthContext';

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
    <div className="flex flex-1 items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-8 text-center shadow-sm">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
          期貨資訊分析
        </h1>
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
          請登入以檢視即時報價與分析資料
        </p>

        <button
          onClick={handleSignIn}
          disabled={isSigningIn}
          className="mt-6 flex w-full items-center justify-center gap-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
  );
}
