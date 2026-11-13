#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
platform="${1:-linux/amd64}"
case "$platform" in
  linux/amd64) arch=amd64 ;;
  linux/arm64) arch=arm64 ;;
  *) echo '用法: bash scripts/build-image.sh [linux/amd64|linux/arm64]' >&2; exit 1 ;;
esac
if ! command -v docker >/dev/null 2>&1; then
  echo '未找到 Docker。请在已安装 Docker 且支持 buildx 的机器上执行。' >&2
  exit 1
fi
docker info >/dev/null
mkdir -p dist
docker buildx build --platform "$platform" --load -t nasphotos:0.1.2 .
docker image save -o "dist/nasphotos-0.1.2-${arch}.tar" nasphotos:0.1.2
echo "镜像已生成：dist/nasphotos-0.1.2-${arch}.tar"
