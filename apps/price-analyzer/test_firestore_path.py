"""
測試寫入 Firestore 的路徑是否正確使用截斷後的商品代碼（例如 MXFH6 -> MXF），
避免分鐘 OHLC 與秒級 tick 明細用不同代碼格式寫到不同路徑。
"""
import sys
from pathlib import Path
from decimal import Decimal

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from price_analyzer import _extract_base_code, on_minute_complete, on_second_data_complete
from price_analyzer.minute_aggregator import MinuteBar, SecondBar
from price_analyzer.strategy import LongShortAnalyzer


class FakeFirestoreWriter:
    """假的 FirestoreWriter，只記錄呼叫參數，不實際連線 GCP"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def write_document(self, collection: str, data: dict, document_id: str) -> None:
        self.calls.append({"collection": collection, "data": data, "document_id": document_id})


def make_minute_bar(code: str) -> MinuteBar:
    return MinuteBar(
        code=code,
        timestamp=None,
        date="2026-07-27",
        time="0900",
        market_type="regular",
        open=Decimal("21800"),
        high=Decimal("21805"),
        low=Decimal("21795"),
        close=Decimal("21800"),
        volume=10,
    )


def test_extract_base_code_strips_contract_month():
    assert _extract_base_code("MXFH6") == "MXF"
    assert _extract_base_code("MXFF6") == "MXF"
    assert _extract_base_code("TXFH6") == "TXF"


def test_extract_base_code_keeps_short_code_unchanged():
    assert _extract_base_code("MX") == "MX"
    assert _extract_base_code("") == ""


def test_on_minute_complete_writes_to_truncated_code_path():
    writer = FakeFirestoreWriter()
    analyzer = LongShortAnalyzer()
    bar = make_minute_bar("MXFH6")

    on_minute_complete(bar, writer, analyzer)

    assert len(writer.calls) == 1
    assert writer.calls[0]["collection"] == "market/MXF/20260727"
    assert writer.calls[0]["document_id"] == "0900"


def test_on_second_data_complete_writes_to_truncated_code_path():
    """秒級 tick 明細應與分鐘 OHLC 用同一套截斷後代碼，寫到 market/MXF/..._tick，
    而不是完整合約代碼 market/MXFH6/..._tick"""
    writer = FakeFirestoreWriter()
    second_bar = SecondBar(
        code="MXFH6",
        date="20260727",
        time="0900",
        prices={"00": {"price": 100.0}},
    )

    on_second_data_complete(second_bar, writer)

    assert len(writer.calls) == 1
    assert writer.calls[0]["collection"] == "market/MXF/20260727_tick"
    assert writer.calls[0]["document_id"] == "0900"
