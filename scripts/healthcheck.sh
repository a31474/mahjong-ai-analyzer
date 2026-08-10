#!/usr/bin/env bash
# 启动自检：轮询 /api/health 直到就绪或超时。
# 用途：systemd ExecStartPost 等 —— 模型加载成功（200 ok）返回 0，
#       模型缺失/服务未起/超时返回非 0（systemd 判定启动失败）。
# 用法：healthcheck.sh [URL] [RETRIES] [INTERVAL]
#       或环境变量 HEALTHCHECK_URL / HEALTHCHECK_RETRIES / HEALTHCHECK_INTERVAL
set -uo pipefail

URL="${1:-${HEALTHCHECK_URL:-http://127.0.0.1:8000/api/health}}"
RETRIES="${2:-${HEALTHCHECK_RETRIES:-60}}"
INTERVAL="${3:-${HEALTHCHECK_INTERVAL:-1}}"

for ((i = 1; i <= RETRIES; i++)); do
    body="$(curl -sf --max-time 2 "$URL" 2>/dev/null)" && {
        echo "[healthcheck] ready: $body"
        exit 0
    }
    sleep "$INTERVAL"
done

echo "[healthcheck] FAILED: 服务在 ${RETRIES}x${INTERVAL}s 内未就绪（$URL）" >&2
exit 1
