#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""龙虾门户（lx.pt2153.com 入口服务，端口 8100）
- GET /          导航页：分两组列出服务（龙虾本机 / 乌兰察布服务器），探活绿/灰点
- GET /menu/     每日菜单静态页（portal/menu.html，菜谱推送改更新此文件）
- 新增本机服务：改 LOCAL_SERVICES + Caddyfile 加路径路由
- 新增外部项目：只改 REMOTE_SERVICES（host:port 探活，0=不探）
"""
import json, os, socket, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8100
ROOT = os.path.dirname(os.path.abspath(__file__))
MENU_HTML = os.path.join(ROOT, "menu.html")

# ============ 🦞 龙虾本机服务（经 lx.pt2153.com:8443 路径分发） ============
LOCAL_SERVICES = [
    {"name": "海报",       "icon": "🖼️", "path": "/poster/",   "check": 8137, "desc": "家庭海报轮播"},
    {"name": "菜谱",       "icon": "🍚", "path": "/menu/",     "check": 0,    "desc": "每日菜单（饭谱与库存）"},
    {"name": "心理学100天", "icon": "📚", "path": "/psych100",  "check": 3100, "desc": "读书打卡 · 心理学进度"},
    {"name": "数学60周",   "icon": "🔢", "path": "/math60w/",  "check": 3200, "desc": "数学学习计划 · 游戏化打卡"},
    {"name": "书胃",       "icon": "📖", "path": "/bookqueue", "check": 8090, "desc": "待消化书单管理", "lock": True},
    {"name": "小P的每日一书", "icon": "🟥", "path": "/dailybook", "check": 3020, "desc": "每日荐书", "lock": True},
    {"name": "图书馆查询",  "icon": "🏠", "path": "/library/",  "check": 0,    "desc": "OPAC 馆藏检索结果", "lock": True},
    {"name": "健身动作库",  "icon": "💪", "path": None,         "check": 0,    "desc": "大屏页签内的动作卡片（非独立服务）"},
    {"name": "田螺姑娘",   "icon": "🖥️", "path": "__ext__",    "check": 0,    "desc": "家里的大屏终端", "external": "https://tianluo.pt2153.com"},
]

# ============ 🖧 乌兰察布服务器项目（pt2153.com 黄页） ============
REMOTE_SERVICES = [
    {"name": "NocoDB",     "icon": "📊", "path": "__ext__", "check": "nocodb.pt2153.com:443",   "desc": "表数据库（打卡/到期提醒/食材库存）", "external": "https://nocodb.pt2153.com"},
    {"name": "Directus",   "icon": "🗂️", "path": "__ext__", "check": "directus.pt2153.com:443", "desc": "无头 CMS · 日记系统", "external": "https://directus.pt2153.com"},
    {"name": "Memos",      "icon": "📝", "path": "__ext__", "check": "memos.pt2153.com:443",    "desc": "闪念 · 情绪日记", "external": "https://memos.pt2153.com"},
    {"name": "WebUI",      "icon": "💬", "path": "__ext__", "check": "webui.pt2153.com:443",    "desc": "和 AI 聊天", "external": "https://webui.pt2153.com"},
    {"name": "格物Lab",    "icon": "🧪", "path": "__ext__", "check": "gewu.pt2153.com:443",     "desc": "格物 Lab 工作区", "external": "http://gewu.pt2153.com"},
    {"name": "精力管理",   "icon": "⚡", "path": "__ext__", "check": "jlgl.pt2153.com:443",     "desc": "精力管理 · 自律打卡", "external": "https://jlgl.pt2153.com"},
    {"name": "游戏人生",   "icon": "🎮", "path": "__ext__", "check": "yxrs.pt2153.com:443",     "desc": "游戏人生 · 积分系统", "external": "https://yxrs.pt2153.com/login"},
    {"name": "HomeAssistant", "icon": "🏠", "path": "__ext__", "check": "hs.pt2153.com:443",    "desc": "智能家居控制", "external": "https://hs.pt2153.com"},
    {"name": "hmqs",       "icon": "📦", "path": "__ext__", "check": "hmqs.pt2153.com:443",     "desc": "独立项目", "external": "http://hmqs.pt2153.com"},
]

GROUPS = [
    ("🦞 龙虾 · 本机服务", LOCAL_SERVICES),
    ("🖧 乌兰察布 · 服务器项目", REMOTE_SERVICES),
]

_probe_cache = {"ts": 0, "result": []}


def probe_one(check):
    """check: int=本机端口 / "host:port"=外部 / 0=不探活(默认活)"""
    if not check:
        return True
    if isinstance(check, int):
        host, port = "127.0.0.1", check
    else:
        host, _, ps = str(check).partition(":")
        port = int(ps or 443)
    try:
        c = socket.create_connection((host, port), timeout=2.0)
        c.close()
        return True
    except OSError:
        return False


def probe_all():
    if time.time() - _probe_cache["ts"] < 10:
        return _probe_cache["result"]
    out = []
    for title, services in GROUPS:
        out.append({"group": title,
                    "items": [{**s, "alive": probe_one(s["check"])} for s in services]})
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
  .sub {{ color:#8b949e; font-size:13px; margin-bottom:20px; }}
  h2 {{ font-size:15px; color:#58a6ff; margin:22px 0 12px; font-weight:600;
       border-bottom:1px solid #21262d; padding-bottom:8px; max-width:920px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:14px; max-width:920px; }}
  a.card {{ display:block; background:#161b22; border:1px solid #30363d; border-radius:12px;
           padding:18px; text-decoration:none; color:inherit; transition:border-color .15s, transform .15s; }}
  a.card:hover {{ border-color:#58a6ff; transform:translateY(-2px); }}
  a.card.disabled {{ opacity:.45; pointer-events:none; }}
  .icon {{ font-size:28px; }}
  .name {{ font-size:16px; margin:8px 0 4px; }}
  .desc {{ color:#8b949e; font-size:12px; line-height:1.5; min-height:36px; }}
  .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
  .on {{ background:#3fb950; }} .off {{ background:#f85149; }}
  .status {{ font-size:11px; color:#8b949e; margin-top:10px; }}
  .lock {{ float:right; font-size:11px; color:#c9a227; border:1px solid #c9a22755; padding:1px 6px; border-radius:6px; }}
</style>
</head>
<body>
  <h1>🦞 龙虾门户</h1>
  <div class="sub">lx.pt2153.com:8443 · 公网入口 · 绿点=在线 / 红点=离线 · 🔒=需登录</div>
  {groups}
</body>
</html>
"""

CARD = """<a class="card{disabled}" href="{href}" {target}>
      <div class="icon">{icon}</div>
      <div class="name">{name}{lock}</div>
      <div class="desc">{desc}</div>
      <div class="status">{dot}{status}</div>
    </a>"""

GROUP = """<h2>{title}</h2>
  <div class="grid">
    {cards}
  </div>"""


def render():
    groups_html = []
    for g in probe_all():
        cards = []
        for s in g["items"]:
            href = s.get("external") or s.get("path") or "#"
            external = bool(s.get("external"))
            cards.append(CARD.format(
                disabled="" if (s["alive"] and s.get("path") or external) else " disabled",
                href=href,
                target='target="_blank"' if external else "",
                icon=s["icon"], name=s["name"],
                lock='<span class="lock">🔒</span>' if s.get("lock") else "",
                desc=s["desc"],
                dot='<span class="dot {}"></span>'.format("on" if s["alive"] else "off"),
                status="在线" if s["alive"] else "离线",
            ))
        groups_html.append(GROUP.format(title=g["group"], cards="\n    ".join(cards)))
    return PAGE_TMPL.format(groups="\n  ".join(groups_html))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._send(200, "text/html; charset=utf-8", render())
        elif self.path.startswith("/menu"):
            if os.path.exists(MENU_HTML):
                with open(MENU_HTML, "rb") as f:
                    self._send(200, "text/html; charset=utf-8", f.read())
            else:
                self._send(404, "text/plain; charset=utf-8", "menu.html not found")
        else:
            self._send(404, "text/plain; charset=utf-8", "not found")


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print("[portal] 龙虾门户 0.0.0.0:%d" % PORT, flush=True)
    srv.serve_forever()
