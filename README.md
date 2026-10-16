# 田螺姑娘（tianluo-girl）

Agent 在家的**身体**：工控一体机常驻大屏终端。Agent（大脑）通过 MQTT 下发指令，终端负责显示卡片/网页、语音播报；终端的麦克风、摄像头感知上报给 Agent。

- 终端"哑"、Agent"聪明"：显示什么、何时显示全由 Agent 决定，终端常年不动
- 唯一通道 MQTT（EMQX Cloud Serverless）：两端都在 NAT 后也能通信
- 每条消息一个 JSON；音频/图片 base64 内嵌；无 HTTP 服务、无 docker

## 架构

```
                 ┌──────── MQTT cmd：显示/播报/听/音量/屏幕 ────────►│
Agent 大脑 ◄─────│                                                   │ 你（说话/按钮/路过）
    ▲ MQTT evt：录音/按键/在场/回执 ◄─────────────────────────────────┘
```

三件套：

1. `web/`——工控机上的 Chrome kiosk 网页（本仓库唯一的"设备端"代码）
2. MQTT broker——EMQX Cloud Serverless（杭州区），见 `docs/deploy.md`
3. **大脑不在本仓库**——任何会发 MQTT 的 AI Agent 都能当大脑。给它的完整工具包在 `skills/tianluo-girl/`（SKILL.md 说明书 + scripts 工具 + reference 协议），交付即复制这个 skill 目录

## 目录

```
web/                      # kiosk 网页（部署在工控机：静态服务 + kiosk 浏览器）
docs/                          # architecture.md / deploy.md（架构说明 + 部署与自启）
skills/tianluo-girl/   # 交给 AI Agent 的完整工具包（核心交付物）
  ├── SKILL.md                 #   是什么、何时用、怎么用
  ├── scripts/                 #   publish.py / subscribe.py / scheduler.py / tts.py / asr.py …
  └── reference/messages.md    #   通信协议全文
```

## 快速开始（联调）

```bash
SKILL=skills/tianluo-girl

# 1. 终端页（工控机或本机，先公共 broker 联调）
cd web && python3 -m http.server 8000
#    Chrome 打开（kiosk 模式见 docs/deploy.md）：http://localhost:8000

# 2. Agent 侧（装依赖，一次性）
pip3 install -r $SKILL/scripts/requirements.txt

# 3. 发一条卡片
python3 $SKILL/scripts/publish.py card --title "明日晚饭" --item "17:30 解冻牛排"

# 4. 语音播报（自动调百炼 TTS 合成）
python3 $SKILL/scripts/publish.py speak "该准备明天的饭啦"

# 5. 看终端回执
python3 $SKILL/scripts/subscribe.py
```

默认连公共测试 broker `broker.emqx.io`（无鉴权，只联调不传真实数据）。
Agent 侧配置在 `skills/tianluo-girl/config.json`（与网页端的 `web/js/config.js` 对称，
一处一个明文配置文件，均不入仓——仓库里只有 `config.example.*` 模板，首次使用复制后填写）。

## 能做什么（终端已实现的能力）

| 指令 | 说明 |
|---|---|
| `card` | 全屏卡片（`fullscreen`）或底部横幅（`banner`），支持 `priority=high` 红色强调、`until` 过期自动回时钟 |
| `html` | 全屏自定义网页（菜单/海报/报告，整段 HTML 直接上屏） |
| `image` | 图片（base64 内嵌，jpeg/png） |
| `speak` | TTS 语音播报，带底部字幕条；`interrupt=true` 可打断上一条 |
| `sound` | 提示音 `chime`（叮咚）/ `ding`（叮） |
| `volume` / `screen` / `clear` | 音量 0–100 / 熄屏·常亮 / 回待机时钟 |
| `listen` | 对话回合交接提示条（麦克风在听 + 倒计时） |
| **通知历史** | 卡片/网页/图片自动存档（本地 localStorage，最近 50 条），屏底 `‹ ›` 按钮或**左右滑动**翻页，横滑回来=实时画面 |

边界（明确不做的）：
- `slideshow` / `light` → 三期实现，当前回 `failed`
- **声音不入历史**（存了会出现"翻页自己说话"），历史只存画面
- 网页端是哑显示端，除历史翻页外没有别的按钮

## 常见问题排障

| 症状 | 原因与解法 |
|---|---|
| 卡片有、语音/音效没有 | kiosk 没带 `--autoplay-policy=no-user-gesture-required`（见 `docs/deploy.md` §3），或浏览器页面刷新后失去自动播放授权——重启 kiosk 或点一下屏幕 |
| 音效 `played` 但听不到 | 音响物理音量旋钮被调小；`publish.py volume 100` 拉软件音量，再查硬件 |
| 网页/海报白屏 | ① 页面先刷新（刷新后 srcdoc 必渲染）② `showHtml` 已做"清空→重排→下一帧赋值"强制重绘 ③ HTML 必须自带 `html,body{height:100%}`，否则只有内容那么高、底下一片白 |
| 竖屏内容被截断 | 一屏放下、禁止滚动：字号用 `clamp()` 按视口缩放（`daily-meal-plan` skill 有具体档位），`overflow:hidden` |
| 显示 `offline` | 先查工控机网络；retained 消息会保留最后一次状态，不代表现在还离线 |

## 配置（本地文件，不入仓）

| 键 | 说明 |
|---|---|
| `MQTT_HOST` / `MQTT_PORT` | EMQX Serverless 域名 / `8883`（8883 自动 TLS；公共联调可填 `broker.emqx.io` / `1883`） |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | 两个认证用户：终端用的填 `config.js`，大脑用的填 `config.json` |
| `DEVICE_ID` | 终端 ID，默认 `girl-01` |
| `TTS_MODEL` / `TTS_VOICE` | 百炼 TTS：`qwen3-tts-flash` / `Cherry` |
| `DASHSCOPE_API_KEY` | 可选：填 config.json、设同名环境变量、或在那台机器 `bl` login（自动落到 `~/.bailian/config.json`），三选一 |

饭食计划在 `skills/tianluo-girl/scripts/plans/*.json`（也不入仓），格式：

```json
{ "2026-10-16": { "dinner": "番茄牛腩煲", "prep": ["早上牛腩焯水", "18:30 下锅"] } }
```
