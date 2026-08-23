import { render, screen, within } from '@testing-library/react';
import QuoteCard from './QuoteCard';
import type { AnalysisResult } from '../types/minuteData';

const baseAnalysis: AnalysisResult = {
  signal: '中性',
  long_ratio: 50,
  short_ratio: 50,
  confidence: 80,
  volume_explosion_level: '正常',
  sentiment_label: '一般',
  sentiment_score: 50,
  basis: 15,
  basis_pct: 0.07,
  volatility: 0,
};

describe('QuoteCard', () => {
  it('期現價差數值後以括弧顯示價差信號', () => {
    render(
      <QuoteCard
        quote={null}
        realtimePrice={{ code: 'MXFF6', price: 21815, underlying_price: 21800, volume: 5 }}
        referencePrice={21800}
        analysis={{ ...baseAnalysis, volatility: 30 }}
      />
    );

    expect(screen.getByText('+15 (正價差)')).toBeInTheDocument();
  });

  it('波動率 >= 50% 顯示「低買高賣」', () => {
    render(
      <QuoteCard
        quote={null}
        realtimePrice={{ code: 'MXFF6', price: 21815, underlying_price: 21800, volume: 5 }}
        referencePrice={21800}
        analysis={{ ...baseAnalysis, volatility: 72 }}
      />
    );

    expect(screen.getByText('72% (低買高賣)')).toBeInTheDocument();
  });

  it('波動率 < 50% 顯示「順勢」', () => {
    render(
      <QuoteCard
        quote={null}
        realtimePrice={{ code: 'MXFF6', price: 21815, underlying_price: 21800, volume: 5 }}
        referencePrice={21800}
        analysis={{ ...baseAnalysis, volatility: 20 }}
      />
    );

    expect(screen.getByText('20% (順勢)')).toBeInTheDocument();
  });

  it('每個指標小標都附有說明計算方式的懸停提示', () => {
    render(
      <QuoteCard
        quote={null}
        realtimePrice={{ code: 'MXFF6', price: 21815, underlying_price: 21800, volume: 5 }}
        referencePrice={21800}
        analysis={{ ...baseAnalysis, volatility: 30 }}
      />
    );

    const tooltips = screen.getAllByRole('tooltip');
    const tooltipTexts = tooltips.map((el) => el.textContent);

    expect(tooltipTexts.some((text) => text?.includes('1分鐘(25%)'))).toBe(true);
    expect(tooltipTexts.some((text) => text?.includes('委買委賣比(30%)'))).toBe(true);
    expect(tooltipTexts.some((text) => text?.includes('爆量比率'))).toBe(true);
    expect(tooltipTexts.some((text) => text?.includes('期貨價格'))).toBe(true);
    expect(tooltipTexts.some((text) => text?.includes('路徑效率比'))).toBe(true);
  });

  it('懸停提示以用途、公式、分級門檻分段排版，而非單一長段落', () => {
    render(
      <QuoteCard
        quote={null}
        realtimePrice={{ code: 'MXFF6', price: 21815, underlying_price: 21800, volume: 5 }}
        referencePrice={21800}
        analysis={{ ...baseAnalysis, volatility: 30 }}
      />
    );

    const signalTooltip = screen.getByText('綜合多空比判斷').closest('[role="tooltip"]');
    expect(signalTooltip).not.toBeNull();

    const { getAllByRole, getByText } = within(signalTooltip as HTMLElement);
    // 分級門檻應以清單項目呈現，而非塞在同一段文字裡
    const levelItems = getAllByRole('listitem');
    expect(levelItems.length).toBe(5);
    expect(levelItems[0]).toHaveTextContent('強多');
    // 公式與用途分別成段
    expect(getByText(/加權：1分鐘\(25%\)/)).toBeInTheDocument();
  });
});
