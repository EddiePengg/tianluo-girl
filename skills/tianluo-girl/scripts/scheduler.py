"""定时推送：每晚 MEALPLAN_PUSH_TIME（默认 22:00）把"明天的饭食计划"推到终端。

    python3 scheduler.py --now            # 立即推一次（联调）
    python3 scheduler.py                  # 常驻，每天定时推
    python3 scheduler.py --date 2026-10-16 --now   # 指定日期
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import uuid
from datetime import datetime, timedelta

import conn
import mealplan
from publish import envelope
from tts import TTSError, synthesize


def build_msgs(entry: dict, speak: bool = True) -> list[dict]:
    msgs = [envelope("card",
                     title=f"明日饭食 · {entry['dinner']}",
                     items=entry.get("prep", []),
                     priority="normal")]
    if speak and entry.get("prep"):
        text = f"明天的晚饭是{entry['dinner']}。准备工作：{'；'.join(entry['prep'])}。"
        try:
            audio, fmt = synthesize(text)
        except TTSError as e:
            print(f"[tts 失败，只发卡] {e}", file=sys.stderr)
            return msgs
        msgs.append(envelope("speak", text=text,
                             audio_b64=base64.b64encode(audio).decode(),
                             format=fmt, interrupt=True))
    return msgs


def push(msgs: list[dict], device: str | None = None) -> None:
    t = conn.topics(device)
    client = conn.connect("tianluo-scheduler-" + uuid.uuid4().hex[:6])
    for m in msgs:
        client.publish(t["cmd"], json.dumps(m, ensure_ascii=False), qos=1) \
             .wait_for_publish(timeout=10)
        print(f"[push] {m['type']}: {(m.get('title') or m.get('text') or '')[:50]}")
    client.loop_stop()
    client.disconnect()


def seconds_until(hhmm: str) -> float:
    hh, mm = int(hhmm[:2]), int(hhmm[3:5])
    now = datetime.now()
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--now", action="store_true", help="立即推一次后退出")
    p.add_argument("--date", default=None, help="把哪天当'明天'：YYYY-MM-DD")
    p.add_argument("--time", dest="push_time", default=None,
                   help="推送时刻 HH:MM（默认读 MEALPLAN_PUSH_TIME，缺省 22:00）")
    p.add_argument("--no-speak", action="store_true")
    p.add_argument("--device", default=None)
    a = p.parse_args()

    target_date = a.date or (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    entry = mealplan.get(target_date)
    if not entry:
        print(f"[plan] {target_date} 没有饭食计划，跳过")
        if a.now:
            return
        # 常驻模式下没计划也继续等明天
    if a.now:
        if entry:
            push(build_msgs(entry, speak=not a.no_speak), device=a.device)
        return

    push_time = a.push_time or __import__("os").environ.get("MEALPLAN_PUSH_TIME", "22:00")
    print(f"[scheduler] 每天 {push_time} 推送次日计划，Ctrl-C 退出")
    while True:
        wait = seconds_until(push_time)
        print(f"[scheduler] 下次推送：{push_time}（{int(wait // 3600)}h{int(wait % 3600 // 60)}m 后）")
        time.sleep(wait)
        d = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        entry = mealplan.get(d)
        if entry:
            try:
                push(build_msgs(entry, speak=not a.no_speak), device=a.device)
            except Exception as e:  # 单点失败不退出常驻循环
                print(f"[push 失败] {e}", file=sys.stderr)
        else:
            print(f"[plan] {d} 没有饭食计划，跳过")


if __name__ == "__main__":
    main()
