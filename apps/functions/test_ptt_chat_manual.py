"""
PTT Chat Crawler Manual Trigger - 手動觸發 PTT 閒聊爬蟲測試腳本
會實際打 PTT 網頁並依規定的 Firestore schema 寫入 pttThreads / pttPosts，無需等待 Cloud Scheduler
"""
import os
import sys
from datetime import datetime
import argparse
from dotenv import load_dotenv

from firestore_writer import FirestoreWriter
from ptt_chat import PttChatCrawler


def main():
    """手動觸發一次 PTT 閒聊爬蟲"""
    load_dotenv()

    parser = argparse.ArgumentParser(description='手動觸發 PTT 閒聊爬蟲')
    parser.add_argument(
        '--now',
        type=str,
        help='模擬觸發時間 (格式: YYYY-MM-DD HH:MM)，預設為現在，可用來測試盤中/盤後切換',
        default=None,
    )
    args = parser.parse_args()

    now = datetime.strptime(args.now, '%Y-%m-%d %H:%M') if args.now else datetime.now()

    print("=" * 70)
    print("📊 PTT 閒聊爬蟲手動測試")
    print("=" * 70)
    print(f"🕐 觸發時間: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")

    firestore_writer = FirestoreWriter(project_id=os.getenv("GCP_PROJECT_ID", "demo-project"))

    try:
        crawler = PttChatCrawler(firestore_writer)
        session = crawler.resolve_current_session(now)
        target_date = crawler.resolve_session_date(session, now)
        posts_doc_id = f"{target_date.strftime('%Y%m%d')}_{session}"

        print(f"📌 判定時段: {session}")
        print(f"📌 pttThreads 文件 ID: {session}（只維護 intraday/afterhours 兩份，內含 date 欄位判斷是否過期）")
        print(f"📌 pttPosts 文件 ID: {posts_doc_id}\n")
        print("-" * 70)

        message = crawler.run(now)

        print("-" * 70)
        print()
        print(f"✅ 執行結果: {message}")
        print(f"💾 已依規定寫入 Firestore:")
        print(f"   - pttThreads/{session}       (date, article_url, last_fingerprint)")
        print(f"   - pttPosts/{posts_doc_id}    (posts[])")

    except Exception as e:
        print(f"❌ 執行時發生錯誤: {e}")
        sys.exit(1)
    finally:
        firestore_writer.close()

    print()
    print("=" * 70)
    print("✨ 測試完成")
    print("=" * 70)


if __name__ == '__main__':
    main()
