# 架构

三件套，全部经 MQTT（EMQX Cloud Serverless，杭州区）通信：

1. **终端（身体）**：工控一体机跑 Chrome kiosk 全屏页（`web/`）。
   哑设备：执行 cmd（显示卡片/网页/图片、播语音、亮熄屏），上报 evt
   （录音、按钮、在场、回执）。协议状态机极简：待机时钟 ↔ 指令视图。

2. **消息通道**：EMQX Cloud Serverless。浏览器走 WSS 8084，agent 工具走 8883（TLS）。
   两端都只需出网，无需公网入口。账号 ACL 白名单：`girl-01` 限
   `tianluo/terminal/girl-01/#`，`agent` 限 `tianluo/#`。

3. **Agent 端（大脑）**：不在本仓库——任何会发 MQTT 的 AI Agent 都能当大脑。
   给大脑的完整工具包是 skill 目录 `skills/tianluo-girl/`：
   SKILL.md（说明书）、scripts/（发指令 CLI、事件监听、TTS/ASR、定时推送）、
   reference/messages.md（协议全文）。

## 媒体路径（base64 内嵌）

- 下行 TTS：skill scripts 调百炼多模态生成 API → 下载 wav → 有 ffmpeg 则转 ogg_opus
  （10s ≈ 40KB）→ base64 塞进 `speak.audio_b64` → 终端 Blob URL 播放。
- 上行 ASR（二期）：终端 MediaRecorder 录 webm/opus → `recording.audio_b64`
  → agent ffmpeg 解 PCM 16k → 百炼 qwen-audio-3.1-asr-flash-message（WS 流式，
  Fun-ASR 协议，本账号实测可用）→ 文字进大脑。
- 为什么不走 HTTP：两端都在 NAT 后，唯一保证可达的通道是 broker。

## 分阶段

- **MVP**：显示卡片 + 语音播报 + 定时饭食推送 + kiosk 自启
- **二期**：按住说话语音问答（`recording` 上报 + ASR + `listen` 回合交接）
- **三期**：摄像头 presence、唤醒词、USB 灯、LLM 大脑、多终端

## 参考

- 协议：`skills/tianluo-girl/reference/messages.md`（唯一权威）
- 部署：`docs/deploy.md`
