"""Чтение/запись .txt с автодетектом кодировки.

Порядок: BOM (utf-8-sig, utf-16) → utf-8 → cp1251 (как самая вероятная
однобайтовая для русских текстов). Сохраняем в исходной кодировке.
"""
from __future__ import annotations

from pathlib import Path


def detect_encoding(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return "utf-16"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1251"


def read_txt(path: str | Path) -> tuple[str, str]:
    raw = Path(path).read_bytes()
    enc = detect_encoding(raw)
    return raw.decode(enc), enc


def write_txt(path: str | Path, text: str, encoding: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(text.encode(encoding))
