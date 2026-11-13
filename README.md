# 拾光 NAS Photos

适合家庭 NAS 的轻量相册。支持照片和视频时间线、自动翻页、HEIC 大图预览、多目录管理、地点聚合地图、本地人脸识别、回收站和对外分享。按 4GB 内存设备设计，扫描串行执行，无需独立显卡。

项目：https://github.com/zbulrush-spec/nasphotos

## 从镜像仓库安装（推荐 Compose）

镜像地址：`crpi-44sb4bvpcm655d55.cn-beijing.personal.cr.aliyuncs.com/zbulrush/nasphotos:latest`。镜像包含 AMD64 和 ARM64，Docker 自动选择架构，极空间 Z2Pro / RK3568 使用 ARM64。

镜像托管在阿里云容器镜像服务（ACR）。需要登录 ACR 才能推送镜像；公开拉取请在 ACR 将仓库设为公开。

在极空间 Docker 的 Compose 页面新建项目，选择项目保存位置，复制仓库中的 [compose.yaml](compose.yaml)。**只需修改照片 `source` 为 NAS 上已有的照片根目录**，启动项目。

- `config` 自动创建在 Compose 项目保存目录中，映射为容器 `/config`。
- 数据库、会话密钥、缩略图和预览目录首次启动自动初始化。
- 不需要 `.env`，不需要填写环境变量，不需要手动新建 config 文件夹。
- 照片挂载路径不存在时启动会报错，不会自动创建一个空照片目录。

打开 `http://NAS地址:8080`，设置管理员密码，在“图库设置”页面勾选一个或多个照片目录，保存后点击“扫描图库”。照片目录直接包含图片时，勾选“选择当前目录”。

照片必须先由 Docker 授权挂载；网页只能选择挂载范围内的目录，不会自行访问 NAS 其他文件夹。照片目录需要读写权限以实现回收站。

### 在本地镜像页面手动创建容器

也可自定义拉取 `crpi-44sb4bvpcm655d55.cn-beijing.personal.cr.aliyuncs.com/zbulrush/nasphotos:latest`，再添加到容器：

| 项目 | 配置 |
| --- | --- |
| 端口 | 本地 8080 → 容器 8080 |
| 照片 | NAS 照片根目录 → `/media`，读写 |
| 配置（建议显式保存） | 应用配置目录 → `/config`，读写 |
| 内存 | 建议 2560MB |
| 重启 | 自动重启 |
| 环境变量 | 不需要 |

手动创建容器且不映射 `/config` 时，Docker 也会自动创建配置卷，但这是匿名卷；重新创建容器时需复用该卷才能保留密码和索引。**希望自动创建且便于升级，请使用上述 Compose 方式。**

## 已安装 0.1.0 / 0.1.1 的升级方式

不要在正在扫描时更换容器。当前任务未持久化，中断后需要重新点击扫描，已保存的索引和缩略图可复用。

旧安装使用 `/data`：升级时继续把原数据目录映射到 `/data`，保持照片目录在容器内的原路径。新版自动识别旧映射并继续使用，不会迁移、覆盖或清空它；旧环境里显式设置的 `DATA_DIR` 也继续生效。

**不要为了新目录名将旧安装切换到一个空的 config 目录。** 只替换镜像，保留原数据和照片映射。Compose 示例面向新安装；旧项目应保留原有的 `/data` 映射配置。

之后更新同一项目：

```bash
docker compose pull
docker compose up -d
```

不要使用删除持久数据卷的选项，不要删除 config 或原 data 文件夹。回退镜像前应先备份数据库，未来数据库升级可能不支持直接降级。

## 从 GitHub 源码安装

```bash
git clone https://github.com/zbulrush-spec/nasphotos.git
cd nasphotos
# 修改 compose.yaml 中的照片 source 为已有 NAS 照片目录
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

离线镜像导出（需要 Docker Buildx）：

```bash
bash scripts/build-image.sh linux/arm64
# Intel / AMD 使用 linux/amd64
```

## 数据和功能

- 登录密码以哈希保存，配置保存在 SQLite 中；下拉时间线会自动加载下一页。
- 照片详情先显示缩略图，原图加载完成后替换；视频按实际缓冲进度显示加载条。
- 地点页使用内置 Leaflet 组件和 OpenStreetMap 在线底图，按缩放级别聚合照片数量，放大到最小范围后可查看区域内全部照片。
- “图库设置”为独立页面，管理多目录、手动扫描和人脸识别；扫描完成提示可以关闭。
- HEIC/HEIF 由本机解码生成 JPEG 预览，原文件保持原样，下载仍为原格式。
- 多目录递归扫描，已有缩略图和未变化文件可跳过处理；进度显示发现、处理和失败数量。
- 日期优先读取拍摄元数据，没有时使用文件修改时间；GPS 写入数据库。
- 删除会实际将源文件移动到父目录中的 `.nasphotos-trash`，支持恢复，按删除时间排列，满30天永久删除。每小时检查，容器启动时补执行。
- 分享链接支持密码、有效期、撤销和下载开关；被删除的照片立即停止分享。下载开关不防复制；原文件可能包含 GPS。
- 最近删除保留缩略图和详情预览，支持从详情恢复到原目录；已删除项目不能创建分享。
- 人物页按人脸分组浏览照片并支持命名；图库设置中点击“识别图库人物”运行增量识别。识别过程和照片扫描串行执行。
- 单管理员，单扫描或识别任务，一个 Gunicorn worker。配置和缓存保存在同一持久化目录，原片保存在照片挂载中。

## 本地人脸识别

同一个 Docker 内集成 [mt-photos-insightface-unofficial](https://github.com/dev-fox-101/mt-photos-insightface-unofficial) 服务和 InsightFace CPU 推理。构建阶段下载并校验 buffalo_l 的全部五个 ONNX 文件，直接打包进镜像；容器启动和首次识别无需再下载模型。服务仅监听容器内 `127.0.0.1:8066`，对外仍只开放 8080。

模型按需加载，连续空闲五分钟后释放；建议为容器分配 2560MB 内存。识别照片和人脸向量保存在本机，不上传到外部服务。新照片扫描完成后，在图库设置中运行识别，未变化的照片会跳过。识别目前处理静态照片，人物分组可能需要人工确认；视频人脸识别尚未包含。

预训练 buffalo_l 模型遵循上游的非商业研究用途限制，详见 [第三方说明](vendor/mt-photos-insightface/NOTICE.md)。模型文件存放在镜像内，不提交大体积二进制到 Git 仓库。

## 外网访问

在极空间配置 HTTPS 域名和反向代理到容器端口，代理保留原始 Host。先在局域网完成管理员设置，再开放外网。从外网域名访问后创建的分享链接才能供外网访客使用。镜像不会自动配置域名、公网入口或内网穿透。

## 开发与测试

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p media
python app.py
python -m unittest discover -s tests -v
node --check static/app.js
node --check static/folder-picker.js
# 可选：pip install playwright && playwright install chromium
python scripts/test-browser.py # 无截图浏览器交互测试
```

本地默认使用 `./data`。开发或特殊部署可用 `DATA_DIR`、`MEDIA_ROOT` 指定目录，普通 NAS 安装无需设置。FFmpeg/FFprobe 在镜像中已包含，本地开发需另外安装。

Docker 端到端测试（人脸测试需要准备一张包含清晰人脸的本地照片）：

```bash
TEST_IMAGE=nasphotos:0.2.0 python scripts/smoke-image.py --config-target /config
TEST_IMAGE=nasphotos:0.2.0 python scripts/smoke-image.py --config-target /data
python scripts/test-recognition.py --image nasphotos:0.2.0 --sample /path/to/face.jpg
```

Docker 镜像由 ACR 托管。推送多架构镜像前，先用 ACR 页面提供的访问凭证登录，然后运行 `bash scripts/publish-acr.sh`。脚本会发布 `latest` 标签；登录密码只在终端交互输入，不保存在代码库中。

## 当前版本边界

这是核心流程预览版，尚未实现视频转码、多用户权限、独立多图库、相册分享、Live Photo 配对、RAW 预览、手机备份、定时扫描和持久化任务恢复。地点底图需要联网；视频直接播放取决于浏览器编码支持。

时区尚未完整统一；文件操作尚无可恢复的崩溃日志；公网暴力登录封禁和多因素认证尚未实现。请保留原片独立备份。人脸识别采用容器内本地服务。开发测试使用生成的媒体文件，尚未在用户极空间实机上验证所有功能。
