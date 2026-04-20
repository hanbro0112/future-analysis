import shioaji as sj
from shioaji import TickFOPv1, Exchange
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
config = {
    "api_key": os.environ["API_KEY"],
    "secret_key": os.environ["SECRET_KEY"],
    "ca_cert_path": os.environ["CA_CERT_PATH"],
    "ca_password": os.environ["CA_PASSWORD"],
}


def quote_callback(exchange: Exchange, tick: TickFOPv1):
    print(f"Received tick from {exchange}: {tick}")


def main() -> None:
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
