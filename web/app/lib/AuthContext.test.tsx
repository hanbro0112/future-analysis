import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';

const mockOnAuthStateChanged = jest.fn();
const mockSignInWithPopup = jest.fn();
const mockSignOut = jest.fn();

jest.mock('firebase/auth', () => ({
  onAuthStateChanged: (...args: unknown[]) => mockOnAuthStateChanged(...args),
  signInWithPopup: (...args: unknown[]) => mockSignInWithPopup(...args),
  signOut: (...args: unknown[]) => mockSignOut(...args),
  GoogleAuthProvider: jest.fn(),
  getAuth: jest.fn(() => ({})),
  connectAuthEmulator: jest.fn(),
}));

jest.mock('./firebase', () => ({
  auth: {},
  googleAuthProvider: {},
}));

function TestConsumer() {
  const { user, loading, signInWithGoogle, signOut } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="user">{user ? user.uid : 'none'}</span>
      <button onClick={() => signInWithGoogle()}>登入</button>
      <button onClick={() => signOut()}>登出</button>
    </div>
  );
}

describe('AuthContext', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('初始為 loading，收到 onAuthStateChanged 後更新 user', async () => {
    let authCallback: (user: unknown) => void = () => {};
    mockOnAuthStateChanged.mockImplementation((_auth, callback) => {
      authCallback = callback;
      return jest.fn();
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    expect(screen.getByTestId('loading').textContent).toBe('true');

    act(() => {
      authCallback({ uid: 'user-123' });
    });

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('user').textContent).toBe('user-123');
  });

  it('signInWithGoogle 會呼叫 signInWithPopup', async () => {
    mockOnAuthStateChanged.mockImplementation((_auth, callback) => {
      callback(null);
      return jest.fn();
    });
    mockSignInWithPopup.mockResolvedValue(undefined);

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    fireEvent.click(screen.getByText('登入'));

    await waitFor(() => {
      expect(mockSignInWithPopup).toHaveBeenCalledTimes(1);
    });
  });

  it('signOut 會呼叫 firebase signOut', async () => {
    mockOnAuthStateChanged.mockImplementation((_auth, callback) => {
      callback(null);
      return jest.fn();
    });
    mockSignOut.mockResolvedValue(undefined);

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    fireEvent.click(screen.getByText('登出'));

    await waitFor(() => {
      expect(mockSignOut).toHaveBeenCalledTimes(1);
    });
  });
});
