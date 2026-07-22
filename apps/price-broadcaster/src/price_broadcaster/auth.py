"""
Firebase Auth Token 驗證模組
用於驗證前端 WebSocket 連線時帶上的 Firebase ID Token
"""
from typing import Any, Dict

import firebase_admin
from firebase_admin import auth as firebase_auth

from config import config


class InvalidTokenError(Exception):
    """Firebase ID Token 無效或已過期"""


def _get_app() -> firebase_admin.App:
    """
    取得（或初始化）Firebase Admin App 實例

    正式環境依賴執行環境綁定的服務帳戶（Cloud Run / GKE 等）透過
    Application Default Credentials 自動取得憑證；
    本地開發搭配 FIREBASE_AUTH_EMULATOR_HOST 使用 Auth Emulator，不需要真實憑證。

    Returns:
        Firebase Admin App 實例
    """
    if firebase_admin._apps:
        return firebase_admin.get_app()

    return firebase_admin.initialize_app(options={"projectId": config["gcp_project_id"]})


def verify_firebase_token(token: str) -> Dict[str, Any]:
    """
    驗證 Firebase ID Token

    Args:
        token: 前端傳入的 Firebase ID Token

    Returns:
        解碼後的 Token payload（含 uid 等欄位）

    Raises:
        InvalidTokenError: Token 缺失、無效或已過期
    """
    if not token:
        raise InvalidTokenError("缺少 Token")

    try:
        app = _get_app()
        return firebase_auth.verify_id_token(token, app=app)
    except InvalidTokenError:
        raise
    except Exception as e:
        raise InvalidTokenError(f"Token 驗證失敗: {e}") from e
