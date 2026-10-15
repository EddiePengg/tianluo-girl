# 田螺姑娘 web 终端 all-in-one 镜像
# nginx 伺服 web/ 静态文件；容器启动时按环境变量生成 js/config.js（配置不入仓）。
# 用法：docker run -p 8000:80 \
#         -e WS_URL=wss://<部署域名>:8084/mqtt \
#         -e MQTT_USERNAME=tianluo -e MQTT_PASSWORD=tianluo \
#         tianluo-web
FROM nginx:alpine

# nginx 官方镜像的入口会自动执行 /docker-entrypoint.d/*.sh
COPY docker/gen-config.sh /docker-entrypoint.d/99-tianluo-config.sh
RUN chmod +x /docker-entrypoint.d/99-tianluo-config.sh

COPY web/ /usr/share/nginx/html/

EXPOSE 80
