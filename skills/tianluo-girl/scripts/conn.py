"""MQTT 连接助手：publish/scheduler/subscribe 共用。
paho-mqtt 2.x。端口 8883 或 MQTT_TLS=1 时自动启用 TLS。
配置见 skill 目录下的 config.json（环境变量同名可覆盖）。
"""
from __future__ import annotations

import ssl

import paho.mqtt.client as mqtt

from config import get


def connect(client_id: str) -> mqtt.Client:
    host = get("MQTT_HOST", "broker.emqx.io")
    port = int(get("MQTT_PORT", "1883"))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)

    user = get("MQTT_USERNAME")
    password = get("MQTT_PASSWORD")
    if user:
        client.username_pw_set(user, password)
    if port == 8883 or get("MQTT_TLS") == "1":
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

    client.connect(host, port, keepalive=60)
    client.loop_start()
    return client


def topics(device: str | None = None) -> dict:
    d = device or get("DEVICE_ID", "girl-01")
    base = f"tianluo/terminal/{d}"
    return {"cmd": base + "/cmd", "evt": base + "/evt", "status": base + "/status"}
