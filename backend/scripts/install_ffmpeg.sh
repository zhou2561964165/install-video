#!/usr/bin/env bash
# 一键安装 ffmpeg（Linux）
set -e
if command -v apt >/dev/null 2>&1; then
  sudo apt update && sudo apt install -y ffmpeg
elif command -v brew >/dev/null 2>&1; then
  brew install ffmpeg
else
  echo "请手动安装 ffmpeg 并加入 PATH"
  exit 1
fi
