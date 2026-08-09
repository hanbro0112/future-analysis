"""
PTT Stock 板盤中/盤後閒聊爬蟲
每分鐘由 Cloud Scheduler 觸發，抓取當日「盤中閒聊」「盤後閒聊」文章的推文並寫入 Firestore
"""
import hashlib
import os
import re
from datetime import datetime, timedelta
from typing import Literal, Optional, TypedDict

import requests
from bs4 import BeautifulSoup
from google.cloud import firestore

from firestore_writer import FirestoreWriter

Session = Literal["intraday", "afterhours"]


class Push(TypedDict):
    push_tag: str
    userid: str
    content: str
    time: str


BOARD_INDEX_URL = "https://www.ptt.cc/bbs/Stock/index.html"
BOARD_BASE_URL = "https://www.ptt.cc"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FuturesAnalysisBot/1.0)"}
REQUEST_TIMEOUT_SECONDS = 15
MAX_INDEX_PAGES_TO_SEARCH = 4  # 最新頁 + 找不到最多再往前翻 3 頁

SESSION_TITLE_KEYWORD: dict[Session, str] = {
    "intraday": "盤中閒聊",
    "afterhours": "盤後閒聊",
}

# 台股現股時段時間，用來判斷目前該對應盤中或盤後閒聊
CASH_MARKET_OPEN_MINUTES = 8 * 60 + 30  # 08:30，盤中閒聊開始
CASH_MARKET_CLOSE_MINUTES = 14 * 60  # 14:00，盤後閒聊開始


def _last_trading_day(date: datetime) -> datetime:
    """若 date 落在週末，往前推到最近的週五（不含國定假日判斷）"""
    weekday = date.weekday()  # 0=Mon ... 5=Sat, 6=Sun
    if weekday == 5:
        return date - timedelta(days=1)
    if weekday == 6:
        return date - timedelta(days=2)
    return date


class PttChatCrawler:
    """PTT Stock 板盤中/盤後閒聊爬蟲"""

    def __init__(self, firestore_writer: FirestoreWriter) -> None:
        self.firestore_writer = firestore_writer

    def resolve_current_session(self, now: datetime) -> Session:
        """
        依現在時間判斷目前預設屬於盤中還是盤後閒聊

        - 週六、週日：整天延續盤後閒聊（假日沒有盤中閒聊）
        - 平日 00:00-08:29（凌晨，延續前一天的盤後閒聊，因為當天盤中閒聊還沒發文）=> afterhours
        - 平日 08:30-13:59 => intraday
        - 平日 14:00-23:59 => afterhours
        """
        if now.weekday() >= 5:
            return "afterhours"

        total_minutes = now.hour * 60 + now.minute
        if total_minutes < CASH_MARKET_OPEN_MINUTES:
            return "afterhours"
        return "intraday" if total_minutes < CASH_MARKET_CLOSE_MINUTES else "afterhours"

    def resolve_session_date(self, session: Session, now: datetime) -> datetime:
        """
        依現在時間與指定 session，判斷該 session 對應的日期

        兩個 session 各自的「今天文章還沒發文」判斷時間點不同（盤中 08:30 / 盤後 14:00），
        未到發文時間前延續前一天的日期；算出來的日期若落在週末，再往前推到最近的交易日（週五），
        所以週五盤後閒聊會一路延續到週一 08:30
        """
        total_minutes = now.hour * 60 + now.minute
        cutoff_minutes = CASH_MARKET_OPEN_MINUTES if session == "intraday" else CASH_MARKET_CLOSE_MINUTES
        target_date = now - timedelta(days=1) if total_minutes < cutoff_minutes else now
        return _last_trading_day(target_date)

    def find_article_url(self, session: Session, date_title_str: str) -> Optional[str]:
        """
        在板面 index 尋找當天對應 session 的文章連結

        從最新一頁開始找，找不到就往前翻頁（較舊），最多翻到 MAX_INDEX_PAGES_TO_SEARCH 頁，
        避免文章發出後被大量後續文章洗出最新頁時找不到

        Args:
            session: intraday 或 afterhours
            date_title_str: 文章標題中的日期格式，例如 2026/08/06

        Returns:
            文章完整網址，找不到則回傳 None
        """
        keyword = SESSION_TITLE_KEYWORD[session]
        page_url = BOARD_INDEX_URL

        for _ in range(MAX_INDEX_PAGES_TO_SEARCH):
            try:
                response = requests.get(page_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"❌ 讀取板面列表失敗: {page_url} - {e}")
                return None

            soup = BeautifulSoup(response.text, "html.parser")

            for entry in soup.select("div.r-ent"):
                title_tag = entry.select_one("div.title a")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                if date_title_str in title and keyword in title:
                    return BOARD_BASE_URL + title_tag["href"]

            prev_page_href = self._find_prev_page_href(soup)
            if not prev_page_href:
                break
            page_url = BOARD_BASE_URL + prev_page_href

        return None

    @staticmethod
    def _find_prev_page_href(soup: BeautifulSoup) -> Optional[str]:
        """從板面頁面找「‹ 上頁」（較舊的一頁）連結，已在最舊頁時該連結不存在"""
        for link in soup.select("div.btn-group-paging a.btn"):
            if "上頁" in link.get_text():
                return link.get("href")
        return None

    def fetch_pushes(self, article_url: str) -> list[Push]:
        """
        抓取文章頁目前可見的所有推文（排除「檔案過大」提示區塊）

        Args:
            article_url: 文章網址

        Returns:
            推文列表（依畫面上原始順序），失敗則回傳空列表
        """
        try:
            response = requests.get(article_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"❌ 讀取文章失敗: {article_url} - {e}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        pushes: list[Push] = []

        for push_div in soup.select("div.push"):
            if "warning-box" in push_div.get("class", []):
                continue

            tag_el = push_div.select_one(".push-tag")
            userid_el = push_div.select_one(".push-userid")
            content_el = push_div.select_one(".push-content")
            time_el = push_div.select_one(".push-ipdatetime")

            if not (tag_el and userid_el and content_el and time_el):
                continue

            content = re.sub(r"^:\s*", "", content_el.get_text(strip=True))
            pushes.append({
                "push_tag": tag_el.get_text(strip=True),
                "userid": userid_el.get_text(strip=True),
                "content": content,
                "time": time_el.get_text(strip=True),
            })

        return pushes

    @staticmethod
    def compute_fingerprint(push: Push) -> str:
        """計算單則推文的指紋，用來當增量游標（推文沒有唯一 ID）"""
        raw = f"{push['userid']}|{push['time']}|{push['content']}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def find_new_pushes(pushes: list[Push], last_fingerprint: Optional[str]) -> list[Push]:
        """
        找出 last_fingerprint 之後新增的推文

        - last_fingerprint 為 None：第一次抓取，全部視為新推文
        - last_fingerprint 在目前列表中找不到：代表中段被 PTT 隱藏吃掉了，
          視為全部都是新的並記警告（可能造成重複，可接受）

        Args:
            pushes: 目前頁面上的推文列表（依原始順序）
            last_fingerprint: 上次已處理到的推文指紋

        Returns:
            新增的推文列表
        """
        if last_fingerprint is None:
            return pushes

        for index, push in enumerate(pushes):
            if PttChatCrawler.compute_fingerprint(push) == last_fingerprint:
                return pushes[index + 1:]

        print(f"⚠️  找不到上次記錄的推文指紋（可能已被 PTT 隱藏），視為全部新增: {last_fingerprint}")
        return pushes

    def run(self, now: Optional[datetime] = None) -> str:
        """
        執行一次爬取（由 Cloud Scheduler 每分鐘觸發）

        流程：先看有無已解析的文章網址，沒有再嘗試解析，若還是沒有則結束本次更新

        `pttThreads` 只維護 intraday/afterhours 兩份文件（文件 ID 就是 session），
        不像 `pttPosts` 按日期各自累積歷史；文件內用 `date` 欄位記錄目前鎖定的文章屬於哪一天，
        跨天時視為過期，不能沿用舊的 article_url/last_fingerprint

        Returns:
            執行結果訊息
        """
        now = now or datetime.now()
        session = self.resolve_current_session(now)
        target_date = self.resolve_session_date(session, now)
        target_date_key = target_date.strftime("%Y%m%d")
        posts_doc_id = f"{target_date_key}_{session}"

        thread_snapshot = self.firestore_writer.db.collection("pttThreads").document(session).get()
        thread_data = thread_snapshot.to_dict() or {} if thread_snapshot.exists else {}
        is_same_day = thread_data.get("date") == target_date_key
        article_url = thread_data.get("article_url") if is_same_day else None
        last_fingerprint = thread_data.get("last_fingerprint") if is_same_day else None

        if not article_url:
            date_title_str = target_date.strftime("%Y/%m/%d")
            article_url = self.find_article_url(session, date_title_str)

            if not article_url:
                message = f"{date_title_str} {SESSION_TITLE_KEYWORD[session]} 文章尚未找到，本次跳過"
                print(f"⏸️  {message}")
                return message

            self.firestore_writer.write_document(
                collection="pttThreads",
                document_id=session,
                data={"date": target_date_key, "article_url": article_url, "last_fingerprint": None},
                merge=True,
            )
            print(f"✅ 已鎖定文章: {article_url}")

        pushes = self.fetch_pushes(article_url)
        if not pushes:
            return "本次未抓到任何推文"

        new_pushes = self.find_new_pushes(pushes, last_fingerprint)
        if not new_pushes:
            return "無新增推文"

        self.firestore_writer.write_document(
            collection="pttPosts",
            document_id=posts_doc_id,
            data={"posts": firestore.ArrayUnion(new_pushes)},
            merge=True,
        )
        self.firestore_writer.write_document(
            collection="pttThreads",
            document_id=session,
            data={"date": target_date_key, "last_fingerprint": self.compute_fingerprint(pushes[-1])},
            merge=True,
        )

        message = f"新增 {len(new_pushes)} 則推文"
        print(f"✅ {message}")
        return message


def crawl_ptt_chat(request):
    """Cloud Functions HTTP entry point：由 Cloud Scheduler 每分鐘觸發"""
    now = datetime.now()

    try:
        firestore_writer = FirestoreWriter(project_id=os.getenv("GCP_PROJECT_ID", "demo-project"))
        try:
            crawler = PttChatCrawler(firestore_writer)
            message = crawler.run(now)
        finally:
            firestore_writer.close()

        return message, 200

    except Exception as e:
        print(f"❌ PTT 閒聊爬蟲發生錯誤: {e}")
        return f"PTT 閒聊爬蟲失敗: {e}", 500
