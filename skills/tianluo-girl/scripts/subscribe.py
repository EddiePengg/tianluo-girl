"""事件监听：看终端上报了什么（联调用；也是未来大脑的事件入口）。

    python3 subscribe.py            # 看 evt + status
    python3 subscribe.py --cmd      # 连 cmd 一起看
"""
from __future__ import annotations

import argparse
import json
import time
import uuid

import conn


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--device", default=None)
    p.add_argument("--cmd", action="store_true", help="同时监听下行指令")
    a = p.parse_args()

    t = conn.topics(a.device)
    client = conn.connect("tianluo-sub-" + uuid.uuid4().hex[:6])
    client.subscribe(t["evt"])
    client.subscribe(t["status"])
    if a.cmd:
        client.subscribe(t["cmd"])

    def on_message(c, u, m):
        ts = time.strftime("%H:%M:%S")
        try:
            obj = json.loads(m.payload.decode())
            brief = json.dumps(obj, ensure_ascii=False)
        except (UnicodeDecodeError, json.JSONDecodeError):
            brief = f"<{len(m.payload)} bytes binary>"
        print(f"[{ts}] {m.topic}  {brief[:300]}", flush=True)

    client.on_message = on_message
    print(f"监听中… 终端={t['cmd'].split('/')[2]}  Ctrl-C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
