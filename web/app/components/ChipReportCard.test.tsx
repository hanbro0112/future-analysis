import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import ChipReportCard, {
  getChipReportDate,
  getDateOffsetTradingDays,
  formatDateToYYYYMMDD,
} from './ChipReportCard';

const mockGetDownloadURL = jest.fn((ref: { path: string }) =>
  Promise.resolve(`https://example.com/${ref.path}`)
);

jest.mock('firebase/storage', () => ({
  ref: (_storage: unknown, path: string) => ({ path }),
  getDownloadURL: (ref: { path: string }) => mockGetDownloadURL(ref),
}));

jest.mock('../lib/firebase', () => ({
  storage: {},
}));

// 每個測試使用獨立的 SWR 快取，避免跨測試互相污染
const renderCard = () =>
  render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <ChipReportCard />
    </SWRConfig>
  );

describe('getDateOffsetTradingDays', () => {
  it('往前推算會略過週六、週日', () => {
    const wednesday = new Date(2026, 0, 14); // 2026/01/14 為週三

    expect(formatDateToYYYYMMDD(getDateOffsetTradingDays(wednesday, 0))).toBe('20260114');
    expect(formatDateToYYYYMMDD(getDateOffsetTradingDays(wednesday, 1))).toBe('20260113'); // 週二
    expect(formatDateToYYYYMMDD(getDateOffsetTradingDays(wednesday, 2))).toBe('20260112'); // 週一
    expect(formatDateToYYYYMMDD(getDateOffsetTradingDays(wednesday, 3))).toBe('20260109'); // 略過週末，回到上週五
  });
});

describe('getChipReportDate', () => {
  it('15:21 前顯示前一交易日', () => {
    const before = new Date(2026, 0, 14, 15, 20); // 週三 15:20
    expect(formatDateToYYYYMMDD(getChipReportDate(before))).toBe('20260113');
  });

  it('15:21 後顯示當日', () => {
    const after = new Date(2026, 0, 14, 15, 21); // 週三 15:21
    expect(formatDateToYYYYMMDD(getChipReportDate(after))).toBe('20260114');
  });

  it('週一 15:21 前應顯示上週五（略過週末）', () => {
    const mondayMorning = new Date(2026, 0, 12, 8, 0); // 週一 08:00
    expect(formatDateToYYYYMMDD(getChipReportDate(mondayMorning))).toBe('20260109');
  });
});

describe('ChipReportCard', () => {
  beforeEach(() => {
    mockGetDownloadURL.mockClear();
  });

  it('切換到前一交易日後再切回，已快取的日期不會重新發送請求', async () => {
    renderCard();

    // 等待初始日期的圖片載入完成
    await waitFor(() => expect(screen.getByAltText('小台散戶多空比')).toBeInTheDocument());
    const initialCallCount = mockGetDownloadURL.mock.calls.length;
    expect(initialCallCount).toBe(2); // MTX + TMF

    // 切到前一交易日：應該重新發送請求
    fireEvent.click(screen.getByLabelText('切換至前一交易日'));
    await waitFor(() => expect(mockGetDownloadURL.mock.calls.length).toBe(initialCallCount + 2));

    // 切回原本的日期：已經快取過，不應該再打一次 API
    fireEvent.click(screen.getByLabelText('切換至下一交易日'));
    await waitFor(() => expect(screen.getByAltText('小台散戶多空比')).toBeInTheDocument());
    expect(mockGetDownloadURL.mock.calls.length).toBe(initialCallCount + 2);
  });

  it('最多只能往前切換兩個交易日', async () => {
    renderCard();
    await waitFor(() => expect(screen.getByAltText('小台散戶多空比')).toBeInTheDocument());

    const prevButton = screen.getByLabelText('切換至前一交易日');
    fireEvent.click(prevButton);
    await waitFor(() => expect(prevButton).not.toBeDisabled());
    fireEvent.click(prevButton);

    await waitFor(() => expect(prevButton).toBeDisabled());
  });

  it('在最新交易日時，下一交易日按鈕為 disabled', async () => {
    renderCard();
    await waitFor(() => expect(screen.getByAltText('小台散戶多空比')).toBeInTheDocument());

    expect(screen.getByLabelText('切換至下一交易日')).toBeDisabled();
  });

  it('停在舊日期時按手動更新，會強制重抓今天的資料並跳回今天', async () => {
    renderCard();
    await waitFor(() => expect(screen.getByAltText('小台散戶多空比')).toBeInTheDocument());
    const initialCallCount = mockGetDownloadURL.mock.calls.length;
    expect(initialCallCount).toBe(2); // 今天的 MTX + TMF

    // 切到前一交易日（已快取今天的資料）
    fireEvent.click(screen.getByLabelText('切換至前一交易日'));
    await waitFor(() => expect(mockGetDownloadURL.mock.calls.length).toBe(initialCallCount + 2));

    // 在舊日期按下手動更新：應該強制重抓「今天」，而不是重抓目前畫面上的舊日期
    fireEvent.click(screen.getByLabelText('手動更新籌碼報告'));

    await waitFor(() => expect(mockGetDownloadURL.mock.calls.length).toBe(initialCallCount + 4));
    // 應該跳回今天，且下一交易日按鈕重新變回 disabled
    await waitFor(() => expect(screen.getByLabelText('切換至下一交易日')).toBeDisabled());

    const refetchedPaths = mockGetDownloadURL.mock.calls.slice(-2).map(([ref]) => ref.path);
    expect(refetchedPaths.every((path) => path.includes(formatDateToYYYYMMDD(getChipReportDate())))).toBe(true);
  });
});
