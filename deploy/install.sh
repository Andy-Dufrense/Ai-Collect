#!/usr/bin/env bash

# 将项目安装到 Ubuntu 云服务器并设置为开机自启。
# 用法：sudo bash deploy/install.sh

set -euo pipefail

PROJECT_SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="/opt/ai-music"
APP_USER="ai-music"

if [[ "${EUID}" -ne 0 ]]; then
    echo "请使用 sudo 运行：sudo bash deploy/install.sh" >&2
    exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip nginx rsync

if ! id "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --home-dir "${TARGET_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

install -d -o "${APP_USER}" -g "${APP_USER}" "${TARGET_DIR}"
install -d -o "${APP_USER}" -g "${APP_USER}" "${TARGET_DIR}/data"

# 保留已部署数据库、日志和授权公众号源，不覆盖运行时数据。
rsync -a \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '.venv' \
    --exclude 'data' \
    --exclude 'custom_sources.json' \
    "${PROJECT_SOURCE}/" "${TARGET_DIR}/"

if [[ ! -f "${TARGET_DIR}/custom_sources.json" ]]; then
    printf '{\n  "sources": []\n}\n' > "${TARGET_DIR}/custom_sources.json"
fi

if [[ ! -d "${TARGET_DIR}/.venv" ]]; then
    python3 -m venv "${TARGET_DIR}/.venv"
fi
"${TARGET_DIR}/.venv/bin/pip" install --upgrade pip
"${TARGET_DIR}/.venv/bin/pip" install -r "${TARGET_DIR}/requirements.txt"

install -m 644 \
    "${TARGET_DIR}/deploy/ai-music-web.service" \
    /etc/systemd/system/ai-music-web.service
install -m 644 \
    "${TARGET_DIR}/deploy/ai-music-worker.service" \
    /etc/systemd/system/ai-music-worker.service
install -m 644 \
    "${TARGET_DIR}/deploy/nginx-ai-music.conf" \
    /etc/nginx/sites-available/ai-music
ln -sfn /etc/nginx/sites-available/ai-music /etc/nginx/sites-enabled/ai-music
rm -f /etc/nginx/sites-enabled/default

chown -R "${APP_USER}:${APP_USER}" "${TARGET_DIR}"

systemctl daemon-reload
systemctl enable --now ai-music-web.service
systemctl enable --now ai-music-worker.service
nginx -t
systemctl enable --now nginx
systemctl reload nginx

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    ufw allow 'Nginx Full'
fi

server_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "部署完成。"
echo "访问地址：http://${server_ip}/"
echo "服务状态：systemctl status ai-music-web ai-music-worker"
echo "实时日志：journalctl -u ai-music-worker -f"
