/* 田螺姑娘终端：哑显示端。只负责忠实执行 cmd、上报 evt，一切决策在大脑。
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
    view: "clock",        // clock | card | html | image | speak | off
    volume: 1.0,
    player: null,         // 正在播放的 Audio
    speakCmd: null,       // 正在播放的 speak cmd（打断时回 failed）
    cardUntil: null,      // 当前卡片的过期时间（Date）
    listenTimer: null,
    wakeLock: null,
    histIdx: -1,          // 正在浏览历史的下标，-1 = 看实时画面
    liveCmd: null,        // 最近一条实时画面 {type, cmd}（退出历史时还原）
  };

  function $(id) { return document.getElementById(id); }
  function genId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }

  /* ---------- 通知历史（画面存档，左右翻页；声音不存） ---------- */

  var HIST_KEY = "tianluo_history_v1";
  var HIST_MAX = 50;

  var hist = [];
  try {
    var raw = localStorage.getItem(HIST_KEY);
    if (raw) { hist = JSON.parse(raw); if (!(hist instanceof Array)) hist = []; }
  } catch (e) { hist = []; }

  function saveHist() {
    for (;;) {
      try { localStorage.setItem(HIST_KEY, JSON.stringify(hist)); return; }
      catch (e) {
        // 配额超了：丢最旧的再试；只剩一条还存不下就放弃（不崩）
        if (hist.length > 1) hist.shift(); else return;
      }
    }
  }

  function histPush(type, cmd) {
    hist.push({ t: Date.now(), type: type, cmd: cmd });
    while (hist.length > HIST_MAX) hist.shift();
    saveHist();
  }

  function fmtTs(t) {
    var d = new Date(t), p = function (n) { return (n < 10 ? "0" : "") + n; };
    return p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " +
      p(d.getHours()) + ":" + p(d.getMinutes());
  }

  var TYPE_CN = { card: "卡片", html: "网页", image: "图片" };

  function updateHistBar() {
    var bar = $("hist-bar");
    if (!hist.length) { bar.classList.add("hidden"); return; }
    bar.classList.remove("hidden");
    if (state.histIdx < 0) {
      $("hist-label").textContent = "‹ 通知历史";
    } else {
      var e = hist[state.histIdx];
      $("hist-label").textContent =
        fmtTs(e.t) + " " + (TYPE_CN[e.type] || e.type) +
        "  " + (state.histIdx + 1) + "/" + hist.length + " ›";
    }
  }

  function renderEntry(e) {
    if (e.type === "card") renderCard(e.cmd);
    else if (e.type === "html") renderHtml(e.cmd);
    else if (e.type === "image") renderImage(e.cmd);
  }

  function renderLive() {
    if (state.liveCmd) renderEntry(state.liveCmd);
    else setView("clock");
  }

  function histShow(i) {
    if (i < 0 || i >= hist.length) {         // 越界 = 回实时画面
      state.histIdx = -1;
      renderLive();
      updateHistBar();
      return;
    }
    state.histIdx = i;
    renderEntry(hist[i]);
    updateHistBar();
  }

  /* ---------- 视图切换 ---------- */

  var VIEWS = ["view-clock", "view-card", "view-html", "view-image"];

  function setView(name, opts) {
    opts = opts || {};
    VIEWS.forEach(function (v) { $(v).classList.add("hidden"); });
    $("speak-bar").classList.add("hidden");
    $("listen-bar").classList.add("hidden");
    state.view = name;

    if (name === "card" && opts.mode === "banner") {
      $("view-card").classList.remove("hidden");
    } else if (VIEWS.indexOf("view-" + name) >= 0) {
      $("view-" + name).classList.remove("hidden");
    } else if (name === "clock") {
      $("view-clock").classList.remove("hidden");
    }
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
      $("view-clock").classList.remove("hidden");  // banner 模式时钟保留
      state.view = "card";
      publishStatus("online");
    } else {
      setView("card");
    }
    state.cardUntil = cmd.display && cmd.display.until ? new Date(cmd.display.until) : null;
  }

  function showCard(cmd) {
    state.histIdx = -1;
    renderCard(cmd);
    state.liveCmd = { type: "card", cmd: cmd };
    histPush("card", cmd);
    updateHistBar();
    ack(cmd, "displayed");
  }

  function renderHtml(cmd) {
    const frame = $("html-frame");
    // 强制重绘：清空 → 强制重排 → 下一帧再赋值，
    // 修复 kiosk 上间歇性白屏（srcdoc 在旧视图状态下偶发不重画）
    frame.srcdoc = "";
    void frame.offsetHeight;
    const html = cmd.html || "";
    if (window.requestAnimationFrame) {
      requestAnimationFrame(() => { frame.srcdoc = html; });
    } else {
      frame.srcdoc = html;
    }
    setView("html");
  }

  function showHtml(cmd) {
    state.histIdx = -1;
    renderHtml(cmd);
    state.liveCmd = { type: "html", cmd: cmd };
    histPush("html", cmd);
    updateHistBar();
    ack(cmd, "displayed");
  }

  function renderImage(cmd) {
    $("image-img").src = "data:image/" + (cmd.format || "jpeg") +
      ";base64," + cmd.image_b64;
    setView("image");
  }

  function showImage(cmd) {
    state.histIdx = -1;
    renderImage(cmd);
    state.liveCmd = { type: "image", cmd: cmd };
    histPush("image", cmd);
    updateHistBar();
    ack(cmd, "displayed");
  }

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
        $("speak-bar").classList.remove("hidden");
      }
      audio.onended = function () {
        state.player = null; state.speakCmd = null;
        $("speak-bar").classList.add("hidden");
        ack(cmd, "played");
        if (state.view === "speak") setView("clock");
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
      if (state.view === "off") setView("clock");
      if (cmd.state === "keep_awake" && navigator.wakeLock) {
        navigator.wakeLock.request("screen").then(function (lock) {
          state.wakeLock = lock;
        }).catch(function () {});
      }
    }
    publishStatus("online");
    ack(cmd, "displayed");
  }

  function doClear(cmd) {
    stopPlaying(null);
    clearInterval(state.listenTimer);
    $("off-overlay").classList.add("hidden");
    state.cardUntil = null;
    state.histIdx = -1;
    state.liveCmd = null;
    setView("clock");
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
      if (state.view === "card") doClear(null);
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
  updateHistBar();
  // 翻页：‹=往更旧的一条，›=往更新的一条（越界即回到实时画面）
  $("hist-prev").addEventListener("click", function () {
    histShow(state.histIdx < 0 ? hist.length - 1 : state.histIdx - 1);
  });
  $("hist-next").addEventListener("click", function () {
    histShow(state.histIdx + 1);
  });
  // 横向滑动翻页（触屏）
  var sx = null;
  window.addEventListener("touchstart", function (e) { sx = e.touches[0].clientX; }, { passive: true });
  window.addEventListener("touchend", function (e) {
    if (sx === null) return;
    var dx = e.changedTouches[0].clientX - sx; sx = null;
    if (Math.abs(dx) < 60) return;                       // 太短不算
    if (state.histIdx < 0 && dx > 0) return;             // 实时画面时右滑不动作（新内容优先）
    histShow(dx < 0 ? (state.histIdx < 0 ? hist.length - 1 : state.histIdx - 1)
                    : state.histIdx + 1);
  }, { passive: true });
  window.addEventListener("beforeunload", function () {
    publishStatus("offline");
  });
  connect();
})();
