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
    "api_key": os.environ["API_KEY"],
    "secret_key": os.environ["SECRET_KEY"],
    "ca_cert_path": os.environ["CA_CERT_PATH"],
    "ca_password": os.environ["CA_PASSWORD"],

    # GCP 配置
    "gcp_project_id": os.getenv("GCP_PROJECT_ID", "demo-project"),
    "pubsub_topic_id": os.getenv("PUBSUB_TOPIC_ID", "price-updates"),
}

__all__ = ["config"]