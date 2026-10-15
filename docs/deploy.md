# 部署

## 1. EMQX Cloud Serverless（一次性）

1. 控制台创建 Serverless 部署：**杭州区**（或就近区域）、消费限额 0。
   创建后得到部署域名（形如 `xxxx.ala.cn-hangzhou.emqxsl.cn`），端口固定 8883（MQTT/TLS）/ 8084（WebSocket/TLS）。
2. **认证鉴权（Authentication）**：加两个用户，例如 `tianluo`（终端用）、`hermes`（大脑用）。
   注意：Serverless **强制认证**，不建用户连不上（匿名会被 CONNACK 134 拒绝）。
3. **访问控制 → 授权**（白名单模式，建议）：
   - All Users：`#` → **deny**（兜底拒绝）
   - 终端用户：`tianluo/terminal/girl-01/#` → pubsub allow
   - 大脑用户：`tianluo/#` → pubsub allow

## 2. 填两处本地配置（模板入仓，真配置不入仓）

```bash
cp web/js/config.example.js web/js/config.js                                # 填 WS_URL + 终端用户账密
cp skills/tianluo-girl/config.example.json skills/tianluo-girl/config.json  # 填大脑用户账密
```

改完浏览器**强制刷新** Cmd+Shift+R，否则旧 config.js 缓存不生效。

## 3. 工控机：静态服务 + kiosk 自启

终端页需要本机静态服务（getUserMedia 安全上下文 + kiosk 加载）：

```bash
python3 -m http.server 8000 --directory /opt/tianluo-girl/web
```

**Windows**：快捷方式放 `shell:startup`
```
chrome.exe --kiosk http://localhost:8000 --autoplay-policy=no-user-gesture-required
```
**Linux（chromium）**：systemd 起 http.server + 禁休眠（`xset s off; xset -dpms` 或 wayland 等价物），chromium 参数同上。FydeOS 同理（Chromium kiosk + Linux 容器跑静态服务）。
**macOS**（调试用）：
```
open -na "Google Chrome" --args --kiosk http://localhost:8000 --autoplay-policy=no-user-gesture-required
```

要点：
- `--autoplay-policy=no-user-gesture-required` 必须有，否则语音播报无声
- 浏览器自动更新建议关掉（专用 profile），防止 kiosk 被打断
- 系统电源设置：屏幕不自动关闭，或配合 `screen` 指令做熄屏
- 大脑（skill 工具包）可跑在任何有网的机器：`python3 skills/tianluo-girl/scripts/scheduler.py`

## 4. 验证清单

1. 工控机打开页面 → 右上角徽标"已连接 girl-01"
2. 任一台机器：`python3 skills/tianluo-girl/scripts/publish.py card --title "测试" --item "你好" --wait-ack 5` → 大屏显示卡片，终端回 `[ack] displayed`
3. `python3 skills/tianluo-girl/scripts/publish.py speak "该准备明天的饭啦" --wait-ack 10` → 出声 + `[ack] played`
4. `python3 skills/tianluo-girl/scripts/scheduler.py --now` → 卡片 + 播报

## 5. Docker / Dokploy 部署（备选）

`web/` 是纯静态站。仓库提供 all-in-one `Dockerfile`：nginx 伺服 + **容器启动时按环境变量生成 `js/config.js`**（配置依然不入仓，改密码只需重启容器）。

```bash
# 自建镜像
docker build -t tianluo-web .
docker run -d -p 8000:80 \
  -e WS_URL=wss://<部署域名>:8084/mqtt \
  -e MQTT_USERNAME=tianluo -e MQTT_PASSWORD=tianluo \
  tianluo-web
```

**Dokploy 配置清单**：
- Provider：GitHub → `EddiePengg/tianluo-girl`，branch `main`，Trigger：On Push
- Build Type：**Dockerfile**（Static 模式零 Docker 也可用——Publish Directory 填 `web`——但 config.js 需另用文件挂载注入，不推荐）
- Environment 标签页填：

  | 变量 | 值 |
  |---|---|
  | `WS_URL` | `wss://<部署域名>:8084/mqtt` |
  | `MQTT_USERNAME` | 终端用的认证用户（如 `tianluo`） |
  | `MQTT_PASSWORD` | 对应密码 |
  | `DEVICE_ID` | `girl-01` |

- Domains 标签页绑域名（如 `tianluo.example.com`）→ Traefik 自动 HTTPS。部署后 Logs 里应出现 `[tianluo] config.js generated`。
- 工控机 kiosk 直接指向该域名即可，本地 `python3 -m http.server` 可以退休；kiosk 启动参数仍需 `--autoplay-policy=no-user-gesture-required`。

注意：Environment 里的值等同密码，别截图外发。
