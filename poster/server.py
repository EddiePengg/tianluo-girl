# -*- coding: utf-8 -*-
"""田螺姑娘海报轮播服务

读 NocoDB「当前海报」表 -> 提供轮播网页 + 文件代理。
token 只存在本文件（服务端），推给大屏的 HTML 里不含任何凭据。

启动: python server.py   (默认 0.0.0.0:8137, HTTPS)
"""
import json
import os
import threading
import time
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import requests

warnings.filterwarnings("ignore")

NOCODB = "https://nocodb.pt2153.com"
TOKEN = "7_Ez69czjupNfAtNYwFCVqC3K4mYhTIqzsUM8nFt"
BASE_ID = "pq5z1fyvctx4p5x"
TABLE_ID = "m5naksvn8zldcng"
PORT = 8137
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
LIST_TTL = 60          # 海报列表缓存秒数
os.makedirs(CACHE_DIR, exist_ok=True)

_state = {"list": None, "ts": 0}
_lock = threading.Lock()


# ---------------- 数据 ----------------
def fetch_posters():
    """从 NocoDB 拉海报列表，按标题（日期前缀）排序"""
    r = requests.get(
        f"{NOCODB}/api/v3/data/{BASE_ID}/{TABLE_ID}/records?limit=200",
        headers={"xc-token": TOKEN}, verify=False, timeout=25)
    r.raise_for_status()
    items = []
    for rec in r.json().get("records", []):
        f = rec.get("fields") or {}
        if not f.get("is_show"):        # 只显示打了对号（激活）的
            continue
        for a in (f.get("Attachment") or []):
            mime = (a.get("mimetype") or "").lower()
            if mime.startswith("video"):
                kind = "video"
            elif mime.startswith("image"):
                kind = "image"
            else:
                continue                      # 其它类型跳过
            items.append({
                "title": f.get("Title") or a.get("title") or "",
                "kind": kind,
                "path": a.get("path") or "",
                "name": a.get("title") or "",
                "size": a.get("size") or 0,
            })
    items.sort(key=lambda x: x["title"])       # 251207 < 260103 ... 按日期轮
    return items


def get_posters(force=False):
    with _lock:
        if not force and _state["list"] is not None and time.time() - _state["ts"] < LIST_TTL:
            return _state["list"]
        try:
            _state["list"] = fetch_posters()
            _state["ts"] = time.time()
        except Exception as e:
            print("[list] 拉取失败:", e)
            if _state["list"] is None:
                _state["list"] = []
        return _state["list"]


def get_file(path):
    """服务端代理下载附件，落本地缓存（token 不出本机）"""
    safe = path.replace("/", "_").replace("\\", "_")
    local = os.path.join(CACHE_DIR, safe)
    if os.path.exists(local) and os.path.getsize(local) > 0:
        return local, None
    r = requests.get(f"{NOCODB}/{path}", headers={"xc-token": TOKEN},
                     verify=False, timeout=60)
    if r.status_code != 200:
        return None, f"下载失败 {r.status_code}"
    with open(local, "wb") as fh:
        fh.write(r.content)
    return local, None


# ---------------- 运动动作库页（常驻页签） ----------------
# 数据来源：wger.de 开源健身数据库（CC 授权）+ 本地 GIF + 经典动作自填

def _exercise_page():
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>运动动作库</title>'
        '<style>'
        'body{margin:0;background:#0d1117;color:#e6edf3;font-family:"PingFang SC","Microsoft YaHei",sans-serif;padding:16px 18px}'
        'h1{font-size:clamp(26px,3.2vw,42px);margin:4px 4px 10px;color:#f0883e}'
        '#searchBox{width:100%;box-sizing:border-box;background:#161b22;border:2px solid #f0883e;border-radius:14px;color:#e6edf3;font-size:clamp(20px,2.4vw,32px);padding:14px 18px;outline:none;margin:6px 0 12px;font-family:inherit}'
        '#searchBox::placeholder{color:#484f58}'
        '#searchMeta{font-size:clamp(13px,1.4vw,17px);color:#8b949e;margin:0 4px 8px}'
        '.srow{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:12px 14px;margin-bottom:10px}'
        '.sname{font-size:clamp(18px,2vw,26px);font-weight:800}'
        '.smeta{font-size:clamp(13px,1.4vw,17px);color:#8b949e;margin-top:3px}'
        '.smuscles{margin-top:6px;display:flex;gap:6px;flex-wrap:wrap}'
        '.sm{background:#1f6feb;color:#fff;border-radius:10px;padding:2px 10px;font-size:clamp(12px,1.3vw,16px)}'
        '.sm2{background:#21262d;color:#8b949e;border-radius:10px;padding:2px 8px;font-size:clamp(11px,1.2vw,14px)}'
        '.sdesc{font-size:clamp(13px,1.4vw,17px);color:#8b949e;margin-top:6px}'
        '.sins{font-size:clamp(13px,1.4vw,17px);color:#c9d1d9;margin-top:6px;padding-left:20px}'
        '.sins li{margin:3px 0}'
        '.sgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}'
        '.scard{background:linear-gradient(165deg,#161b22,#0b0e13);border:1px solid #30363d;border-radius:16px;overflow:hidden;transition:border-color .15s,transform .15s}'
        '.scard:hover{border-color:#f0883e;transform:translateY(-2px)}'
        '.svideo{position:relative;background:#000;aspect-ratio:4/3;display:flex;align-items:center;justify-content:center;border-bottom:1px solid #30363d}'
        '.svideo video{width:100%;height:100%;object-fit:contain}'
        '.svideo .ph{font-size:60px;opacity:.4}'
        '.sbody{padding:12px 14px 14px}'
        '.stag{display:inline-block;background:#21262d;color:#8b949e;border-radius:8px;padding:3px 9px;font-size:clamp(11px,1.1vw,13px);margin:0 6px 4px 0}'
        '.sins{max-height:72px;overflow:hidden;position:relative;cursor:pointer;margin:8px 0 0}'
        '.sins:not(.open)::after{content:"点击展开全部步骤 ▾";position:absolute;bottom:0;left:0;right:0;padding:14px 0 2px;text-align:center;font-size:12px;color:#f0883e;background:linear-gradient(transparent,#0b0e13 60%)}'
        '.sins.open{max-height:none;cursor:default}'
        '.sins.open::after{content:""}'
        '.tabs{display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap}'
        '.tab{background:#161b22;border:1px solid #30363d;color:#e6edf3;border-radius:12px;padding:10px 22px;font-size:clamp(18px,2vw,26px);cursor:pointer;font-weight:700}'
        '.tab.on{background:#f0883e;color:#0d1117;border-color:#f0883e}'
        '.chips{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}'
        '.chip{background:#21262d;border:1px solid #30363d;color:#8b949e;border-radius:20px;padding:5px 14px;font-size:clamp(14px,1.5vw,19px);cursor:pointer}'
        '.chip.on{background:#238636;color:#fff;border-color:#238636}'
        '.cnt{color:#8b949e;font-size:clamp(14px,1.5vw,18px);margin-left:auto}'
        '.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}'
        '.card{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:12px;text-align:center}'
        'img{width:100%;max-height:30vh;object-fit:contain;border-radius:10px;background:#000}'
        '.noimg{font-size:64px;line-height:150px;background:#0d1117;border-radius:10px}'
        '.name{font-size:clamp(20px,2.2vw,30px);font-weight:800;margin-top:8px}'
        '.nen{font-size:clamp(13px,1.3vw,16px);color:#484f58;margin-top:2px}'
        '.muscles{margin-top:6px;display:flex;gap:6px;justify-content:center;flex-wrap:wrap}'
        '.m{background:#238636;color:#fff;border-radius:12px;padding:3px 12px;font-size:clamp(14px,1.4vw,18px);font-weight:700}'
        '.m2{background:#21262d;color:#8b949e;border-radius:12px;padding:3px 10px;font-size:clamp(12px,1.2vw,15px)}'
        '.tip{font-size:clamp(14px,1.5vw,19px);color:#8b949e;margin-top:8px;text-align:left}'
        '</style></head><body>'
        '<h1>🏃 运动动作库 <span class="cnt" id="cnt"></span></h1>'
        '<input id=searchBox type=text placeholder="🔍 搜索 6554 个动作：名称 / 肌肉 / 器械 / 部位（如：弹力带划船、股四头肌、dumbbell）" autocomplete=off>'
        '<div id=searchMeta></div>'
        '<div id=searchResults></div>'
        '<div class="tabs" id="tabs"></div>'
        '<div class="chips" id="chips"></div>'
        '<div class="grid" id="grid"></div>'
        '<script>'
        'var LIB=null;fetch("exercise-lib.json").then(function(r){return r.json();}).then(function(d){LIB=d;render();});'
        'var KEYS=[["band","🎗️ 弹力带"],["dumbbell","🏋️ 哑铃"],["bodyweight","🤸 无器材"]];'
        'var cur="band",flt="";'
        'function render(){'
        'var t=document.getElementById("tabs");t.innerHTML="";'
        'KEYS.forEach(function(k){var b=document.createElement("div");b.className="tab"+(cur===k[0]?" on":"");b.textContent=k[1];b.onclick=function(){cur=k[0];flt="";render();};t.appendChild(b);});'
        'var parts=[];LIB[cur].forEach(function(x){x.m.forEach(function(m){if(parts.indexOf(m)<0)parts.push(m);});});'
        'var c=document.getElementById("chips");c.innerHTML="";'
        'var all=document.createElement("div");all.className="chip"+(flt?"":" on");all.textContent="全部";all.onclick=function(){flt="";render();};c.appendChild(all);'
        'parts.forEach(function(p){var d=document.createElement("div");d.className="chip"+(flt===p?" on":"");d.textContent=p;d.onclick=function(){flt=flt===p?"":p;render();};c.appendChild(d);});'
        'var list=LIB[cur].filter(function(x){return !flt||x.m.indexOf(flt)>=0;});'
        'document.getElementById("cnt").textContent=list.length+" 个动作";'
        'var g=document.getElementById("grid");g.innerHTML="";'
        'list.forEach(function(x){'
        'var img=x.img?(`<img src="exercise/${x.img}" loading=lazy>`):"<div class=noimg>🏋️</div>";'
        'var ms=x.m.map(function(m){return "<span class=m>"+m+"</span>";}).join("");'
        'var m2=x.m2.map(function(m){return "<span class=m2>"+m+"</span>";}).join("");'
        'var ne=x.n_en?"<div class=nen>"+x.n_en+"</div>":"";'
        'g.innerHTML+="<div class=card>"+img+"<div class=name>"+x.n+"</div>"+ne'
        '+"<div class=muscles>"+ms+m2+"</div>"'
        '+(x.tip?"<div class=tip>"+x.tip+"</div>":"")+"</div>";});}'
        'var DB=null,dbLoading=false,st=null;'
        'function loadDB(cb){if(DB)return cb();if(dbLoading)return;dbLoading=true;'
        'document.getElementById("searchMeta").textContent="正在加载动作数据库…";'
        'fetch("exercise-db.json").then(function(r){return r.json();}).then(function(d){DB=d.rows;'
        'document.getElementById("searchMeta").textContent="";cb();}).catch(function(){'
        'document.getElementById("searchMeta").textContent="数据库加载失败";});}'
        'document.getElementById("searchBox").addEventListener("input",function(e){'
        'var q=e.target.value.trim();clearTimeout(st);'
        'if(!q){document.getElementById("searchResults").innerHTML="";document.getElementById("searchMeta").textContent="";return;}'
        'st=setTimeout(function(){loadDB(function(){doSearch(q);});},250);});'
        'function doSearch(q){var ql=q.toLowerCase();var hits=[];'
        'for(var i=0;i<DB.length;i++){var r=DB[i];'
        'if((r[1]&&r[1].toLowerCase().indexOf(ql)>=0)||(r[2]&&r[2].toLowerCase().indexOf(ql)>=0)'
        '||(r[3]&&r[3].indexOf(q)>=0)||(r[4]&&r[4].indexOf(q)>=0)'
        '||(r[5]&&r[5].indexOf(q)>=0)||(r[6]&&r[6].join(" ").indexOf(q)>=0)){hits.push(r);if(hits.length>=40)break;}}'
        'document.getElementById("searchMeta").textContent="命中 "+hits.length+" 个动作"+(hits.length>=40?"（最多显示40）":"");'
        'var g=document.getElementById("searchResults");g.className="sgrid";'
        'var html="";'
        'hits.forEach(function(r){'
        'var vid=r[9]?"<div class=svideo><video src=exercise/"+r[0]+".mp4 muted loop playsinline preload=none></video></div>":"<div class=svideo><div class=ph>🏋️</div></div>";'
        'var sec=r[6].map(function(m){return "<span class=sm2>"+m+"</span>";}).join("");'
        'var ins=r[8].map(function(s){return "<li>"+s+"</li>";}).join("");'
        'html+="<div class=scard>"+vid+"<div class=sbody>"'
        '+"<div class=sname>"+(r[1]||r[2])+"</div>"'
        '+(r[2]&&r[1]?"<div class=nen>"+r[2]+"</div>":"")'
        '+"<div><span class=stag>"+r[3]+"</span><span class=stag>"+r[4]+"</span></div>"'
        '+"<div class=smuscles><span class=sm>"+(r[5]||"未标注")+"</span>"+sec+"</div>"'
        '+(r[7]?"<div class=sdesc>"+r[7]+"</div>":"")'
        '+(ins?"<ol class=sins>"+ins+"</ol>":"")'
        '+"</div></div>";});'
        'g.innerHTML=html;'
        'var io=new IntersectionObserver(function(es){es.forEach(function(en){var v=en.target;if(en.isIntersecting){v.play().catch(function(){});}else{v.pause();}});},{rootMargin:"150px"});'
        'document.querySelectorAll("#searchResults video").forEach(function(v){io.observe(v);v.addEventListener("error",function(){var p=v.parentNode;p.innerHTML="<div class=ph>🏋️</div>";});});}'
        '</script></body></html>'
        "document.querySelectorAll("#searchResults .sins").forEach(function(o){o.addEventListener("click",function(){o.classList.toggle("open");});});"
    )

EXERCISE_PAGE = _exercise_page()


PAGE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>海报</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { width:100%; height:100%; background:#000; overflow:hidden;
              font-family:"Microsoft YaHei",sans-serif; }
  #stage { position:absolute; inset:0; }
  .layer { position:absolute; inset:0; display:flex; align-items:center;
           justify-content:center; opacity:0; transition:opacity .8s ease; }
  .layer.on { opacity:1; }
  .layer img, .layer video { max-width:100%; max-height:100%;
           width:100%; height:100%; object-fit:contain; }
  .nav { position:absolute; top:0; bottom:0; width:64px; border:0;
         background:rgba(255,255,255,.06); color:rgba(255,255,255,.85);
         font-size:46px; cursor:pointer; opacity:.45; transition:opacity .2s;
         z-index:5; font-family:system-ui,sans-serif; }
  .nav:hover { opacity:.95; }
  #prev { left:0; } #next { right:0; }
  #meta { position:absolute; left:0; right:0; top:0; padding:10px 76px;
          color:rgba(255,255,255,.85); font-size:18px;
          background:linear-gradient(rgba(0,0,0,.7),transparent);
          display:flex; justify-content:center; gap:18px; align-items:baseline;
          pointer-events:none; z-index:4; }
  #m-page { font-size:21px; color:#fff; letter-spacing:1px; }
  #m-title { opacity:.75; }
  #err { position:absolute; inset:0; display:none; color:#f66;
         align-items:center; justify-content:center; font-size:22px;
         text-align:center; padding:40px; z-index:6; }
  /* 移动端竖屏（2026-11-19）：meta 行压缩防溢出，翻页按钮适配触控 */
  @media (max-width: 768px) {
    #meta { padding:8px 52px; font-size:12px; gap:10px; flex-wrap:wrap; }
    #m-page { font-size:15px; }
    #m-title { max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .nav { width:44px; font-size:30px; opacity:.6; }
  }
</style>
</head>
<body>
  <div id="stage"></div>
  <button class="nav" id="prev" title="上一张">&#8249;</button>
  <button class="nav" id="next" title="下一张">&#8250;</button>
  <div id="meta"><span id="m-page"></span><span id="m-title"></span></div>
  <div id="err"></div>
<script>
var list = [], idx = 0, timer = null;
var DWELL_IMG = 30000;      // 图片 30 秒
var DWELL_VID = 90000;      // 视频 90 秒
var LIST_REFRESH = 120000;  // 每 2 分钟重拉列表（新海报自动进轮播）

function showErr(msg) {
  var e = document.getElementById('err');
  if (msg) { e.style.display = 'flex'; e.textContent = msg; }
  else { e.style.display = 'none'; }
}

function src(p) { return 'file?path=' + encodeURIComponent(p); }

function render() {
  if (!list.length) { showErr('海报列表为空\\n（检查 NocoDB「当前海报」表）');
                      document.getElementById('m-page').textContent = ''; return; }
  showErr('');
  if (idx >= list.length) idx = 0;
  if (idx < 0) idx = list.length - 1;
  var it = list[idx];
  var stage = document.getElementById('stage');

  // 新层淡入
  var layer = document.createElement('div');
  layer.className = 'layer';
  var el;
  if (it.kind === 'video') {
    el = document.createElement('video');
    el.src = src(it.path); el.autoplay = true; el.muted = true;
    el.playsInline = true; el.loop = true;   // 播完自动重播
    el.onerror = function(){ mediaFail(it, layer); };
  } else {
    el = document.createElement('img');
    el.src = src(it.path);
    el.onerror = function(){ mediaFail(it, layer); };
  }
  layer.appendChild(el);
  stage.appendChild(layer);
  requestAnimationFrame(function(){
    requestAnimationFrame(function(){ layer.classList.add('on'); });
  });

  // 旧层淡出并移除
  var olds = stage.querySelectorAll('.layer:not(:last-child)');
  Array.prototype.forEach.call(olds, function(o){
    o.classList.remove('on');
    setTimeout(function(){ if (o.parentNode) o.parentNode.removeChild(o); }, 900);
  });

  document.getElementById('m-title').textContent = it.title || '';
  document.getElementById('m-page').textContent = (idx + 1) + ' / ' + list.length;
  clearTimeout(timer);
  var dwell = (it.kind === 'video') ? DWELL_VID : DWELL_IMG;
  timer = setTimeout(next, dwell);
}

var failFlood = 0, failTimer = null;   // 连续失败护栏：禁止白屏疯狂循环

function mediaFail(it, layer) {
  // 取图失败：整页服务挂掉时若继续 next() 会白屏高速循环，这里改为停住 + 退避重拉
  if (layer && layer.parentNode) layer.parentNode.removeChild(layer);
  failFlood++;
  if (failFlood >= 3) {
    showErr('海报加载失败，10 秒后自动重试\\n（多半是本机 poster 服务没起）');
    clearTimeout(failTimer);
    failTimer = setTimeout(function(){ failFlood = 0; load(); }, 10000);
    return;
  }
  clearTimeout(failTimer);
  failTimer = setTimeout(function(){ failFlood = 0; next(); }, 3000);
}

function ding() {
  // 海报提醒音（网页自身发声）：每 10 分钟一次，只在海报页可见时响
  // 设计：叮 = 「抬头看海报」的信号，不随每次换图响（太频繁会脱敏）
  try {
    var h = new Date().getHours();          // 免打扰：22:00 -> 08:00
    if (h >= 22 || h < 8) return;
    if (document.visibilityState !== 'visible') return;   // 页签切走了不叮
    var C = window.AudioContext || window.webkitAudioContext;
    if (!C) return;
    if (!ding._c) ding._c = new C();
    var c = ding._c;
    if (c.state === 'suspended' && c.resume) c.resume();
    var o = c.createOscillator(), g = c.createGain();
    o.type = 'sine'; o.frequency.value = 1046.5;   // C6 叮
    g.gain.setValueAtTime(0.0001, c.currentTime);
    g.gain.exponentialRampToValueAtTime(0.25, c.currentTime + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + 0.7);
    o.connect(g); g.connect(c.destination);
    o.start(); o.stop(c.currentTime + 0.7);
  } catch (e) {}
}
// 随机 5-10 分钟提醒一次（变异间隔比固定间隔更抗脱敏，且避免与轮播周期共振）
function scheduleDing() {
  var delay = (5 * 60 + Math.random() * 5 * 60) * 1000;
  setTimeout(function () { ding(); scheduleDing(); }, delay);
}
scheduleDing();

function go(d) { idx += d; render(); }
function next() { go(1); }
function prev() { go(-1); }

document.getElementById('next').addEventListener('click', function(e){
  e.stopPropagation(); e.preventDefault(); next(); });
document.getElementById('prev').addEventListener('click', function(e){
  e.stopPropagation(); e.preventDefault(); prev(); });
document.addEventListener('keydown', function(e){
  if (e.key === 'ArrowRight') next();
  else if (e.key === 'ArrowLeft') prev();
 });

function load() {
  fetch('api/posters', {cache: 'no-store'})
    .then(function(r){ return r.json(); })
    .then(function(d){
      var oldKey = list.length && list[idx] ? list[idx].path : null;
      list = d.items || [];
      failFlood = 0; showErr('');
      if (oldKey) {
        var found = list.findIndex(function(x){ return x.path === oldKey; });
        idx = found >= 0 ? found : 0;
      } else { idx = 0; }
      render();
    })
    .catch(function(e){ showErr('拉取海报失败: ' + e); });
}

load();
setInterval(load, LIST_REFRESH);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        line = f"[http] {self.client_address[0]} {fmt % args}"
        print(line)
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "access.log"), "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
        except Exception:
            pass

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # 大屏 iframe 是 sandbox（即使 allow-same-origin 也可能来自匿名源），
        # 统一带 CORS 头，任何来源都能读。
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        if u.path.startswith("/web/"):
            parts = u.path.split("/")
            if len(parts) >= 3 and parts[2].isdigit():
                self._proxy(parts[2], "/" + "/".join(parts[3:]) if len(parts) > 3 else "/", u.query)
                return
        self._send(200, "{}", "application/json; charset=utf-8")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self._send(200, PAGE)
        elif u.path == "/api/posters":
            items = get_posters(force=(parse_qs(u.query).get("refresh") == ["1"]))
            self._send(200, json.dumps({"items": items, "count": len(items)},
                                       ensure_ascii=False),
                       "application/json; charset=utf-8")
        elif u.path == "/file":
            path = (parse_qs(u.query).get("path") or [""])[0]
            if not path:
                self._send(400, "missing path", "text/plain; charset=utf-8")
                return
            self._serve_file(path)
        elif u.path in ("/exercise-lib.json", "/exercise-db.json"):
            fn = "exercise_lib.json" if u.path == "/exercise-lib.json" else "exercise_db.json"
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), fn)
            if os.path.exists(p):
                with open(p, "rb") as f:
                    self._send(200, f.read(), "application/json; charset=utf-8")
            else:
                self._send(404, "not found")
        elif u.path == "/exercise":
            # 运动动作库页（常驻页签用）：GIF 网格 + 组数提示
            self._send(200, EXERCISE_PAGE)
        elif u.path.startswith("/exercise/"):
            # 健身 GIF 静态目录：本地 cache/exercise/ 直读，不走 NocoDB
            name = os.path.basename(u.path)   # basename 防路径穿越
            fp = os.path.join(CACHE_DIR, "exercise", name)
            if os.path.isfile(fp):
                with open(fp, "rb") as fh:
                    data = fh.read()
                low = name.lower()
                if low.endswith(".mp4"):
                    ctype = "video/mp4"
                elif low.endswith((".jpg", ".jpeg")):
                    ctype = "image/jpeg"
                else:
                    ctype = "image/gif"
                self._send(200, data, ctype)
            else:
                self._send(404, "not found", "text/plain; charset=utf-8")
        elif u.path.startswith("/web/"):
            # 内网服务 https 反代：/web/<port>/<rest> → http://192.168.88.118:<port>/<rest>
            # 用途：tianluo 是 https，iframe 直嵌 http 内网会被 mixed content 拦截，走 8137 包一层
            # 绝对路径重写：/_next/、/api/ 等 → /web/<port>/...（相对路径 ./assets 不受影响）
            parts = u.path.split("/")
            if len(parts) < 3 or not parts[2].isdigit():
                self._send(400, "bad proxy path", "text/plain; charset=utf-8")
                return
            self._proxy(parts[2], "/" + "/".join(parts[3:]) if len(parts) > 3 else "/", u.query)
        elif u.path.startswith("/download/"):
            # 兼容旧版页面（浏览器里还开着的老标签页用 /download/noco/... 直连取图）
            self._serve_file(u.path.lstrip("/"))
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def _proxy(self, port, rest, query):
        import urllib.request
        target = f"http://192.168.88.118:{port}{rest}"
        if query:
            target += "?" + query
        body = None
        clen = self.headers.get("Content-Length")
        if clen:
            body = self.rfile.read(int(clen))
        req = urllib.request.Request(target, data=body, method=self.command)
        for h, v in self.headers.items():
            if h.lower() not in ("host", "content-length", "connection", "accept-encoding"):
                req.add_header(h, v)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
                ctype = resp.headers.get("Content-Type", "application/octet-stream")
                # HTML/JS 绝对路径重写，让 iframe 里的资源走反代
                if "text/html" in ctype or "javascript" in ctype:
                    prefix = f"/web/{port}".encode()
                    for pat in (b'"/_next/', b"'/_next/", b'"/api/', b"'/api/"):
                        data = data.replace(pat, pat[:1] + prefix + pat[1:])
                    ctype += "; charset=utf-8"
                self._send(200, data, ctype)
        except Exception as e:
            self._send(502, f"proxy failed: {e}", "text/plain; charset=utf-8")

    def _serve_file(self, path):
        local, err = get_file(path)
        if not local:
            self._send(502, err or "fetch failed", "text/plain; charset=utf-8")
            return
        ctype = "application/octet-stream"
        low = path.lower()
        if low.endswith((".webp",)):
            ctype = "image/webp"
        elif low.endswith((".png",)):
            ctype = "image/png"
        elif low.endswith((".jpg", ".jpeg")):
            ctype = "image/jpeg"
        elif low.endswith((".mp4",)):
            ctype = "video/mp4"
        elif low.endswith((".gif",)):
            ctype = "image/gif"
        with open(local, "rb") as fh:
            data = fh.read()
        self._send(200, data, ctype)   # CORS 头 _send 已统一加，勿重复


if __name__ == "__main__":
    import ssl
    CERT = r"C:\Users\nainaijia\.acme.sh\pt2153.com_ecc\fullchain.cer"
    KEY = r"C:\Users\nainaijia\.acme.sh\pt2153.com_ecc\pt2153.com.key"
    print(f"[poster] 启动 0.0.0.0:{PORT} (HTTPS)  列表缓存 {LIST_TTL}s")
    print(f"[poster] 首次拉取海报: {len(get_posters())} 个文件")
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT, KEY)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    httpd.serve_forever()
