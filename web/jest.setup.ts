import '@testing-library/jest-dom';

// jsdom 未實作 scrollIntoView，補上空實作避免呼叫時噴錯
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = jest.fn();
}

// jsdom 未實作 IntersectionObserver，補上最小假實作避免呼叫時噴錯
if (typeof global !== 'undefined' && !('IntersectionObserver' in global)) {
  class FakeIntersectionObserver implements IntersectionObserver {
    readonly root: Element | Document | null = null;
    readonly rootMargin: string = '';
    readonly thresholds: ReadonlyArray<number> = [];
    observe = jest.fn();
    unobserve = jest.fn();
    disconnect = jest.fn();
    takeRecords = jest.fn(() => []);
  }

  // @ts-expect-error 測試用假的 IntersectionObserver 實作，型別不需完全對齊瀏覽器原生 API
  global.IntersectionObserver = FakeIntersectionObserver;
}
