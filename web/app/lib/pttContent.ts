/**
 * PTT 推文內容解析：抽出連結、判斷圖片/GIF 連結
 */

const URL_REGEX = /https?:\/\/[^\s]+/g;
const IMAGE_EXTENSION_REGEX = /\.(jpe?g|png|gif|webp)(\?\S*)?$/i;

export interface PttContentSegment {
  type: 'text' | 'link';
  value: string;
}

/**
 * 把推文內容拆成純文字與連結片段，依原始順序排列
 * @param content 推文內容
 */
export function parsePttContent(content: string): PttContentSegment[] {
  const segments: PttContentSegment[] = [];
  let lastIndex = 0;

  for (const match of content.matchAll(URL_REGEX)) {
    const url = match[0];
    const index = match.index ?? 0;

    if (index > lastIndex) {
      segments.push({ type: 'text', value: content.slice(lastIndex, index) });
    }
    segments.push({ type: 'link', value: url });
    lastIndex = index + url.length;
  }

  if (lastIndex < content.length) {
    segments.push({ type: 'text', value: content.slice(lastIndex) });
  }

  return segments;
}

/**
 * 判斷網址是否為圖片/GIF 直連（副檔名判斷，短網址如 imgur.com/xxx 不會被判定為圖片）
 * @param url 網址
 */
export function isImageUrl(url: string): boolean {
  return IMAGE_EXTENSION_REGEX.test(url);
}

/**
 * 從推文內容抽出所有圖片/GIF 直連網址
 * @param content 推文內容
 */
export function extractImageUrls(content: string): string[] {
  return Array.from(content.matchAll(URL_REGEX), (match) => match[0]).filter(isImageUrl);
}
