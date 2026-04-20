import shioaji as sj
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def main() -> None:
    get_shioaji_client()


def get_shioaji_client() -> sj.Shioaji:
    api = sj.Shioaji(simulation=True)
    print("Connecting to Shioaji API...")
    api.login(
        api_key=os.environ["API_KEY"],
        secret_key=os.environ["SECRET_KEY"],
        fetch_contract=False
    )
    
    # ca 憑證放在專案根目錄
    project_root = Path(__file__).resolve().parents[4]
    ca_path = str(project_root / os.environ["CA_CERT_PATH"])
    
    api.activate_ca(
        ca_path= ca_path,
        ca_passwd=os.environ["CA_PASSWORD"]
    )
    print("login and activate CA successfully.")
    return api
