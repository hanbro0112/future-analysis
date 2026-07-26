/**
 * Firebase 配置與初始化
 */
import { initializeApp, getApps } from 'firebase/app';
import { getFirestore, connectFirestoreEmulator } from 'firebase/firestore';
import { getStorage, connectStorageEmulator } from 'firebase/storage';
import { getAuth, connectAuthEmulator, GoogleAuthProvider } from 'firebase/auth';

// Firebase 配置（使用環境變數或預設值）
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || 'demo-key',
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || 'demo-project.firebaseapp.com',
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || 'demo-project',
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || 'demo-project.firebasestorage.app',
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || '123456789',
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID || '1:123456789:web:abcdef'
};

// 初始化 Firebase（避免重複初始化）
const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];

// 初始化 Firestore
export const db = getFirestore(app);

// 初始化 Storage
export const storage = getStorage(app);

// 初始化 Auth
export const auth = getAuth(app);

// Google 登入 Provider
export const googleAuthProvider = new GoogleAuthProvider();

// 連接到 emulator（僅在瀏覽器環境且設定為 true）
let firestoreEmulatorConnected = false;
let storageEmulatorConnected = false;
let authEmulatorConnected = false;

if (typeof window !== 'undefined' && process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATOR === 'true') {
  // Firestore Emulator
  if (!firestoreEmulatorConnected) {
    try {
      connectFirestoreEmulator(db, 'localhost', 8080);
      firestoreEmulatorConnected = true;
      console.log('🔧 已連接到 Firestore Emulator');
    } catch (error) {
      console.warn('⚠️ Firestore Emulator 連接失敗（可能已連接）');
    }
  }
  
  // Storage Emulator
  if (!storageEmulatorConnected) {
    try {
      connectStorageEmulator(storage, 'localhost', 9199);
      storageEmulatorConnected = true;
      console.log('🔧 已連接到 Storage Emulator');
    } catch (error) {
      console.warn('⚠️ Storage Emulator 連接失敗（可能已連接）');
    }
  }

  // Auth Emulator
  if (!authEmulatorConnected) {
    try {
      connectAuthEmulator(auth, 'http://localhost:9099', { disableWarnings: true });
      authEmulatorConnected = true;
      console.log('🔧 已連接到 Auth Emulator');
    } catch (error) {
      console.warn('⚠️ Auth Emulator 連接失敗（可能已連接）');
    }
  }
}
