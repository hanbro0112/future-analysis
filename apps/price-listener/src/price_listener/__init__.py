import shioaji as sj
from shioaji import TickFOPv1, Exchange
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# 將 libs 目錄加入 Python path
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from libs.pubsub import PubSubPublisher

config = {
    "api_key": os.environ["API_KEY"],
    "secret_key": os.environ["SECRET_KEY"],
    "ca_cert_path": os.environ["CA_CERT_PATH"],
    "ca_password": os.environ["CA_PASSWORD"],
}

# 初始化 Pub/Sub Publisher
pubsub_publisher: PubSubPublisher | None = None


def init_pubsub():
    """初始化 Pub/Sub Publisher"""
    global pubsub_publisher
    
    # 從環境變數讀取配置，預設使用 emulator
    project_id = os.getenv("GCP_PROJECT_ID", "demo-project")
    topic_id = os.getenv("PUBSUB_TOPIC_ID", "price-updates")
    
    try:
        pubsub_publisher = PubSubPublisher(project_id=project_id)
        # 確保 topic 存在
        pubsub_publisher.ensure_topic_exists(topic_id)
        print(f"✅ Pub/Sub 初始化成功，Topic: {topic_id}")
    except Exception as e:
        print(f"⚠️  Pub/Sub 初始化失敗: {e}")
        print(f"   將繼續運行，但不會發送訊息到 Pub/Sub")
        pubsub_publisher = None


def quote_callback(exchange: Exchange, tick: TickFOPv1):
    """處理報價回調，推送到 Pub/Sub"""
    print(f"Received tick from {exchange}: {tick}")
    
    # 如果 Pub/Sub 已初始化，則發送訊息
    if pubsub_publisher:
        try:
            topic_id = os.getenv("PUBSUB_TOPIC_ID", "price-updates")
            
            # 準備訊息資料
            message_data = {
                "symbol": tick.code,
                "exchange": str(exchange),
                "close": float(tick.close) if tick.close else None,
                "volume": int(tick.volume) if tick.volume else None,
                "bid_price": float(tick.bid_price) if tick.bid_price else None,
                "ask_price": float(tick.ask_price) if tick.ask_price else None,
                "bid_volume": int(tick.bid_volume) if tick.bid_volume else None,
                "ask_volume": int(tick.ask_volume) if tick.ask_volume else None,
                "timestamp": datetime.now().isoformat(),
            }
            
            # 發布到 Pub/Sub
            message_id = pubsub_publisher.publish_message(
                topic_id=topic_id,
                data=message_data,
                source="price-listener"
            )
            print(f"📤 已發布到 Pub/Sub，訊息 ID: {message_id}")
            
        except Exception as e:
            print(f"❌ 發送訊息到 Pub/Sub 失敗: {e}")


def check_usage(api: sj.Shioaji):
    """檢查 API 使用量並顯示剩餘額度百分比"""
    try:
        # { connections=1, bytes, limit_bytes=500MB, remaining_bytes }
        usage = api.usage()
        
        # 提取 limit_bytes 和 remaining_bytes（物件屬性，不是字典）
        limit_bytes = usage.limit_bytes
        remaining_bytes = usage.remaining_bytes
        
        if limit_bytes > 0:
            # 計算剩餘百分比
            remaining_percentage = (remaining_bytes / limit_bytes) * 100
            used_percentage = 100 - remaining_percentage
            
            # 將 bytes 轉換為 MB 以便閱讀
            limit_mb = limit_bytes / (1024 * 1024)
            remaining_mb = remaining_bytes / (1024 * 1024)
            used_mb = limit_mb - remaining_mb
            
            print(f"📊 API 使用量報告")
            print(f"   已使用: {used_mb:.0f} MB ({used_percentage:.1f}%)")
            print(f"   剩餘額度: {remaining_mb:.0f} MB ({remaining_percentage:.1f}%)")
            print(f"   總額度: {limit_mb:.0f} MB")
            
            # 根據剩餘百分比顯示警告
            if remaining_percentage < 10:
                print(f"⚠️  警告：剩餘額度不足 10%，請注意流量使用！")
            elif remaining_percentage < 25:
                print(f"⚡ 提醒：剩餘額度低於 25%")
        else:
            print(f"⚠️  無法計算使用量百分比，usage 資料: {usage}")
    except Exception as e:
        print(f"❌ 檢查使用量時發生錯誤: {e}")
        print(f"   原始資料: {usage}")


def main() -> None:
    # 初始化 Pub/Sub
    init_pubsub()
    
    api = get_shioaji_client() 
    # TXF: 大台 MXF: 小台 R1: 熱門月(近月) 合約
    target_symbols = ["MXFR1"]
    
    for code in target_symbols:
        # 取得合約物件並訂閱報價
        contract = api.Contracts.Futures[code]
        if contract:
            print(f"Subscribing to {contract.code}...")
            api.quote.subscribe(
                contract, 
                quote_type = sj.constant.QuoteType.Quote,
                version = sj.constant.QuoteVersion.v1
            )
        else:
            print(f"Contract {code} not found.")

    # 註冊回調函數
    api.quote.set_on_tick_fop_v1_callback(quote_callback)
    
    try:
        print("Listening for price updates... Press Ctrl+C to exit.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting...")


def get_shioaji_client() -> sj.Shioaji:
    api = sj.Shioaji(simulation=True)
    print("Connecting to Shioaji API...")
    api.login(
        api_key=config["api_key"],
        secret_key=config["secret_key"],
    )
    
    # ca 憑證放在專案根目錄
    project_root = Path(__file__).resolve().parents[4]
    ca_path = str(project_root / config["ca_cert_path"])
    
    api.activate_ca(
        ca_path= ca_path,
        ca_passwd=config["ca_password"]
    )
    print("Shioaji API login and activate CA successfully.")
    return api
