#!/bin/sh
# 容器启动时由环境变量生成 js/config.js —— 配置不入仓，改密码后重启容器即生效。
# 本地调试：OUT=/tmp/config.js sh docker/gen-config.sh
#
# 2026-11-24 起 config.js 已入仓（含默认连接配置）：
#   - 仓库里已有 config.js 时直接沿用，不再用环境变量覆盖（解决 Dokploy 环境变量
#     里的旧地址/旧账号覆盖新配置的问题）
#   - 确需用环境变量重新生成时，设 REGEN_CONFIG=1 再重启容器
set -e

OUT="${OUT:-/usr/share/nginx/html/js/config.js}"

if [ -f "$OUT" ] && [ "${REGEN_CONFIG:-0}" != "1" ]; then
  echo "[tianluo] config.js 已存在（入仓配置），跳过生成。如需环境变量覆盖请设 REGEN_CONFIG=1"
  exit 0
fi

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
