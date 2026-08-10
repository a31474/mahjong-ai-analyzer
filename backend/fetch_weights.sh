#!/usr/bin/env bash
# 从 HuggingFace 下载 kdens3 三学生权重到 backend/weights/
# 用法: bash backend/fetch_weights.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)/weights"
BASE="https://huggingface.co/Dannibal/ijcai-mahjong-ckpts-2026/resolve/main/champion"
for i in 0 1 2; do
  curl -L -o "$DIR/kdens_s${i}_fp16.npz" "$BASE/kdens_s${i}_fp16.npz"
done
ls -la "$DIR"
