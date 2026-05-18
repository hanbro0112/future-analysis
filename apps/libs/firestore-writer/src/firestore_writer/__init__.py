"""
Firestore 客戶端模組
提供寫入資料到 Firestore 的功能，支援 Emulator 和正式環境
"""
from .client import FirestoreWriter, is_emulator_mode

__all__ = [
    "FirestoreWriter",
    "is_emulator_mode",
]
