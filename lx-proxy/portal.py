#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""龙虾门户（lx.pt2153.com 入口服务，端口 8100）
- GET /          导航页：列出当前运行的服务，探测端口活性（绿/灰），点击进入
- GET /menu/     每日菜单静态页（portal/menu.html，菜谱推送改更新此文件）
- 新增服务：改 SERVICES 清单 + Caddyfile 加路径路由
"""
import json, os, socket, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8100
ROOT = os.path.dirname(os.path.abspath(__file__))
MENU_HTML = os.path.join(ROOT, "menu.html")

# 服务清单：check=探活端口（0=无需探活），external=站外链接
SERVICES = [
    {"name": "海报",       "icon": "🖼️", "path": "/poster/",   "check": 8137, "desc": "家庭海报轮播"},
    {"name": "菜谱",       "icon": "🍚", "path": "/menu/",     "check": 0,    "desc": "每日菜单（饭谱与库存）"},
    {"name": "心理学100天", "icon": "📚", "path": "/psych100",  "check": 3100, "desc": "读书打卡 · 心理学进度"},
    {"name": "数学60周",   "icon": "🔢", "path": "/math60w/",  "check": 3200, "desc": "数学学习计划 · 游戏化打卡"},
    {"name": "健身动作库", "icon": "💪", "path": None,         "check": 0,    "desc": "大屏页签内的动作卡片（非独立服务）"},
    {"name": "田螺姑娘",   "icon": "🖥️", "path": "__ext__",    "check": 0,    "desc": "家里的大屏终端", "external": "https://tianluo.pt2153.com"},
]

_probe_cache = {"ts": 0, "result": []}

def probe_all():
    if time.time() - _probe_cache["ts"] < 10:
        return _probe_cache["result"]
    out = []
    for s in SERVICES:
        ok = True
        if s["check"]:
            try:
                c = socket.create_connection(("127.0.0.1", s["check"]), timeout=1.5)
                c.close()
            except OSError:
                ok = False
        out.append({**s, "alive": ok})
    _probe_cache["ts"] = time.time()
    _probe_cache["result"] = out
    return out

PAGE_TMPL = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>龙虾 · 服务导航</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:100%; min-height:100vh; background:#0d1117; color:#e6edf3;
         font-family:"Microsoft YaHei",system-ui,sans-serif; padding:24px; }}
  h1 {{ font-size:22px; margin-bottom:4px; }}
  .sub {{ color:#8b949e; font-size:13px; margin-bottom:24px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:14px; max-width:900px; }}
  a.card {{ display:block; background:#161b22; border:1px solid #30363d; border-radius:12px;
           padding:18px; text-decoration:none; color:inherit; transition:border-color .15s, transform .15s; }}
  a.card:hover {{ border-color:#58a6ff; transform:translateY(-2px); }}
  a.card.disabled {{ opacity:.45; pointer-events:none; }}
  .icon {{ font-size:28px; }}
  .name {{ font-size:16px; margin:8px 0 4px; }}
  .desc {{ color:#8b949e; font-size:12px; line-height:1.5; }}
  .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
  .on {{ background:#3fb950; }} .off {{ background:#f85149; }}
  .status {{ font-size:11px; color:#8b949e; margin-top:10px; }}
</style>
</head>
<body>
<h1>🦞 龙虾</h1>
<div class="sub">lx.pt2153.com · 内网服务公网出口 · 当前运行 {n_ok}/{n_all} 个服务</div>
<div class="grid">
{cards}
</div>
</body>
</html>
"""

def render():
    items = probe_all()
    cards = []
    for s in items:
        if s["path"] == "__ext__":
            href, target, cls = s["external"], ' target="_blank"', ""
            st = '<span class="status">外部站点 ↗</span>'
        elif s["path"] is None:
            href, target, cls = "#", "", " disabled"
            st = f'<span class="status"><span class="dot on"></span>随大屏页签提供</span>'
        else:
            state = f'<span class="dot on"></span>运行中' if s["alive"] else '<span class="dot off"></span>离线'
            st = f'<span class="status">{state}</span>'
            href, target, cls = s["path"], "", "" if s["alive"] else " disabled"
        cards.append(
            f'<a class="card{cls}" href="{href}"{target}>'
            f'<div class="icon">{s["icon"]}</div>'
            f'<div class="name">{s["name"]}</div>'
            f'<div class="desc">{s["desc"]}</div>{st}</a>'
        )
    alive_n = sum(1 for s in items if s["alive"])
    return PAGE_TMPL.format(cards="\n".join(cards), n_ok=alive_n, n_all=len(items))

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静默
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/services":
            return self._send(200, json.dumps(probe_all(), ensure_ascii=False), "application/json; charset=utf-8")
        if p.rstrip("/") == "/menu":
            if os.path.isfile(MENU_HTML):
                return self._send(200, open(MENU_HTML, encoding="utf-8").read())
            return self._send(404, "菜单还没推送（portal/menu.html 不存在）")
        return self._send(200, render())

if __name__ == "__main__":
    print(f"[portal] 龙虾门户 0.0.0.0:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
