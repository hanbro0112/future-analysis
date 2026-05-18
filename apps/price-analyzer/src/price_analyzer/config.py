"""配置模組"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 載入根目錄的 .env
root_dir = Path(__file__).resolve().parents[4]
env_file = root_dir / '.env'
if env_file.exists():
    load_dotenv(env_file)

config = {
    # GCP 配置
    "project_id": os.getenv("GCP_PROJECT_ID", "demo-project"),
    "subscription_id": os.getenv("PUBSUB_SUBSCRIPTION_ID", "price-subscription"),
    "collection_name": os.getenv("FIRESTORE_COLLECTION", "prices"),
}

__all__ = ["config"]