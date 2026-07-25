"""配置模組"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 載入根目錄的 .env
root_dir = Path(__file__).resolve().parents[1]
env_file = root_dir / '.env'
if env_file.exists():
    load_dotenv(env_file)
else:
    print(f"⚠️  配置文件不存在: {env_file}")

config = {
    # 僅 price-listener 需要（Shioaji 憑證），其餘服務不使用
    "api_key": os.getenv("API_KEY", ""),
    "secret_key": os.getenv("SECRET_KEY", ""),
    "ca_cert_path": os.getenv("CA_CERT_PATH", ""),
    "ca_password": os.getenv("CA_PASSWORD", ""),

    # GCP 配置
    "gcp_project_id": os.getenv("GCP_PROJECT_ID", "demo-project"),
    "pubsub_topic_id": os.getenv("PUBSUB_TOPIC_ID", "price-updates"),
    "pubsub_subscription_id": os.getenv("PUBSUB_SUBSCRIPTION_ID", "price-subscription"),
}

__all__ = ["config"]