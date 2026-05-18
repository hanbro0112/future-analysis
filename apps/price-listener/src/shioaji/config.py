import os
from dotenv import load_dotenv

load_dotenv()

config = {
    "api_key": os.environ["API_KEY"],
    "secret_key": os.environ["SECRET_KEY"],
    "ca_cert_path": os.environ["CA_CERT_PATH"],
    "ca_password": os.environ["CA_PASSWORD"],

    # 從環境變數讀取配置，預設使用 emulator
    "gcp_project_id": os.getenv("GCP_PROJECT_ID", "demo-project"),
    "pubsub_topic_id": os.getenv("PUBSUB_TOPIC_ID", "price-updates"),
}

__all__ = ["config"]