#!/usr/bin/env bash
set -euo pipefail

ACR_IMAGE="${ACR_IMAGE:-crpi-44sb4bvpcm655d55.cn-beijing.personal.cr.aliyuncs.com/zbulrush/nasphotos:latest}"
ACR_USERNAME="${ACR_USERNAME:?Set ACR_USERNAME to the login name shown in ACR}"
ACR_REGISTRY_HOST="${ACR_IMAGE%%/*}"

docker login "$ACR_REGISTRY_HOST" --username "$ACR_USERNAME"
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag "$ACR_IMAGE" \
  --push \
  .
