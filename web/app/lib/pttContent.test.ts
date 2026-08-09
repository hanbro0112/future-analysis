import { parsePttContent, isImageUrl, extractImageUrls } from './pttContent';

describe('parsePttContent', () => {
  it('沒有連結時回傳單一文字片段', () => {
    expect(parsePttContent('大家早安！')).toEqual([{ type: 'text', value: '大家早安！' }]);
  });

  it('文字中間夾雜連結時，依序拆成文字/連結片段', () => {
    const result = parsePttContent('看這個 https://i.imgur.com/abc123.jpg 笑死');

    expect(result).toEqual([
      { type: 'text', value: '看這個 ' },
      { type: 'link', value: 'https://i.imgur.com/abc123.jpg' },
      { type: 'text', value: ' 笑死' },
    ]);
  });

  it('整則內容都是連結時不會有多餘的空文字片段', () => {
    const result = parsePttContent('https://i.imgur.com/abc123.jpg');

    expect(result).toEqual([{ type: 'link', value: 'https://i.imgur.com/abc123.jpg' }]);
  });

  it('可以處理多個連結', () => {
    const result = parsePttContent('https://a.com/1.png https://b.com/2.gif');

    expect(result).toEqual([
      { type: 'link', value: 'https://a.com/1.png' },
      { type: 'text', value: ' ' },
      { type: 'link', value: 'https://b.com/2.gif' },
    ]);
  });
});

describe('isImageUrl', () => {
  it.each(['https://i.imgur.com/abc123.jpg', 'https://i.imgur.com/abc123.jpeg', 'https://i.imgur.com/abc123.png', 'https://i.imgur.com/abc123.gif', 'https://i.imgur.com/abc123.webp', 'https://i.imgur.com/abc123.JPG'])(
    '%s 應判定為圖片連結',
    (url) => {
      expect(isImageUrl(url)).toBe(true);
    }
  );

  it('副檔名後面帶 query string 仍判定為圖片連結', () => {
    expect(isImageUrl('https://i.imgur.com/abc123.jpg?a=1')).toBe(true);
  });

  it('沒有副檔名的短網址不判定為圖片連結', () => {
    expect(isImageUrl('https://imgur.com/abc123')).toBe(false);
  });

  it('一般網頁連結不判定為圖片連結', () => {
    expect(isImageUrl('https://www.ptt.cc/bbs/Stock/index.html')).toBe(false);
  });
});

describe('extractImageUrls', () => {
  it('抽出內容中所有圖片連結，忽略非圖片連結', () => {
    const content = '兩張圖 https://i.imgur.com/1.jpg https://imgur.com/2 https://i.imgur.com/3.gif';

    expect(extractImageUrls(content)).toEqual(['https://i.imgur.com/1.jpg', 'https://i.imgur.com/3.gif']);
  });

  it('沒有圖片連結時回傳空陣列', () => {
    expect(extractImageUrls('沒有連結的推文')).toEqual([]);
  });
});
