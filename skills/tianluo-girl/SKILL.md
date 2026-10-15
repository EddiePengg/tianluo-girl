---
name: tianluo-girl
description: 控制家里的"田螺姑娘"大屏终端（工控机 kiosk 网页）：推送卡片/网页/图片、语音播报、屏幕与音量控制；也能监听它的按键/语音/在场事件。当用户想"让家里大屏显示什么、播报什么提醒、定时推什么内容"时使用。通信走 MQTT（EMQX Cloud Serverless），终端订阅 tianluo/terminal/girl-01/#。
---

# 田螺姑娘：家里的大屏终端

本 skill 是一个**自包含工具包**。Agent（大脑）加载后按本文件的指引即可控制终端——
终端是"哑"的，显示什么、何时显示、播什么，全部由你决定。

## 目录结构

- `SKILL.md`——本文件：是什么、何时用、怎么用
- `scripts/`——可执行工具（Python 3.9+，paho-mqtt + httpx + websockets + ffmpeg）
- `reference/messages.md`——通信协议全文（3 个主题、16 种消息的字段定义）

## 何时用

- 用户说"在大屏上显示…"、"提醒…"、"播报…"、"把…投到屏幕上"
- 需要定时往大屏推内容（饭食计划、待办、明日天气、纪念日）
- 需要确认终端状态/有没有执行（监听事件与回执）

## 连接方式（已由 scripts 封装，了解即可）

- 配置文件：本 skill 目录下的 `config.json`（环境变量同名可临时覆盖）
- 关键项：
  - `MQTT_HOST` / `MQTT_PORT`：默认 `broker.emqx.io` / `1883`（公共测试，勿发隐私）；生产为 `<部署域名>.emqxsl.cn` / `8883`（8883 自动启用 TLS）
  - `MQTT_USERNAME` / `MQTT_PASSWORD`：EMQX 认证用户（生产必配，公共 broker 留空）
  - `DEVICE_ID`：默认 `girl-01`
- 主题：`tianluo/terminal/{DEVICE_ID}/cmd`（下行指令）、`/evt`（上行事件）、`/status`（retained 在线状态）
- 百炼 API Key：自动读 `DASHSCOPE_API_KEY` 或 `~/.bailian/config.json`，无需配置

## 怎么用

SKILL_DIR = 本文件所在目录。首次使用先装依赖：

```bash
pip3 install -r SKILL_DIR/scripts/requirements.txt
```

### 发指令（scripts/publish.py）

```bash
# 显示卡片（--item 可多次；--mode banner = 底部横条不打断时钟；--priority high 红色强调）
python3 SKILL_DIR/scripts/publish.py card --title "明日晚饭" \
    --item "17:30 解冻牛排" --item "电饭煲预约 18:00"

# 语音播报（自动百炼 TTS 合成音频，base64 内嵌，终端直接出声）
python3 SKILL_DIR/scripts/publish.py speak "该准备明天的饭啦"

# 显示自定义网页 / 图片
python3 SKILL_DIR/scripts/publish.py html --html "<h1 style='font-size:80px'>周末大扫除</h1>"
python3 SKILL_DIR/scripts/publish.py image --file menu.jpg

# 其它指令
python3 SKILL_DIR/scripts/publish.py sound --name chime      # 提示音
python3 SKILL_DIR/scripts/publish.py listen --timeout 10     # 对话回合交接
python3 SKILL_DIR/scripts/publish.py volume 80
python3 SKILL_DIR/scripts/publish.py screen off|on|keep_awake
python3 SKILL_DIR/scripts/publish.py clear                   # 清除显示回待机时钟

# 通用选项：--device girl-02（多终端）；--until "+30m" 或 ISO8601（到期自动回时钟）；
#           --wait-ack 10（等终端回执，输出 displayed/played/failed）
python3 SKILL_DIR/scripts/publish.py card --title "测试" --wait-ack 5
```

### 事件监听（scripts/subscribe.py）

```bash
python3 SKILL_DIR/scripts/subscribe.py         # 实时打印 evt + status
```

终端对每条指令回 `ack`（displayed/played/failed）。未来会有 `recording`（语音）、
`button`（按钮）、`presence`（在场）事件从这里上来——做语音问答时这就是入口。

### 定时推送（scripts/scheduler.py）

```bash
python3 SKILL_DIR/scripts/scheduler.py --now   # 立即推一次明天的饭食计划（卡片+播报）
python3 SKILL_DIR/scripts/scheduler.py         # 常驻，每天 MEALPLAN_PUSH_TIME（默认 22:00）推
```

饭食计划数据在 `scripts/plans/*.json`，按日期索引。此脚本是独立兜底，
如果你（Agent）自己有 cron/定时能力，直接调 publish.py 更灵活。

## 不依赖 scripts 直接写代码

```python
import json, uuid, paho.mqtt.client as mqtt
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="agent-" + uuid.uuid4().hex[:6])
c.username_pw_set("<MQTT_USERNAME>", "<MQTT_PASSWORD>")   # 公共 broker 可省略
c.connect("<MQTT_HOST>", 8883)   # 8883 需先 c.tls_set()；公共 broker: broker.emqx.io 1883
c.loop_start()
msg = {"v": 1, "id": uuid.uuid4().hex[:16], "type": "card",
       "sent_at": "...", "title": "明日晚饭", "items": ["17:30 解冻牛排"],
       "display": {"mode": "fullscreen"}, "priority": "normal"}
c.publish("tianluo/terminal/girl-01/cmd", json.dumps(msg, ensure_ascii=False), qos=1)
```

## 规则与注意

- 音频/图片是 base64 字段（`audio_b64`/`image_b64`），HTML 是纯文本字段，都不是 URL
- 单条消息 ≤1MB；speak 文案一两句；图片 ≤300KB；视频不走 MQTT
- `speak.interrupt=true`（CLI 默认）会打断正在播的上一条
- 公共测试 broker（broker.emqx.io）无鉴权，**勿发真实隐私内容**；生产是 EMQX Cloud
- 协议细节查 `reference/messages.md`
