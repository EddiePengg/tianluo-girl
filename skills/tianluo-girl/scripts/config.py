"""配置来源：skill 目录下的 config.json（环境变量同名可临时覆盖）。
百炼 API Key：环境变量 DASHSCOPE_API_KEY → 回落 ~/.bailian/config.json（bl CLI 登录即有）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parents[1]
_CONFIG_PATH = _SKILL_DIR / "config.json"
_BAILIAN_CONFIG = Path.home() / ".bailian" / "config.json"

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _cache = {}
    return _cache


def get(key: str, default: str = "") -> str:
    """环境变量优先，回落 config.json。"""
    return os.environ.get(key) or str(_load().get(key, default) or default)


def dashscope_api_key() -> str:
    if key := os.environ.get("DASHSCOPE_API_KEY", ""):
        return key
    try:
        data = json.loads(_BAILIAN_CONFIG.read_text(encoding="utf-8"))
        return str(data.get("api_key", ""))
    except (OSError, json.JSONDecodeError):
        return ""


def dashscope_ws_url() -> str:
    """百炼推理 WS 地址：DASHSCOPE_WS_URL 覆盖 → ~/.bailian/config.json base_url 推导。"""
    if url := os.environ.get("DASHSCOPE_WS_URL", ""):
        return url
    try:
        data = json.loads(_BAILIAN_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    base = str(data.get("base_url", "")).strip().rstrip("/")
    if base.startswith("https://"):
        return f"wss://{base[len('https://'):]}/api-ws/v1/inference"
    return ""


def tts_model() -> str:
    # 本账号 qwen-audio-3.1 合成未开通（"url error"），qwen3-tts-flash 实测可用
    return get("TTS_MODEL", "qwen3-tts-flash")


def tts_voice() -> str:
    return get("TTS_VOICE", "Cherry")


def asr_model() -> str:
    # 本账号 qwen-audio-3.1 同步版未开通，-message 流式版可用——见 asr.py
    return get("ASR_MODEL", "qwen-audio-3.1-asr-flash-message")
