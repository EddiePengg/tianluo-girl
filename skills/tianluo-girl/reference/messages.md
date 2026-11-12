# 田螺姑娘消息协议 v1

> 本文件是通信协议的唯一权威。改协议先改这里，再改代码。
> 设计原则：终端"哑"、Agent"聪明"；每条消息一个自足 JSON；二进制（音频/图片）base64 内嵌。

## 1. 主题

| 主题 | 方向 | QoS | 说明 |
|---|---|---|---|
| `tianluo/terminal/{id}/cmd` | Agent → 终端 | 1 | 下行指令（id 默认 `girl-01`） |
| `tianluo/terminal/{id}/evt` | 终端 → Agent | 0 | 上行事件；`recording` 用 QoS 1 |
| `tianluo/terminal/{id}/status` | 终端 → Agent | 1 + retained | 在线状态；连接时置 online，LWT 遗嘱置 offline |

## 2. 消息 envelope

```json
{ "v": 1, "id": "01J8Z…", "type": "speak", "sent_at": "2026-10-15T22:00:00+08:00" }
```

- `v`：协议版本，当前固定 1。
- `id`：消息 UUID（ULID/UUID 均可），终端回执 `ack` 时带回 `cmd_id`。
- `type`：消息类型，决定其余字段（见 §3/§4）。

## 3. 下行指令（cmd）

| type | 干什么 | 字段 |
|---|---|---|
| `card` | 显示卡片（终端模板渲染，首选） | `title` str, `items` str[], `display` {`mode`: fullscreen\|banner, `until`: ISO8601}, `priority`: normal\|high |
| `html` | 显示自定义网页（sandbox iframe 禁脚本） | `html` str, `display` 同上 |
| `image` | 显示单图 | `image_b64` str, `format`: jpeg\|png, `display` 同上 |
| `slideshow` | 电子相框轮播 | `images_b64` str[], `interval_s` int |
| `speak` | 语音播报（TTS 音频 base64 内嵌） | `text` str（原文）, `audio_b64` str, `format`: mp3\|ogg\|wav, `interrupt` bool（打断当前播放） |
| `sound` | 播终端本地提示音 | `name`: ding\|chime |
| `listen` | 对话回合交接：开麦等用户回话 | `timeout_s` int |
| `volume` | 设置播放音量 | `level` 0-100 |
| `screen` | 屏幕控制 | `state`: on\|off\|keep_awake |
| `light` | USB 通知灯 | `state`: on\|off, `color` str（三期） |
| `clear` | 清除临时层/停止播放、回当前页签（无页签回待机时钟） | — |
| `slot` | 常驻页签管理（2026-11-12 新增，左侧竖排按钮，多 iframe 独立保活） | `action`: set\\|activate\\|remove\\|clear；`set` 另带 `slot_id` str, `label` str, `icon` str, `kind`: url\\|html, `url` str（kind=url）, `html` str（kind=html）, `activate` bool（推后激活） |

### speak 示例

```json
{
  "v": 1, "id": "01J8ZA", "type": "speak", "sent_at": "2026-10-15T22:00:00+08:00",
  "text": "该准备明天的饭啦",
  "audio_b64": "SUQzBAAAAAA…",
  "format": "mp3",
  "interrupt": true
}
```

## 4. 上行事件（evt）

| type | 干什么 | 字段 |
|---|---|---|
| `recording` | 语音上报（终端自主触发：按钮/唤醒词） | `audio_b64` str, `format`: webm/opus, `duration_s` float |
| `button` | 用户点了屏幕按钮 | `name`: ok\|snooze\|… |
| `presence` | 在场状态变化（摄像头本地检测，只报布尔，画面不出本机） | `state`: active\|away |
| `idle` | 键鼠活跃/离开 | `state`: active\|away |
| `ack` | 指令执行回执 | `cmd_id` str, `action`（= cmd.type）, `result`: displayed\|played\|failed |
| `slot` | 用户点按左侧页签（本地切换后上报） | `action`: activate, `slot_id` str, `label` str |

### ack 示例

```json
{ "v": 1, "id": "01J8ZC", "type": "ack", "cmd_id": "01J8ZA", "action": "speak", "result": "played" }
```

## 5. 规则

1. **单条消息自足**：所有字段（含 base64 媒体）在一条 JSON 里；无跨主题配对、无顺序依赖。
2. 二进制只出现在 `audio_b64`、`image_b64` 两个字段；HTML/卡片是纯文本。
3. 单条消息 ≤ 1MB（broker 硬上限；base64 膨胀 33%，原始内容 ≤ 700KB）。录音 ≤ 10s；speak 文案一两句；图片 ≤ 300KB。
4. 视频/大文件不走 MQTT。
5. 每条显示指令带 `until` 过期时间，到期终端自动回待机时钟；`until` 缺省 = 常驻直到下一条指令。
6. 终端对每条 cmd 回一条 `ack`：执行成功回 displayed/played，失败回 failed（action 附在字段里）。
7. `listen` 仅用于多轮对话回合交接；日常拾音是终端本地行为（不由云端驱动）。
8. status 消息体：`{ "state": "online"|"offline", "view": "clock|card|html|image|speak|off|slot", "ts": … }`，retained。`view=slot` 表示正在显示某常驻页签。
9. **常驻页签（slot）语义**（2026-11-12）：
   - `slot set` 建立/更新页签；首个页签自动激活，`activate=true` 显式激活；同 `slot_id` 重复 set = 更新内容（内容变了重载该槽 iframe，否则只改元数据）。
   - 用户点左侧页签按钮 = 本地切换，同时上报 `slot` evt；切页签会清掉临时全屏层（card/html/image）。
   - 临时层（fullscreen 卡片 / html / 图片）显示时盖住页签；卡片 `until` 到期自动回当前页签，无 `until` 的临时层等 `clear` 或用户切页签。
   - banner 卡片与页签共存（底部条 + 当前页签）。
   - `clear` 只清临时层不动页签；`slot clear` 清空全部页签回时钟。
   - `html` 指令保留为**临时全屏层**（兼容旧调用）；常驻页面一律走 `slot set`。
