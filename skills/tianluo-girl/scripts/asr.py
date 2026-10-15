"""ASR：百炼 qwen-audio-3.1-asr-flash-message 流式识别（Fun-ASR WebSocket 协议）。

链路（参考 gaga-ai 已实测配置，原生实现不引 SDK）：
    ffmpeg 统一解码成 PCM 16kHz 单声道 s16le
    → WS 连接（Bearer 鉴权，地址从 ~/.bailian/config.json base_url 推导）
    → run-task → 二进制 PCM 帧（100ms 组）→ finish-task
    → result-generated（sentence_end=true 逐句定稿，带润色）→ task-finished
本账号实测：qwen-audio-3.1 同步版未开通（"url error"），-message 流式版可用。
"""
from __future__ import annotations

import asyncio
import base64
import json
import shutil
import subprocess
import uuid

import websockets

from config import asr_model, dashscope_api_key, dashscope_ws_url

_PCM_RATE = 16000
_GROUP_MS = 100
_GROUP_BYTES = _PCM_RATE * 2 * _GROUP_MS // 1000   # 3200 字节/组
_START_TIMEOUT = 10.0
_TAIL_TIMEOUT = 15.0

_MAX_AUDIO = 60 * 1024 * 1024   # ffmpeg 解码前的输入上限（60MB 兜底）


class ASRError(Exception):
    pass


def _to_pcm16k(audio: bytes, fmt: str) -> bytes:
    """任意音频（webm/opus、ogg、mp3、wav…）→ PCM 16kHz 单声道 s16le。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ASRError("缺 ffmpeg（用于把录音统一解码成 PCM 16k）")
    # fmt 只作容器提示，ffmpeg 自动探测；webm/opus 给 audio/webm
    probe = {"webm/opus": "webm", "webm": "webm"}.get(fmt)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    if probe:
        cmd += ["-f", "webm", "-safe", "0"]
    cmd += ["-i", "pipe:0", "-ac", "1", "-ar", str(_PCM_RATE),
            "-f", "s16le", "pipe:1"]
    proc = subprocess.run(cmd, input=audio, capture_output=True, timeout=60)
    if proc.returncode != 0 or not proc.stdout:
        raise ASRError(f"ffmpeg 解码失败: {proc.stderr.decode('utf-8', 'replace')[:200]}")
    return proc.stdout


def transcribe(audio: bytes, fmt: str = "webm/opus") -> str:
    """音频字节 → 转写文本（整段定稿）。失败抛 ASRError。"""
    if not audio:
        raise ASRError("空音频")
    if len(audio) > _MAX_AUDIO:
        raise ASRError(f"音频过大：{len(audio)} bytes")
    api_key = dashscope_api_key()
    ws_url = dashscope_ws_url()
    if not api_key or not ws_url:
        raise ASRError("缺 DASHSCOPE_API_KEY / WS 地址（~/.bailian/config.json 未登录？）")
    pcm = _to_pcm16k(audio, fmt)
    if not pcm:
        raise ASRError("解码后无 PCM 数据")
    return asyncio.run(_run(pcm, api_key, ws_url))


async def _run(pcm: bytes, api_key: str, ws_url: str) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        ws = await websockets.connect(
            ws_url, additional_headers=headers, proxy=None,
            open_timeout=10, max_size=2**22)
    except Exception as e:
        raise ASRError(f"WS 建连失败: {e}") from e

    task_id = str(uuid.uuid4())
    texts: list[str] = []
    started = asyncio.Event()

    async def send(action: str, payload: dict) -> None:
        await ws.send(json.dumps({
            "header": {"action": action, "task_id": task_id,
                       "streaming": "duplex"},
            "payload": payload,
        }, ensure_ascii=False))

    async def sender() -> None:
        await asyncio.wait_for(started.wait(), timeout=_START_TIMEOUT)
        # ~4x 速上行：每组 100ms PCM 间隔 25ms
        for off in range(0, len(pcm), _GROUP_BYTES):
            await ws.send(pcm[off:off + _GROUP_BYTES])
            await asyncio.sleep(0.025)
        await send("finish-task", {"input": {}})

    async def receiver() -> None:
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=_TAIL_TIMEOUT)
            evt = json.loads(raw)
            header, payload = evt.get("header") or {}, evt.get("payload") or {}
            action = header.get("action") or header.get("event")
            if action == "task-started":
                started.set()
            elif action == "task-failed":
                raise ASRError(f"{header.get('error_code')}: "
                               f"{header.get('error_message')}")
            elif action == "result-generated":
                sentence = (payload.get("output") or {}).get("sentence") or {}
                if sentence.get("sentence_end") and sentence.get("text"):
                    texts.append(sentence["text"])
            elif action == "task-finished":
                return

    try:
        await send("run-task", {
            "task_group": "audio", "task": "asr", "function": "recognition",
            "model": asr_model(),
            "parameters": {
                "format": "pcm", "sample_rate": _PCM_RATE,
                "disfluency_removal_enabled": True,   # 去语气词/润色
            },
            "input": {},
        })
        await asyncio.gather(sender(), receiver())
    except asyncio.TimeoutError as e:
        raise ASRError("识别超时") from e
    finally:
        await ws.close()

    text = "".join(texts).strip()
    if not text:
        raise ASRError("识别结果为空（可能全程静音）")
    return text


if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    p = argparse.ArgumentParser(description="识别一段音频文件（webm/opus/ogg/mp3/wav）")
    p.add_argument("file", help="音频文件路径")
    p.add_argument("--format", default=None,
                   help="如 webm/opus（默认按扩展名猜）")
    a = p.parse_args()

    path = Path(a.file)
    fmt = a.format or path.suffix.lstrip(".") or "webm/opus"
    try:
        print(transcribe(path.read_bytes(), fmt))
    except ASRError as e:
        print(f"ASR 失败: {e}", file=sys.stderr)
        sys.exit(1)
