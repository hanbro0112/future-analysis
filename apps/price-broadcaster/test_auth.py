"""
測試 Firebase Auth Token 驗證邏輯
"""
import sys
from pathlib import Path

# 添加 apps 目錄（config 模組）與 src 目錄到路徑
apps_path = Path(__file__).resolve().parents[1]
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(apps_path))
sys.path.insert(0, str(src_path))

import pytest

from price_broadcaster.auth import verify_firebase_token, InvalidTokenError


def test_verify_firebase_token_missing_token_raises():
    """缺少 Token 應拋出 InvalidTokenError"""
    with pytest.raises(InvalidTokenError):
        verify_firebase_token("")

    with pytest.raises(InvalidTokenError):
        verify_firebase_token(None)


def test_verify_firebase_token_valid(monkeypatch):
    """有效 Token 應回傳解碼後的 payload"""
    decoded = {"uid": "user-123", "email": "user@example.com"}

    monkeypatch.setattr("price_broadcaster.auth._get_app", lambda: object())
    monkeypatch.setattr(
        "price_broadcaster.auth.firebase_auth.verify_id_token",
        lambda token, app=None: decoded,
    )

    result = verify_firebase_token("valid-token")

    assert result == decoded


def test_verify_firebase_token_invalid_raises(monkeypatch):
    """無效 Token 應包裝為 InvalidTokenError"""

    def raise_error(token, app=None):
        raise ValueError("Token 已過期")

    monkeypatch.setattr("price_broadcaster.auth._get_app", lambda: object())
    monkeypatch.setattr(
        "price_broadcaster.auth.firebase_auth.verify_id_token", raise_error
    )

    with pytest.raises(InvalidTokenError):
        verify_firebase_token("expired-token")
