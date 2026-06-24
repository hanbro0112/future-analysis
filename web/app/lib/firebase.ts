/**
 * Firebase 配置與初始化
 */
import { initializeApp, getApps } from 'firebase/app';
import { getFirestore, connectFirestoreEmulator } from 'firebase/firestore';

// Firebase 配置（使用環境變數或預設值）
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || 'demo-key',
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || 'demo-project.firebaseapp.com',
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || 'demo-project',
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || 'demo-project.appspot.com',
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || '123456789',
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID || '1:123456789:web:abcdef'
};

// 初始化 Firebase（避免重複初始化）
const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];

// 初始化 Firestore
export const db = getFirestore(app);

// 連接到 emulator（僅在瀏覽器環境且設定為 true）
let emulatorConnected = false;
if (
  typeof window !== 'undefined' && 
  process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATOR === 'true' &&
  !emulatorConnected
) {
  try {
    connectFirestoreEmulator(db, 'localhost', 8080);
    emulatorConnected = true;
    console.log('🔧 已連接到 Firestore Emulator');
  } catch (error) {
    console.warn('⚠️ Firestore Emulator 連接失敗（可能已連接）');
  }
}
