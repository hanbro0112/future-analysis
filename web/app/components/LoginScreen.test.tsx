import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LoginScreen from './LoginScreen';
import { useAuth } from '../lib/AuthContext';

jest.mock('../lib/AuthContext', () => ({
  useAuth: jest.fn(),
}));

const mockUseAuth = useAuth as jest.Mock;

describe('LoginScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('點擊按鈕會呼叫 signInWithGoogle', async () => {
    const signInWithGoogle = jest.fn().mockResolvedValue(undefined);
    mockUseAuth.mockReturnValue({ signInWithGoogle, error: null });

    render(<LoginScreen />);
    fireEvent.click(screen.getByRole('button', { name: /使用 Google 登入/ }));

    await waitFor(() => {
      expect(signInWithGoogle).toHaveBeenCalledTimes(1);
    });
  });

  it('登入失敗時顯示錯誤訊息', () => {
    mockUseAuth.mockReturnValue({
      signInWithGoogle: jest.fn(),
      error: '登入失敗，請再試一次',
    });

    render(<LoginScreen />);

    expect(screen.getByText('登入失敗，請再試一次')).toBeInTheDocument();
  });
});
