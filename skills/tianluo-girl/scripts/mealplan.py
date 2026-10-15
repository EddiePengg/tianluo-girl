"""饭食计划读取：plans/*.json 按日期索引，结构：

    { "2026-10-16": { "dinner": "番茄牛腩煲", "prep": ["早上牛腩焯水", …] } }
"""
from __future__ import annotations

import json
from pathlib import Path

PLANS_DIR = Path(__file__).resolve().parent / "plans"


def load_all() -> dict:
    out: dict = {}
    if not PLANS_DIR.is_dir():
        return out
    for f in sorted(PLANS_DIR.glob("*.json")):
        out.update(json.loads(f.read_text(encoding="utf-8")))
    return out


def get(date_str: str) -> dict | None:
    return load_all().get(date_str)
