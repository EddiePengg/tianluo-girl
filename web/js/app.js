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
  };

  function $(id) { return document.getElementById(id); }
  function genId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
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

  function showCard(cmd) {
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
    ack(cmd, "displayed");
  }

  function showHtml(cmd) {
    $("html-frame").srcdoc = cmd.html || "";
    setView("html");
    ack(cmd, "displayed");
  }

  function showImage(cmd) {
    $("image-img").src = "data:image/" + (cmd.format || "jpeg") +
      ";base64," + cmd.image_b64;
    setView("image");
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
  window.addEventListener("beforeunload", function () {
    publishStatus("offline");
  });
  connect();
})();
