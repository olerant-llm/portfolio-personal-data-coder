"""マスター（対応表）の暗号化保存・読み込み。

- パスワードから PBKDF2HMAC(SHA256) で鍵を作り、Fernet で暗号化する。
- ファイルは「先頭16バイト＝salt（平文）」＋「残り＝暗号文」の形。
- 平文をディスクに書く経路は作らない（保存時は必ず暗号化して書く）。
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 仕様: iterations は 600000 以上、salt は 16 バイト
SALT_SIZE = 16
KDF_ITERATIONS = 600_000


class StorageError(Exception):
    """保存・読み込みに関する利用者向けエラー。"""


class WrongPasswordError(StorageError):
    """パスワードが違う（またはファイルが壊れている）場合。"""


def _derive_key(password: str, salt: bytes) -> bytes:
    """パスワードと salt から Fernet 用の鍵（32バイトを base64 化）を作る。"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    raw = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def master_exists(path: str | os.PathLike) -> bool:
    """マスターファイルが既にあるか。"""
    return Path(path).exists()


def save_master(data: dict, password: str, path: str | os.PathLike) -> None:
    """マスター（dict）を暗号化してファイルに保存する。

    毎回新しい salt を生成し、salt＋暗号文をまとめて書き込む。
    平文が途中でディスクに残らないよう、一時ファイルへ暗号文を書いてから差し替える。
    """
    path = Path(path)
    try:
        salt = os.urandom(SALT_SIZE)
        key = _derive_key(password, salt)
        plaintext = json.dumps(data, ensure_ascii=False).encode("utf-8")
        token = Fernet(key).encrypt(plaintext)

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as f:
            f.write(salt + token)
        os.replace(tmp, path)
    except WrongPasswordError:
        raise
    except Exception as exc:  # noqa: BLE001 - 利用者向けに平易化する
        raise StorageError(f"名簿の保存に失敗しました。（{exc}）") from exc


def load_master(password: str, path: str | os.PathLike) -> dict:
    """暗号化マスターを読み込んで dict を返す。

    パスワード違い・破損時は WrongPasswordError を送出する。
    """
    path = Path(path)
    try:
        blob = path.read_bytes()
    except FileNotFoundError as exc:
        raise StorageError("名簿ファイルが見つかりません。") from exc
    except Exception as exc:  # noqa: BLE001
        raise StorageError(f"名簿ファイルを開けませんでした。（{exc}）") from exc

    if len(blob) <= SALT_SIZE:
        raise WrongPasswordError("パスワードが違います")

    salt, token = blob[:SALT_SIZE], blob[SALT_SIZE:]
    key = _derive_key(password, salt)
    try:
        plaintext = Fernet(key).decrypt(token)
    except InvalidToken as exc:
        # パスワード違い・改ざん・破損はすべてこれに集約（詳細は出さない）
        raise WrongPasswordError("パスワードが違います") from exc

    try:
        return json.loads(plaintext.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise StorageError("名簿ファイルの中身を読み取れませんでした。") from exc
