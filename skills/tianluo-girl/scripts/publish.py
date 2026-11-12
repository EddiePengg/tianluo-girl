"""发指令 CLI（联调入口，也是 AI Agent 的标准调用方式）。

示例：
    python3 publish.py card --title "明日晚饭" --item "17:30 解冻牛排"
    python3 publish.py speak "该准备明天的饭啦"
    python3 publish.py html --file notice.html --until "+2h"
    python3 publish.py image --file menu.jpg
    python3 publish.py clear --wait-ack 5
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import conn
from tts import TTSError, synthesize


def envelope(type_: str, **fields) -> dict:
    msg = {"v": 1, "type": type_,
           "id": uuid.uuid4().hex[:16],
           "sent_at": datetime.now().astimezone().isoformat()}
    msg.update(fields)
    return msg


def parse_until(s: str | None) -> str | None:
    """支持 ISO 字符串或 '+30m'/'+2h' 相对时长。"""
    if not s:
        return None
    if s.startswith("+"):
        n, unit = int(s[1:-1]), s[-1]
        delta = timedelta(hours=n) if unit == "h" else timedelta(minutes=n)
        return (datetime.now().astimezone() + delta).isoformat()
    return s


def publish(msg: dict, device: str | None = None, wait_ack: float = 0) -> dict | None:
    """发布一条 cmd；wait_ack>0 时等终端回执并返回 ack dict（超时返回 None）。"""
    t = conn.topics(device)
    client = conn.connect("tianluo-cli-" + uuid.uuid4().hex[:6])
    got: dict = {}

    if wait_ack > 0:
        def on_message(c, u, m):
            try:
                obj = json.loads(m.payload.decode())
            except (UnicodeDecodeError, json.JSONDecodeError):
                return
            if obj.get("type") == "ack" and obj.get("cmd_id") == msg["id"]:
                got["ack"] = obj
        client.on_message = on_message
        client.subscribe(t["evt"])

    client.publish(t["cmd"], json.dumps(msg, ensure_ascii=False), qos=1) \
         .wait_for_publish(timeout=10)

    deadline = time.time() + wait_ack
    while wait_ack > 0 and time.time() < deadline and "ack" not in got:
        time.sleep(0.05)

    client.loop_stop()
    client.disconnect()
    return got.get("ack")


def read_file(path: str) -> bytes:
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"文件不存在: {path}")
    return p.read_bytes()


def guess_format(path: str, default: str) -> str:
    ext = Path(path).suffix.lower().lstrip(".")
    return {"jpg": "jpeg", "jpeg": "jpeg", "png": "png"}.get(ext, default)


def main() -> None:
    p = argparse.ArgumentParser(prog="publish.py", description="向田螺姑娘终端发指令")
    # 公共选项放在子命令里，publish.py card ... --wait-ack 5 这种顺序也能用
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--device", default=None, help="终端 ID（默认 girl-01）")
    common.add_argument("--dry-run", action="store_true", help="只打印 JSON 不发送")
    common.add_argument("--wait-ack", type=float, default=0, help="等待回执秒数")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("card", parents=[common], help="显示卡片")
    c.add_argument("--title", required=True)
    c.add_argument("--item", action="append", default=[], help="条目，可多次")
    c.add_argument("--mode", choices=["fullscreen", "banner"], default="fullscreen")
    c.add_argument("--until", default=None, help="过期时间：ISO 或 '+30m'/'+2h'")
    c.add_argument("--priority", choices=["normal", "high"], default="normal")

    s = sub.add_parser("speak", parents=[common], help="语音播报（自动 TTS）")
    s.add_argument("text")
    s.add_argument("--voice", default=None)
    s.add_argument("--no-interrupt", action="store_true")

    h = sub.add_parser("html", parents=[common], help="显示自定义网页")
    h.add_argument("--html", default=None)
    h.add_argument("--file", default=None, help="HTML 文件路径")
    h.add_argument("--until", default=None)
    h.add_argument("--ttl", type=int, default=None, help="多少秒后自动关闭（临时层）")

    i = sub.add_parser("image", parents=[common], help="显示图片")
    i.add_argument("--file", required=True)
    i.add_argument("--format", default=None, help="jpeg/png（默认按扩展名）")
    i.add_argument("--until", default=None)
    i.add_argument("--ttl", type=int, default=None, help="多少秒后自动关闭（临时层）")

    so = sub.add_parser("sound", parents=[common], help="播提示音")
    so.add_argument("--name", choices=["ding", "chime"], default="ding")

    l = sub.add_parser("listen", parents=[common], help="对话回合交接")
    l.add_argument("--timeout", type=int, default=10)

    v = sub.add_parser("volume", parents=[common], help="音量")
    v.add_argument("level", type=int)

    sc = sub.add_parser("screen", parents=[common], help="屏幕控制")
    sc.add_argument("state", choices=["on", "off", "keep_awake"])

    sub.add_parser("clear", parents=[common], help="清除显示，回待机")

    sl = sub.add_parser("slot", parents=[common], help="常驻页签槽管理")
    sl_sub = sl.add_subparsers(dest="slot_action", required=True)
    ss = sl_sub.add_parser("set", parents=[common], help="建立/更新页签（--kind url 外链 / html 内嵌）")
    ss.add_argument("--id", required=True, help="槽 ID（如 poster/menu/checkin）")
    ss.add_argument("--label", default=None, help="显示名（默认同 id）")
    ss.add_argument("--icon", default=None, help="图标 emoji（默认 📄）")
    ss.add_argument("--kind", choices=["url", "html"], default="url")
    ss.add_argument("--url", default=None)
    ss.add_argument("--html", default=None, help="HTML 字符串")
    ss.add_argument("--html-file", default=None, help="HTML 文件路径")
    ss.add_argument("--activate", action="store_true", help="推送后激活显示")
    sa = sl_sub.add_parser("activate", parents=[common], help="切换到指定页签")
    sa.add_argument("--id", required=True)
    sr = sl_sub.add_parser("remove", parents=[common], help="删除页签")
    sr.add_argument("--id", required=True)
    sl_sub.add_parser("clear", parents=[common], help="清空所有页签，回时钟")

    a = p.parse_args()

    msg: dict
    if a.cmd == "card":
        display = {"mode": a.mode}
        if until := parse_until(a.until):
            display["until"] = until
        msg = envelope("card", title=a.title, items=a.item,
                       display=display, priority=a.priority)
    elif a.cmd == "speak":
        if a.dry_run:
            msg = envelope("speak", text=a.text, format="mp3", interrupt=True)
        else:
            try:
                audio, fmt = synthesize(a.text, voice=a.voice)
            except TTSError as e:
                raise SystemExit(f"TTS 失败: {e}")
            msg = envelope("speak", text=a.text,
                           audio_b64=base64.b64encode(audio).decode(),
                           format=fmt, interrupt=not a.no_interrupt)
            print(f"[tts] 合成 {len(audio)} bytes ({fmt})", file=sys.stderr)
    elif a.cmd == "html":
        html = a.html or (read_file(a.file).decode("utf-8") if a.file else None)
        if not html:
            raise SystemExit("html: 需要 --html 或 --file")
        msg = envelope("html", html=html)
        if a.ttl:
            msg["ttl"] = a.ttl
        elif until := parse_until(a.until):
            msg["display"] = {"until": until}
    elif a.cmd == "image":
        data = read_file(a.file)
        if len(data) > 700 * 1024:
            raise SystemExit(f"图片过大：{len(data)} bytes（base64 后须 ≤1MB）")
        msg = envelope("image", image_b64=base64.b64encode(data).decode(),
                       format=a.format or guess_format(a.file, "jpeg"))
        if a.ttl:
            msg["ttl"] = a.ttl
        elif until := parse_until(a.until):
            msg["display"] = {"until": until}
    elif a.cmd == "sound":
        msg = envelope("sound", name=a.name)
    elif a.cmd == "listen":
        msg = envelope("listen", timeout_s=a.timeout)
    elif a.cmd == "volume":
        msg = envelope("volume", level=a.level)
    elif a.cmd == "screen":
        msg = envelope("screen", state=a.state)
    elif a.cmd == "slot":
        if a.slot_action == "set":
            if a.kind == "url" and not a.url:
                raise SystemExit("slot set --kind url 需要 --url")
            if a.kind == "html" and not (a.html or a.html_file):
                raise SystemExit("slot set --kind html 需要 --html 或 --html-file")
            html = None
            if a.kind == "html":
                html = a.html or read_file(a.html_file).decode("utf-8")
            msg = envelope("slot", action="set", slot_id=a.id,
                           label=a.label or a.id, icon=a.icon or "📄",
                           kind=a.kind)
            if a.kind == "url":
                msg["url"] = a.url
            else:
                msg["html"] = html
            if a.activate:
                msg["activate"] = True
        elif a.slot_action == "activate":
            msg = envelope("slot", action="activate", slot_id=a.id)
        elif a.slot_action == "remove":
            msg = envelope("slot", action="remove", slot_id=a.id)
        else:
            msg = envelope("slot", action="clear")
    else:  # clear
        msg = envelope("clear")

    if a.dry_run:
        print(json.dumps(msg, ensure_ascii=False, indent=2)[:800])
        return

    ack = publish(msg, device=a.device, wait_ack=a.wait_ack)
    print(f"[pub] {a.cmd} → tianluo/terminal/{a.device or 'girl-01'}/cmd (id={msg['id']})")
    if a.wait_ack > 0:
        print(f"[ack] {ack['result'] if ack else '超时未收到'}")


if __name__ == "__main__":
    main()
