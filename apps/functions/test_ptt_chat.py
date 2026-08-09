"""
測試 PTT 閒聊爬蟲的解析與增量游標邏輯
"""
from datetime import datetime

import pytest
import requests
from google.cloud import firestore

import ptt_chat
from ptt_chat import PttChatCrawler

BOARD_INDEX_HTML = """
<html><body>
<div class="r-ent">
  <div class="title"><a href="/bbs/Stock/M.1111111111.A.111.html">[新聞] 隨便一篇新聞</a></div>
</div>
<div class="r-ent">
  <div class="title"><a href="/bbs/Stock/M.1785976206.A.458.html">[閒聊] 2026/08/06 盤中閒聊</a></div>
</div>
<div class="r-ent">
  <div class="title">(本文已被刪除)</div>
</div>
</body></html>
"""

def _board_page_html(article_title: str | None, article_href: str | None, prev_href: str | None) -> str:
    """組出一頁板面 HTML，可選擇是否含有目標文章、以及「上頁」（較舊一頁）連結"""
    entry_html = ""
    if article_title:
        entry_html = f'<div class="r-ent"><div class="title"><a href="{article_href}">{article_title}</a></div></div>'

    prev_link_html = (
        f'<a class="btn wide" href="{prev_href}">‹ 上頁</a>'
        if prev_href
        else '<a class="btn wide disabled">‹ 上頁</a>'
    )

    return f"""
    <html><body>
    {entry_html}
    <div class="btn-group-paging">
      <a class="btn wide" href="/bbs/Stock/index1.html">最舊</a>
      {prev_link_html}
      <a class="btn wide disabled">下頁 ›</a>
      <a class="btn wide" href="/bbs/Stock/index.html">最新</a>
    </div>
    </body></html>
    """


ARTICLE_HTML = """
<html><body>
<div id="main-content">
  <div class="push"><span class="push-tag">推 </span><span class="push-userid">ruwjo12</span><span class="push-content">: 大家早安！</span><span class="push-ipdatetime"> 08/06 08:30</span></div>
  <div class="push"><span class="push-tag">推 </span><span class="push-userid">davie11333</span><span class="push-content">: 早安大爆崩</span><span class="push-ipdatetime"> 08/06 08:30</span></div>
  <div class="push center warning-box">檔案過大！部分文章無法顯示</div>
  <div class="push"><span class="f1 hl push-tag">→ </span><span class="push-userid">james5271</span><span class="push-content">: 被動要V了嗎</span><span class="push-ipdatetime"> 08/06 10:20</span></div>
</div>
</body></html>
"""


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class FakeDocSnapshot:
    def __init__(self, exists: bool, data: dict | None = None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return self._data


class FakeFirestoreWriter:
    """duck-typed 假 FirestoreWriter，不連線真的 Firestore"""

    def __init__(self, thread_snapshot: FakeDocSnapshot):
        self._thread_snapshot = thread_snapshot
        self.write_calls: list[dict] = []

    @property
    def db(self):
        writer = self

        class _DocRef:
            def get(self_inner):
                return writer._thread_snapshot

        class _Collection:
            def document(self_inner, doc_id):
                return _DocRef()

        class _Db:
            def collection(self_inner, name):
                return _Collection()

        return _Db()

    def write_document(self, collection, document_id, data, merge=False):
        self.write_calls.append(
            {"collection": collection, "document_id": document_id, "data": data, "merge": merge}
        )


@pytest.fixture
def crawler() -> PttChatCrawler:
    return PttChatCrawler(FakeFirestoreWriter(FakeDocSnapshot(exists=False)))


def test_resolve_current_session_before_close_is_intraday(crawler: PttChatCrawler):
    # 2026-08-06 為週四
    assert crawler.resolve_current_session(datetime(2026, 8, 6, 10, 0)) == "intraday"
    assert crawler.resolve_current_session(datetime(2026, 8, 6, 13, 30)) == "intraday"


def test_resolve_current_session_after_close_is_afterhours(crawler: PttChatCrawler):
    assert crawler.resolve_current_session(datetime(2026, 8, 6, 14, 0)) == "afterhours"
    assert crawler.resolve_current_session(datetime(2026, 8, 6, 20, 0)) == "afterhours"


def test_resolve_current_session_early_morning_is_afterhours(crawler: PttChatCrawler):
    """凌晨（00:00-08:29）延續前一天的盤後閒聊，因為當天盤中閒聊還沒發文"""
    # 2026-08-07 為週五
    assert crawler.resolve_current_session(datetime(2026, 8, 7, 2, 0)) == "afterhours"
    assert crawler.resolve_current_session(datetime(2026, 8, 7, 8, 29)) == "afterhours"


def test_resolve_current_session_weekend_is_always_afterhours(crawler: PttChatCrawler):
    """假日沒有盤中閒聊，整天延續盤後閒聊"""
    # 2026-08-08 為週六，2026-08-09 為週日
    assert crawler.resolve_current_session(datetime(2026, 8, 8, 10, 0)) == "afterhours"
    assert crawler.resolve_current_session(datetime(2026, 8, 9, 20, 0)) == "afterhours"


def test_resolve_session_date_intraday_before_open_is_previous_day(crawler: PttChatCrawler):
    result = crawler.resolve_session_date("intraday", datetime(2026, 8, 7, 2, 0))
    assert result.strftime("%Y-%m-%d") == "2026-08-06"


def test_resolve_session_date_intraday_after_open_is_same_day(crawler: PttChatCrawler):
    result = crawler.resolve_session_date("intraday", datetime(2026, 8, 7, 9, 0))
    assert result.strftime("%Y-%m-%d") == "2026-08-07"


def test_resolve_session_date_afterhours_before_close_is_previous_day(crawler: PttChatCrawler):
    result = crawler.resolve_session_date("afterhours", datetime(2026, 8, 7, 2, 0))
    assert result.strftime("%Y-%m-%d") == "2026-08-06"


def test_resolve_session_date_afterhours_after_close_is_same_day(crawler: PttChatCrawler):
    result = crawler.resolve_session_date("afterhours", datetime(2026, 8, 7, 14, 0))
    assert result.strftime("%Y-%m-%d") == "2026-08-07"


def test_resolve_session_date_snaps_weekend_date_to_friday(crawler: PttChatCrawler):
    """週六白天手動查盤後閒聊，應該對應到最近的交易日（週五）"""
    result = crawler.resolve_session_date("afterhours", datetime(2026, 8, 8, 15, 0))
    assert result.strftime("%Y-%m-%d") == "2026-08-07"


def test_resolve_session_date_afterhours_continues_through_weekend_to_monday(crawler: PttChatCrawler):
    """週五盤後閒聊應該一路延續到週一 08:30，凌晨仍要能查到週五的日期"""
    # 2026-08-10 為週一
    result = crawler.resolve_session_date("afterhours", datetime(2026, 8, 10, 2, 0))
    assert result.strftime("%Y-%m-%d") == "2026-08-07"


def test_compute_fingerprint_is_deterministic():
    push = {"push_tag": "推 ", "userid": "abc", "content": "hello", "time": "08/06 08:30"}
    assert PttChatCrawler.compute_fingerprint(push) == PttChatCrawler.compute_fingerprint(push)


def test_compute_fingerprint_differs_on_content():
    push_a = {"push_tag": "推 ", "userid": "abc", "content": "hello", "time": "08/06 08:30"}
    push_b = {"push_tag": "推 ", "userid": "abc", "content": "world", "time": "08/06 08:30"}
    assert PttChatCrawler.compute_fingerprint(push_a) != PttChatCrawler.compute_fingerprint(push_b)


def test_find_new_pushes_returns_all_when_no_cursor():
    pushes = [{"push_tag": "推 ", "userid": "a", "content": "1", "time": "08/06 08:30"}]
    assert PttChatCrawler.find_new_pushes(pushes, None) == pushes


def test_find_new_pushes_returns_tail_after_cursor():
    pushes = [
        {"push_tag": "推 ", "userid": "a", "content": "1", "time": "08/06 08:30"},
        {"push_tag": "推 ", "userid": "b", "content": "2", "time": "08/06 08:31"},
        {"push_tag": "推 ", "userid": "c", "content": "3", "time": "08/06 08:32"},
    ]
    cursor = PttChatCrawler.compute_fingerprint(pushes[0])
    assert PttChatCrawler.find_new_pushes(pushes, cursor) == pushes[1:]


def test_find_new_pushes_returns_all_when_cursor_hidden(capsys):
    pushes = [{"push_tag": "推 ", "userid": "a", "content": "1", "time": "08/06 08:30"}]
    result = PttChatCrawler.find_new_pushes(pushes, "not-found-fingerprint")
    assert result == pushes
    assert "隱藏" in capsys.readouterr().out


def test_fetch_pushes_parses_and_skips_warning_box(crawler: PttChatCrawler, monkeypatch):
    monkeypatch.setattr(ptt_chat.requests, "get", lambda *a, **k: FakeResponse(ARTICLE_HTML))

    pushes = crawler.fetch_pushes("https://www.ptt.cc/bbs/Stock/M.1785976206.A.458.html")

    assert len(pushes) == 3
    assert pushes[0] == {"push_tag": "推", "userid": "ruwjo12", "content": "大家早安！", "time": "08/06 08:30"}
    assert pushes[2]["userid"] == "james5271"


def test_find_article_url_matches_date_and_keyword(crawler: PttChatCrawler, monkeypatch):
    monkeypatch.setattr(ptt_chat.requests, "get", lambda *a, **k: FakeResponse(BOARD_INDEX_HTML))

    url = crawler.find_article_url("intraday", "2026/08/06")

    assert url == "https://www.ptt.cc/bbs/Stock/M.1785976206.A.458.html"


def test_find_article_url_returns_none_when_not_found(crawler: PttChatCrawler, monkeypatch):
    monkeypatch.setattr(ptt_chat.requests, "get", lambda *a, **k: FakeResponse(BOARD_INDEX_HTML))

    url = crawler.find_article_url("afterhours", "2026/08/06")

    assert url is None


def test_find_article_url_searches_older_pages_when_not_on_latest(crawler: PttChatCrawler, monkeypatch):
    """最新頁沒有目標文章時，應該往前翻到「上頁」繼續找"""
    page1_html = _board_page_html(None, None, prev_href="/bbs/Stock/index2.html")
    page2_html = _board_page_html(
        "[閒聊] 2026/08/06 盤中閒聊", "/bbs/Stock/M.MATCH.A.111.html", prev_href="/bbs/Stock/index1.html"
    )
    requested_urls: list[str] = []

    def fake_get(url, *a, **k):
        requested_urls.append(url)
        if url == ptt_chat.BOARD_INDEX_URL:
            return FakeResponse(page1_html)
        if url == "https://www.ptt.cc/bbs/Stock/index2.html":
            return FakeResponse(page2_html)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(ptt_chat.requests, "get", fake_get)

    url = crawler.find_article_url("intraday", "2026/08/06")

    assert url == "https://www.ptt.cc/bbs/Stock/M.MATCH.A.111.html"
    assert requested_urls == [ptt_chat.BOARD_INDEX_URL, "https://www.ptt.cc/bbs/Stock/index2.html"]


def test_find_article_url_gives_up_after_max_pages(crawler: PttChatCrawler, monkeypatch):
    """翻到 MAX_INDEX_PAGES_TO_SEARCH 頁還是找不到就放棄，即使還有更舊的頁面可翻"""
    pages = {
        ptt_chat.BOARD_INDEX_URL: _board_page_html(None, None, prev_href="/bbs/Stock/index3.html"),
        "https://www.ptt.cc/bbs/Stock/index3.html": _board_page_html(None, None, prev_href="/bbs/Stock/index2.html"),
        "https://www.ptt.cc/bbs/Stock/index2.html": _board_page_html(None, None, prev_href="/bbs/Stock/index1.html"),
        "https://www.ptt.cc/bbs/Stock/index1.html": _board_page_html(None, None, prev_href="/bbs/Stock/index0.html"),
    }
    requested_urls: list[str] = []

    def fake_get(url, *a, **k):
        requested_urls.append(url)
        return FakeResponse(pages[url])

    monkeypatch.setattr(ptt_chat.requests, "get", fake_get)

    result = crawler.find_article_url("intraday", "2026/08/06")

    assert result is None
    assert requested_urls == [
        ptt_chat.BOARD_INDEX_URL,
        "https://www.ptt.cc/bbs/Stock/index3.html",
        "https://www.ptt.cc/bbs/Stock/index2.html",
        "https://www.ptt.cc/bbs/Stock/index1.html",
    ]


def test_run_skips_when_article_not_resolved_yet(monkeypatch):
    writer = FakeFirestoreWriter(FakeDocSnapshot(exists=False))
    crawler = PttChatCrawler(writer)
    board_html_without_match = "<html><body></body></html>"
    monkeypatch.setattr(ptt_chat.requests, "get", lambda *a, **k: FakeResponse(board_html_without_match))

    message = crawler.run(now=datetime(2026, 8, 6, 8, 30))

    assert "尚未找到" in message
    assert writer.write_calls == []


def test_run_uses_previous_day_for_early_morning_afterhours_resolution(monkeypatch):
    """凌晨 2 點應該找「前一天」的盤後閒聊文章，而不是當天（當天盤後閒聊還沒發文）"""
    writer = FakeFirestoreWriter(FakeDocSnapshot(exists=False))
    crawler = PttChatCrawler(writer)
    board_html_without_match = "<html><body></body></html>"
    monkeypatch.setattr(ptt_chat.requests, "get", lambda *a, **k: FakeResponse(board_html_without_match))

    message = crawler.run(now=datetime(2026, 8, 7, 2, 0))

    assert "2026/08/06 盤後閒聊 文章尚未找到" in message


def test_run_ignores_stale_thread_from_previous_day(monkeypatch):
    """pttThreads 只保留 intraday/afterhours 兩份文件，date 跟今天不同代表是舊資料，要重新解析而不是沿用"""
    writer = FakeFirestoreWriter(
        FakeDocSnapshot(
            exists=True,
            data={
                "date": "20260805",
                "article_url": "https://www.ptt.cc/old-article.html",
                "last_fingerprint": "stale-fingerprint",
            },
        )
    )
    crawler = PttChatCrawler(writer)
    monkeypatch.setattr(ptt_chat.requests, "get", lambda *a, **k: FakeResponse(BOARD_INDEX_HTML))

    crawler.run(now=datetime(2026, 8, 6, 10, 30))

    thread_write = next(c for c in writer.write_calls if c["collection"] == "pttThreads" and c["data"].get("article_url"))
    assert thread_write["document_id"] == "intraday"
    assert thread_write["data"]["article_url"] == "https://www.ptt.cc/bbs/Stock/M.1785976206.A.458.html"
    assert thread_write["data"]["date"] == "20260806"
    assert thread_write["data"]["last_fingerprint"] is None


def test_run_writes_new_pushes_when_article_already_resolved(monkeypatch):
    article_url = "https://www.ptt.cc/bbs/Stock/M.1785976206.A.458.html"
    writer = FakeFirestoreWriter(
        FakeDocSnapshot(exists=True, data={"date": "20260806", "article_url": article_url, "last_fingerprint": None})
    )
    crawler = PttChatCrawler(writer)
    monkeypatch.setattr(ptt_chat.requests, "get", lambda *a, **k: FakeResponse(ARTICLE_HTML))

    message = crawler.run(now=datetime(2026, 8, 6, 10, 30))

    assert "新增 3 則推文" in message
    posts_write = next(c for c in writer.write_calls if c["collection"] == "pttPosts")
    thread_write = next(c for c in writer.write_calls if c["collection"] == "pttThreads")
    assert posts_write["document_id"] == "20260806_intraday"
    assert thread_write["document_id"] == "intraday"
    assert posts_write["data"]["posts"] == firestore.ArrayUnion(crawler.fetch_pushes(article_url))
    assert thread_write["data"]["date"] == "20260806"
    assert thread_write["data"]["last_fingerprint"] == PttChatCrawler.compute_fingerprint(
        crawler.fetch_pushes(article_url)[-1]
    )
