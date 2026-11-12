/* 田螺姑娘终端：哑显示端。只负责忠实执行 cmd、上报 evt，一切决策在大脑。
 * 常驻页签系统（2026-11-12）：左侧竖排页签，多 iframe 独立保活，点按切换。
 * 弱机友好：无框架、少 DOM 更新、音频用原生 HTMLAudio。协议见 skills/tianluo-girl/reference/messages.md。
 */
(function () {
  "use strict";

  var cfg = window.TIANLUO_CONFIG;
  var TOPIC_CMD = "tianluo/terminal/" + cfg.DEVICE_ID + "/cmd";
  var TOPIC_EVT = "tianluo/terminal/" + cfg.DEVICE_ID + "/evt";
  var TOPIC_STATUS = "tianluo/terminal/" + cfg.DEVICE_ID + "/status";

  var MIME = {
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
    "wav": "audio/wav",
    "jpeg": "image/jpeg",
    "png": "image/png",
  };

  var state = {
    view: "clock",        // clock | card | html | image | speak | off | slot
    volume: 1.0,
    player: null,         // 正在播放的 Audio
    speakCmd: null,       // 正在播放的 speak cmd（打断时回 failed）
    cardUntil: null,      // 当前卡片的过期时间（Date）
    listenTimer: null,
    wakeLock: null,
    slots: [],            // 常驻页签 [{id,label,icon,kind,url,html}]
    activeSlot: -1,       // 当前激活槽下标，-1 = 无激活（看时钟/临时层）
    temp: null,           // 临时全屏层 {type:"card"|"html"|"image"}，banner 卡片不算
  };

  var slotEls = {};       // slot id -> {wrap, frame}

  function $(id) { return document.getElementById(id); }
  function genId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }

  /* ---------- 常驻页签系统 ---------- */

  function slotIndexById(id) {
    for (var i = 0; i < state.slots.length; i++) {
      if (state.slots[i].id === id) return i;
    }
    return -1;
  }

  function ensureSlotEl(s) {
    if (slotEls[s.id]) return;
    var wrap = document.createElement("div");
    wrap.className = "slot-frame hidden";
    var frame = document.createElement("iframe");
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin");
    frame.setAttribute("title", s.label || s.id);
    wrap.appendChild(frame);
    $("slot-frames").appendChild(wrap);
    slotEls[s.id] = { wrap: wrap, frame: frame };
  }

  // 强制重绘：清空 → 强制重排 → 下一帧再赋值，
  // 修复 kiosk 上间歇性白屏（srcdoc 在旧视图状态下偶发不重画）
  function loadSlotContent(s) {
    var el = slotEls[s.id];
    if (!el) return;
    var frame = el.frame;
    frame.srcdoc = "";
    frame.removeAttribute("src");
    void frame.offsetHeight;
    var apply = function () {
      if (s.kind === "url") {
        frame.srcdoc = "";
        frame.src = s.url;
      } else {
        frame.removeAttribute("src");
        frame.srcdoc = s.html || "";
      }
    };
    if (window.requestAnimationFrame) requestAnimationFrame(apply);
    else apply();
  }

  function removeSlotEl(id) {
    var el = slotEls[id];
    if (!el) return;
    if (el.wrap.parentNode) el.wrap.parentNode.removeChild(el.wrap);
    delete slotEls[id];
  }

  // 统一裁决：左侧按钮渲染 + iframe 显隐 + 时钟显隐
  function renderSlots() {
    var bar = $("slot-bar");
    var list = $("slot-list");
    list.innerHTML = "";
    if (!state.slots.length) {
      bar.classList.add("hidden");
    } else {
      bar.classList.remove("hidden");
      state.slots.forEach(function (s, i) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "slot-btn" + (i === state.activeSlot && !state.temp ? " active" : "");
        b.innerHTML = "<span class=\"slot-icon\">" + (s.icon || "📄") +
                      "</span><span class=\"slot-label\">" + (s.label || s.id) + "</span>";
        b.addEventListener("click", function () { activateSlot(i, true); });
        list.appendChild(b);
      });
    }
    Object.keys(slotEls).forEach(function (id) {
      var idx = slotIndexById(id);
      var show = idx >= 0 && idx === state.activeSlot && !state.temp;
      slotEls[id].wrap.classList.toggle("hidden", !show);
    });
    // 时钟只在：无临时层 && 无激活槽 时显示
    var showClock = !state.temp && state.activeSlot < 0;
    $("view-clock").classList.toggle("hidden", !showClock);
  }

  function activateSlot(idx, byUser) {
    if (idx < 0 || idx >= state.slots.length) return;
    state.activeSlot = idx;
    state.temp = null;         // 切页签时清掉临时全屏层
    state.cardUntil = null;
    state.view = "slot";
    setView("slot");
    renderSlots();
    if (byUser) {
      var s = state.slots[idx];
      publishEvt({ type: "slot", action: "activate", id: s.id, label: s.label });
    }
    saveSlots();   // 激活态持久化，刷新后回到最后看的页签
  }

  function setSlot(cmd) {
    if (!cmd.slot_id) { ack(cmd, "failed"); return; }
    var idx = slotIndexById(cmd.slot_id);
    var slot = {
      id: cmd.slot_id,
      label: cmd.label || cmd.slot_id,
      icon: cmd.icon || "📄",
      kind: cmd.kind === "url" ? "url" : "html",
      url: cmd.url || "",
      html: cmd.html || "",
    };
    if (idx < 0) {
      state.slots.push(slot);
      ensureSlotEl(slot);
      loadSlotContent(slot);
      // 首个槽自动激活；显式 activate=true 也激活
      if (cmd.activate || state.activeSlot < 0) {
        state.activeSlot = state.slots.length - 1;
        state.view = "slot";
      }
    } else {
      var old = state.slots[idx];
      var contentChanged = old.kind !== slot.kind ||
        (slot.kind === "url" ? old.url !== slot.url : old.html !== slot.html);
      state.slots[idx] = slot;
      ensureSlotEl(slot);
      if (contentChanged) loadSlotContent(slot);
      if (cmd.activate) state.activeSlot = idx;
    }
    if (cmd.activate) state.temp = null;
    state.view = "slot";
    setView("slot");
    renderSlots();
    saveSlots();
    ack(cmd, "displayed");
  }

  function removeSlot(cmd) {
    var idx = slotIndexById(cmd.slot_id);
    if (idx >= 0) {
      state.slots.splice(idx, 1);
      removeSlotEl(cmd.slot_id);
      if (state.activeSlot === idx) {
        state.activeSlot = state.slots.length ? 0 : -1;
        state.temp = null;
      } else if (state.activeSlot > idx) {
        state.activeSlot--;
      }
      setView(state.activeSlot >= 0 ? "slot" : "clock");
      renderSlots();
      saveSlots();
    }
    ack(cmd, "displayed");
  }

  function clearSlots(cmd) {
    state.slots = [];
    Object.keys(slotEls).forEach(removeSlotEl);
    state.activeSlot = -1;
    state.temp = null;
    state.cardUntil = null;
    setView("clock");
    renderSlots();
    saveSlots();
    if (cmd) ack(cmd, "displayed");
  }

  /* ---------- 视图切换 ---------- */

  var BASE_VIEWS = ["view-clock", "view-card", "view-html", "view-image"];

  function setView(name, opts) {
    opts = opts || {};
    BASE_VIEWS.forEach(function (v) { $(v).classList.add("hidden"); });
    $("speak-bar").classList.add("hidden");
    $("listen-bar").classList.add("hidden");
    state.view = name;

    if (name === "card" && opts.mode === "banner") {
      $("view-card").classList.remove("hidden");   // banner：时钟由 renderSlots 保留
    } else if (BASE_VIEWS.indexOf("view-" + name) >= 0) {
      $("view-" + name).classList.remove("hidden");
    }
    // name === "slot" 时所有 BASE_VIEWS 隐藏，显隐由 renderSlots 裁决
    publishStatus("online");
  }

  /* ---------- 状态 ---------- */

  var client = null;

  function publishStatus(s) {
    if (!client || !client.connected) return;
    client.publish(TOPIC_STATUS, JSON.stringify({
      state: s, view: state.view, ts: new Date().toISOString(),
    }), { retain: true, qos: 1 });
  }

  function publishEvt(obj) {
    if (!client || !client.connected) return;
    obj.v = 1; obj.id = obj.id || genId(); obj.sent_at = new Date().toISOString();
    client.publish(TOPIC_EVT, JSON.stringify(obj), { qos: obj.type === "recording" ? 1 : 0 });
  }

  function ack(cmd, result) {
    publishEvt({ type: "ack", cmd_id: cmd.id, action: cmd.type, result: result });
  }

  /* ---------- 页签持久化（localStorage，刷新/重启后恢复） ---------- */

  function saveSlots() {
    try {
      localStorage.setItem("tianluo_slots", JSON.stringify(state.slots));
      localStorage.setItem("tianluo_active_slot",
        state.activeSlot >= 0 && state.slots[state.activeSlot] ? state.slots[state.activeSlot].id : "");
    } catch (e) { console.warn("[persist] 保存失败", e); }
  }

  function loadSlots() {
    try {
      var raw = localStorage.getItem("tianluo_slots");
      if (!raw) return;
      var arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return;
      arr.forEach(function (s) {
        if (s && s.id && s.kind) setSlot({
          slot_id: s.id, label: s.label, icon: s.icon,
          kind: s.kind, url: s.url, html: s.html
        });   // setSlot 内会 saveSlots，幂等无害
      });
      var act = localStorage.getItem("tianluo_active_slot");
      if (act && slotIndexById(act) >= 0) activateSlot(slotIndexById(act));
      if (state.slots.length) {
        renderSlots();
        setView(state.activeSlot >= 0 ? "slot" : "clock");
      }
      console.log("[persist] 恢复页签", state.slots.length, "个");
    } catch (e) { console.warn("[persist] 恢复失败", e); }
  }

  /* ---------- 时钟 ---------- */

  var WEEK = ["日", "一", "二", "三", "四", "五", "六"];

  function tickClock() {
    var now = new Date();
    var p = function (n) { return (n < 10 ? "0" : "") + n; };
    $("clock-time").textContent = p(now.getHours()) + ":" + p(now.getMinutes());
    $("clock-date").textContent =
      now.getFullYear() + "年" + (now.getMonth() + 1) + "月" + now.getDate() +
      "日 星期" + WEEK[now.getDay()];
  }

  /* ---------- 指令处理 ---------- */

  function renderCard(cmd) {
    var card = $("view-card");
    card.className = "view";                       // 重置模式类
    $("card-title").textContent = cmd.title || "";
    $("card-priority").textContent = cmd.priority === "high" ? "❗ 重要提醒" : "";
    var ul = $("card-items");
    ul.innerHTML = "";
    (cmd.items || []).forEach(function (it, i) {
      var li = document.createElement("li");
      li.textContent = it;
      li.style.animationDelay = (i * 60) + "ms";   // 逐条淡入，纯 CSS
      ul.appendChild(li);
    });
    if (cmd.priority === "high") card.classList.add("high");

    var mode = (cmd.display && cmd.display.mode) || "fullscreen";
    if (mode === "banner") {
      card.classList.add("banner");
    } else {
      card.classList.remove("banner");
    }
  }

  // 临时 fullscreen 卡片：盖住槽，until 到期或切槽/clear 后回槽
  function showCard(cmd) {
    var mode = (cmd.display && cmd.display.mode) || "fullscreen";
    renderCard(cmd);
    if (mode === "banner") {
      state.temp = null;                           // banner 与槽共存
      setView("card", { mode: "banner" });
    } else {
      state.temp = { type: "card" };
      setView("card");
    }
    state.cardUntil = cmd.display && cmd.display.until ? new Date(cmd.display.until) : null;
    renderSlots();
    ack(cmd, "displayed");
  }

  function renderHtml(cmd) {
    const frame = $("html-frame");
    // 强制重绘（同上，防 kiosk 白屏）
    frame.srcdoc = "";
    void frame.offsetHeight;
    const html = cmd.html || "";
    if (window.requestAnimationFrame) {
      requestAnimationFrame(() => { frame.srcdoc = html; });
    } else {
      frame.srcdoc = html;
    }
  }

  // 兼容旧协议：html 指令 = 临时全屏层（常驻页面请用 slot）
  function showHtml(cmd) {
    state.temp = { type: "html" };
    renderHtml(cmd);
    setView("html");
    renderSlots();
    ack(cmd, "displayed");
  }

  function renderImage(cmd) {
    $("image-img").src = "data:image/" + (cmd.format || "jpeg") +
      ";base64," + cmd.image_b64;
  }

  // 临时全屏图片：盖住槽，切槽/clear 后回槽
  function showImage(cmd) {
    state.temp = { type: "image" };
    renderImage(cmd);
    setView("image");
    renderSlots();
    ack(cmd, "displayed");
  }

  /* ---------- 音频 ---------- */

  function b64ToBlob(b64, mime) {
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime });
  }

  function stopPlaying(result) {
    if (state.player) {
      var old = state.speakCmd;
      state.player.onended = null;
      state.player.onerror = null;
      state.player.pause();
      state.player = null;
      state.speakCmd = null;
      if (old && result) ack(old, result);         // 被打断的上一条播报记 failed
    }
  }

  function playSpeak(cmd) {
    if (!cmd.audio_b64) { ack(cmd, "failed"); return; }
    try {
      if (state.player) {
        if (cmd.interrupt) stopPlaying("failed");  // 打断上一段
        else { ack(cmd, "failed"); return; }       // 占用中且不许打断
      }
      var blob = b64ToBlob(cmd.audio_b64, MIME[cmd.format] || "audio/mpeg");
      var audio = new Audio(URL.createObjectURL(blob));
      audio.volume = state.volume;
      state.player = audio;
      state.speakCmd = cmd;

      if (cmd.text) {
        $("speak-text").textContent = "🔊 " + cmd.text;
        $("speak-bar").classList.remove("hidden");   // 字幕条不打断当前槽
      }
      audio.onended = function () {
        state.player = null; state.speakCmd = null;
        $("speak-bar").classList.add("hidden");
        ack(cmd, "played");
      };
      audio.onerror = function () {
        state.player = null; state.speakCmd = null;
        $("speak-bar").classList.add("hidden");
        ack(cmd, "failed");
      };
      audio.play().catch(function () {
        state.player = null; state.speakCmd = null;
        $("speak-bar").classList.add("hidden");
        ack(cmd, "failed");
      });
    } catch (e) {
      ack(cmd, "failed");
    }
  }

  function playSound(cmd) {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      var ctx = new Ctx();
      var notes = cmd.name === "chime" ? [660, 880] : [880, 1320];
      notes.forEach(function (f, i) {
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.frequency.value = f;
        osc.type = "sine";
        gain.gain.setValueAtTime(0.0001, ctx.currentTime + i * 0.18);
        gain.gain.exponentialRampToValueAtTime(
          0.4 * state.volume, ctx.currentTime + i * 0.18 + 0.02);
        gain.gain.exponentialRampToValueAtTime(
          0.0001, ctx.currentTime + i * 0.18 + 0.25);
        osc.connect(gain).connect(ctx.destination);
        osc.start(ctx.currentTime + i * 0.18);
        osc.stop(ctx.currentTime + i * 0.18 + 0.3);
      });
      ack(cmd, "played");
    } catch (e) {
      ack(cmd, "failed");
    }
  }

  function showListen(cmd) {
    var bar = $("listen-bar");
    var timeout = (cmd.timeout_s || 10) * 1000;
    var deadline = Date.now() + timeout;
    bar.classList.remove("hidden");
    clearInterval(state.listenTimer);
    state.listenTimer = setInterval(function () {
      var left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      $("listen-count").textContent = "（" + left + "s）";
      if (left <= 0) {
        clearInterval(state.listenTimer);
        bar.classList.add("hidden");
      }
    }, 250);
    ack(cmd, "displayed");
  }

  function setVolume(cmd) {
    state.volume = Math.min(100, Math.max(0, cmd.level)) / 100;
    if (state.player) state.player.volume = state.volume;
    ack(cmd, "displayed");
  }

  function setScreen(cmd) {
    if (cmd.state === "off") {
      $("off-overlay").classList.remove("hidden");
      state.view = "off";
    } else {
      $("off-overlay").classList.add("hidden");
      if (state.view === "off") {
        setView(state.activeSlot >= 0 ? "slot" : "clock");
        renderSlots();
      }
      if (cmd.state === "keep_awake" && navigator.wakeLock) {
        navigator.wakeLock.request("screen").then(function (lock) {
          state.wakeLock = lock;
        }).catch(function () {});
      }
    }
    publishStatus("online");
    ack(cmd, "displayed");
  }

  // 清除：停播 + 清临时层，回当前激活槽（无槽回时钟）；不动常驻槽
  function doClear(cmd) {
    stopPlaying(null);
    clearInterval(state.listenTimer);
    $("off-overlay").classList.add("hidden");
    state.cardUntil = null;
    state.temp = null;
    setView(state.activeSlot >= 0 ? "slot" : "clock");
    renderSlots();
    if (cmd) ack(cmd, "displayed");
  }

  function handleCmd(raw) {
    var cmd;
    try { cmd = JSON.parse(raw.toString()); }
    catch (e) { return; }
    if (!cmd || !cmd.type) return;

    switch (cmd.type) {
      case "card":      showCard(cmd); break;
      case "html":      showHtml(cmd); break;
      case "image":     showImage(cmd); break;
      case "slot":
        if (cmd.action === "set") setSlot(cmd);
        else if (cmd.action === "activate") {
          var i = slotIndexById(cmd.slot_id);
          if (i >= 0) activateSlot(i, false);
          ack(cmd, "displayed");
        }
        else if (cmd.action === "remove") removeSlot(cmd);
        else if (cmd.action === "clear") clearSlots(cmd);
        else ack(cmd, "failed");
        break;
      case "slideshow": // 三期实现，先明确失败
      case "light":     ack(cmd, "failed"); break;
      case "speak":     playSpeak(cmd); break;
      case "sound":     playSound(cmd); break;
      case "listen":    showListen(cmd); break;
      case "volume":    setVolume(cmd); break;
      case "screen":    setScreen(cmd); break;
      case "clear":     doClear(cmd); break;
      default:          ack(cmd, "failed");
    }
  }

  /* ---------- 过期卡片巡检 ---------- */

  setInterval(function () {
    if (state.cardUntil && new Date() > state.cardUntil) {
      state.cardUntil = null;
      if (state.temp && state.temp.type === "card") {
        state.temp = null;                          // 到期回槽（无槽回时钟）
      }
      setView(state.activeSlot >= 0 ? "slot" : "clock");
      renderSlots();
    }
  }, 1000);

  /* ---------- MQTT 连接 ---------- */

  function setBadge(text, on) {
    var b = $("status");
    b.textContent = text;
    b.className = "badge " + (on ? "badge-on" : "badge-off");
  }

  function connect() {
    client = mqtt.connect(cfg.WS_URL, {
      clientId: cfg.DEVICE_ID + "-" + genId().slice(-6),
      username: cfg.USERNAME || undefined,
      password: cfg.PASSWORD || undefined,
      clean: true,
      reconnectPeriod: 3000,
      connectTimeout: 15000,
      will: {
        topic: TOPIC_STATUS,
        payload: JSON.stringify({ state: "offline", view: "off" }),
        retain: true,
        qos: 1,
      },
    });

    client.on("connect", function () {
      setBadge("已连接 " + cfg.DEVICE_ID, true);
      client.subscribe(TOPIC_CMD, { qos: 1 });
      publishStatus("online");
    });
    client.on("message", function (topic, payload) {
      if (topic === TOPIC_CMD) handleCmd(payload);
    });
    client.on("reconnect", function () { setBadge("重连中…", false); });
    client.on("offline", function () { setBadge("离线", false); });
    client.on("error", function () { setBadge("连接错误", false); });
  }

  /* ---------- 启动 ---------- */

  tickClock();
  setInterval(tickClock, 1000);
  renderSlots();
  loadSlots();   // 恢复持久化的页签（刷新/重启后还在）
  window.addEventListener("beforeunload", function () {
    publishStatus("offline");
  });
  connect();
})();
