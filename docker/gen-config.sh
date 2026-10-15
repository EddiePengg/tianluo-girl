#!/bin/sh
# 容器启动时由环境变量生成 js/config.js —— 配置不入仓，改密码后重启容器即生效。
# 本地调试：OUT=/tmp/config.js sh docker/gen-config.sh
set -e

OUT="${OUT:-/usr/share/nginx/html/js/config.js}"

cat > "$OUT" <<EOF
// 本文件由容器启动脚本按环境变量生成，勿手改；改配置请改容器环境变量
window.TIANLUO_CONFIG = {
  WS_URL: "${WS_URL:-wss://broker.emqx.io:8084/mqtt}",
  USERNAME: "${MQTT_USERNAME:-}",
  PASSWORD: "${MQTT_PASSWORD:-}",
  DEVICE_ID: "${DEVICE_ID:-girl-01}",
};
EOF

echo "[tianluo] config.js generated -> $OUT (device=${DEVICE_ID:-girl-01})"
