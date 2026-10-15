"""TTS：百炼多模态生成 API 合成语音。

链路（参考 gaga-ai 已实测配置）：POST /aigc/multimodal-generation/generation
→ output.audio.url（OSS wav，24h 有效）→ 立即下载 → 有 ffmpeg 则转 ogg_opus 24k
（MQTT 省流：10s ≈ 40KB vs wav 480KB）→ 返回 (bytes, format)。
注意：本账号 qwen-audio-3.1 / 3.0-tts-flash 未开通（"url error"），默认 qwen3-tts-flash。
"""
from __future__ import annotations

import shutil
import subprocess

import httpx

from config import dashscope_api_key, tts_model, tts_voice

_TTS_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
_MAX_TEXT = 500          # API 限 512 token，中文一字≈一 token，留余量
_HTTP_TIMEOUT = 60.0
# base64 膨胀 33% 后须 ≤1MB（broker 上限）→ 原始音频软上限 700KB
_MAX_AUDIO_BYTES = 700 * 1024


class TTSError(Exception):
    pass


def synthesize(text: str, voice: str | None = None) -> tuple[bytes, str]:
    """文本 → (音频字节, format: ogg|wav)。失败抛 TTSError。"""
    text = (text or "").strip()[:_MAX_TEXT]
    if not text:
        raise TTSError("空文本")
    api_key = dashscope_api_key()
    if not api_key:
        raise TTSError("缺 DASHSCOPE_API_KEY（或 ~/.bailian/config.json 未登录）")

    body = {
        "model": tts_model(),
        "input": {"text": text, "voice": voice or tts_voice(),
                  "language_type": "Chinese"},
    }
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.post(
                _TTS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            )
            data = resp.json()
            if resp.status_code != 200:
                raise TTSError(str(data.get("message")
                                   or f"HTTP {resp.status_code}")[:300])
            url = data.get("output", {}).get("audio", {}).get("url")
            if not url:
                raise TTSError(str(data.get("message")
                                   or "响应缺 output.audio.url")[:300])
            wav = client.get(url).content
    except httpx.HTTPError as e:
        raise TTSError(f"请求失败: {e}") from e
    if not wav:
        raise TTSError("音频下载为空")

    audio, fmt = _to_ogg_opus(wav)
    if len(audio) > _MAX_AUDIO_BYTES:
        raise TTSError(f"音频过大：{len(audio)} bytes（上限 {_MAX_AUDIO_BYTES}）")
    return audio, fmt


def _to_ogg_opus(wav: bytes) -> tuple[bytes, str]:
    """wav → ogg_opus 24kHz 单声道；无 ffmpeg 时原样返回 wav。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return wav, "wav"
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error",
         "-f", "wav", "-i", "pipe:0",
         "-ac", "1", "-ar", "24000", "-c:a", "libopus",
         "-b:a", "32k", "-application", "audio",
         "-f", "ogg", "pipe:1"],
        input=wav, capture_output=True, timeout=60)
    if proc.returncode != 0 or not proc.stdout:
        return wav, "wav"
    return proc.stdout, "ogg"
