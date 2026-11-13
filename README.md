# 拾光 NAS Photos

适合家庭 NAS 的轻量相册。支持照片和视频时间线、缩略图、HEIC 大图预览、多目录绑定、GPS 信息、回收站和对外分享。按 4GB 内存设备设计，扫描串行执行，无需独立显卡。

项目：https://github.com/zbulrush-spec/nasphotos

## 从镜像仓库安装（推荐 Compose）

镜像地址：`ghcr.io/zbulrush-spec/nasphotos:latest`。同一地址包含 AMD64 和 ARM64，Docker 自动选择架构，极空间 Z2Pro / RK3568 使用 ARM64。

镜像由 GitHub Actions 在测试通过后发布。首次发布的 GHCR 包默认可能是私有的，仓库管理员需要在 GitHub 的 Packages → nasphotos → Package settings 中将可见性设为 Public，然后验证匿名拉取。

在极空间 Docker 的 Compose 页面新建项目，选择项目保存位置，复制仓库中的 [compose.yaml](compose.yaml)。**只需修改照片 `source` 为 NAS 上已有的照片根目录**，启动项目。

- `config` 自动创建在 Compose 项目保存目录中，映射为容器 `/config`。
- 数据库、会话密钥、缩略图和预览目录首次启动自动初始化。
- 不需要 `.env`，不需要填写环境变量，不需要手动新建 config 文件夹。
- 照片挂载路径不存在时启动会报错，不会自动创建一个空照片目录。

打开 `http://NAS地址:8080`，设置管理员密码，在网页勾选一个或多个照片目录并扫描。照片目录直接包含图片时，勾选“选择当前目录”。

照片必须先由 Docker 授权挂载；网页只能选择挂载范围内的目录，不会自行访问 NAS 其他文件夹。照片目录需要读写权限以实现回收站。

### 在本地镜像页面手动创建容器

也可自定义拉取 `ghcr.io/zbulrush-spec/nasphotos:latest`，再添加到容器：

| 项目 | 配置 |
| --- | --- |
| 端口 | 本地 8080 → 容器 8080 |
| 照片 | NAS 照片根目录 → `/media`，读写 |
| 配置（建议显式保存） | 应用配置目录 → `/config`，读写 |
| 内存 | 建议 1536MB |
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

- 登录密码以哈希保存，配置保存在 SQLite 中；列表分页加载缩略图。
- HEIC/HEIF 由本机解码生成 JPEG 预览，原文件保持原样，下载仍为原格式。
- 多目录递归扫描，已有缩略图和未变化文件可跳过处理；进度显示发现、处理和失败数量。
- 日期优先读取拍摄元数据，没有时使用文件修改时间；GPS 写入数据库。
- 删除会实际将源文件移动到父目录中的 `.nasphotos-trash`，支持恢复，满30天永久删除。每小时检查，容器启动时补执行。
- 分享链接支持密码、有效期、撤销和下载开关；被删除的照片立即停止分享。下载开关不防复制；原文件可能包含 GPS。
- 单管理员，单扫描任务，一个 Gunicorn worker。配置和缓存保存在同一持久化目录，原片保存在照片挂载中。

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
```

本地默认使用 `./data`。开发或特殊部署可用 `DATA_DIR`、`MEDIA_ROOT` 指定目录，普通 NAS 安装无需设置。FFmpeg/FFprobe 在镜像中已包含，本地开发需另外安装。

Docker 端到端测试：

```bash
TEST_IMAGE=nasphotos:0.1.2 python scripts/smoke-image.py --config-target /config
TEST_IMAGE=nasphotos:0.1.2 python scripts/smoke-image.py --config-target /data
```

GitHub Actions 自动运行 Python/JS/Compose 检查、容器新配置和旧路径兼容测试，再发布多架构镜像；发布 `v*` Git 标签时生成对应版本镜像标签。只使用 Actions 自动提供的 `GITHUB_TOKEN`，无需手动配置发布密钥。

## 当前版本边界

这是核心流程预览版，尚未实现内嵌地图、人脸识别、视频转码、多用户权限、独立多图库、相册分享、Live Photo 配对、RAW 预览、手机备份、定时扫描和持久化任务恢复。地点目前为列表和外部地图链接，视频直接播放取决于浏览器编码支持。

时区尚未完整统一；文件操作尚无可恢复的崩溃日志；公网暴力登录封禁和多因素认证尚未实现。请保留原片独立备份。模型、人像功能后续计划通过可选本地识别服务接入。开发测试使用生成的媒体文件，尚未在用户极空间实机上验证所有功能。
