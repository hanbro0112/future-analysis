"""
Price Listener 主程式
監聽股價並發送到 Pub/Sub
"""
import sys
from pathlib import Path

# 將 libs 目錄加入 Python path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from price_listener import main


if __name__ == "__main__":
    main()
