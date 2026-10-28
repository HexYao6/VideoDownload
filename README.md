# VideoDownload

自用的视频下载工具

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 下载 B 站视频，按 up 主自动分目录保存，
同时下载封面并维护 up 主 / 视频的 json 索引。

附带一个简易 WebUI：浏览已下载的 up 主 / 视频、在线播放，也可以直接输入 BV 号下载。

## 环境要求

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)（推荐）
- **ffmpeg**（必需）：`bestvideo+bestaudio` 需要它把音视频流合并成 mp4，缺失时 yt-dlp 会直接中止

## 安装

```bash
uv sync

# 系统依赖（ffmpeg）
apt-get install ffmpeg      # Debian / Ubuntu
brew install ffmpeg         # macOS
```

## 使用

编辑 `Bilibili/main.py` 末尾的 `BVS` 列表，然后运行：

```bash
uv run python Bilibili/main.py
```

也可以直接调用函数：

```python
from Bilibili.main import download_bilibili_video

download_bilibili_video("BV1dfJk6hEjX")
```

### WebUI

```bash
uv run python -m webui                      # 默认 127.0.0.1:8000
uv run python -m webui --host 0.0.0.0 --port 8080
```

界面分三层：

| 页面 | 路径 | 说明 |
| --- | --- | --- |
| 视频库 | `/` | 按 up 主分组展示所有已下载内容 |
| up 主详情 | `/u/<up主名>` | 该 up 主下的视频列表（封面 + 名称 + 简介） |
| 播放页 | `/v/<BV号>` | 在线播放，显示标题、时长与简介 |
| 下载 | `/download` | 输入 BV 号即可下载，页面实时显示进度与日志 |

前端是原生 JS + JSON 接口，没有额外的模板引擎依赖。

**回填视频简介**：早期版本下载的视频没有记录简介，可用下面的命令补齐：

```bash
uv run python -m webui.backfill           # 只补缺失的
uv run python -m webui.backfill --force   # 强制重新抓取
```

### Cookie（可选）

未登录状态下无法下载 1080P60 等大会员画质，可通过以下方式提供登录态：

| 方式 | 说明 |
| --- | --- |
| `cookies.txt` | 将 Netscape 格式的 cookies 文件放在项目根目录，默认自动读取 |
| 浏览器 Cookie | 传入元组，如 `("chrome",)`、`("edge", "Default", None, None)`，直接从已登录浏览器读取 |

```python
download_bilibili_video("BV1dfJk6hEjX", cookie=("chrome",))
```

> `cookies.txt` 与 `cookies/` 已在 `.gitignore` 中忽略，避免误提交登录凭证。

### 风控与网络

B 站有较强的风控，程序已做三层处理：

1. **伪装浏览器 UA** —— 否则接口会直接返回 `412` 风控页；
2. **伪装 TLS 指纹**（`curl_cffi` 的 `impersonate`）—— 仅改 UA 仍会被识别并限流；
3. **重试** —— 页面、接口、封面与整体提取都带退避重试，应对链路抖动。

> 若所在网络的出口对 B 站存在干扰（连接被挂起或中途重置），下载仍可能失败。
> 此时建议配置 `cookies.txt`（登录态请求通常不受未登录风控限制），或在网络正常的机器上运行。

## 输出结构

下载结果默认保存在项目根目录的 `downloads/` 下，每个 up 主一个文件夹：

```
downloads/
└── <up主名称>/
    ├── BVxxxx.mp4        # 视频
    ├── BVxxxx.jpg        # 封面
    ├── up.json           # up 主信息 + 视频 BV 号列表
    └── videos.json       # 以 BV 号为 key 的视频明细
```

- `up.json`：记录 up 主名称、uid，以及该 up 主下已下载视频的 BV 号列表（增量、去重、按 BV 号排序）
- `videos.json`：以 BV 号为 key 记录视频名称、封面、简介、时长与下载更新时间（增量、覆盖、按 BV 号排序）

## 配置项

可在 `Bilibili/main.py` 顶部修改：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DOWNLOAD_DIR_PATH` | `<项目根>/downloads` | 视频保存目录 |
| `BILIBILI_URL_PREFIX` | `https://www.bilibili.com/video/` | 视频 URL 前缀 |
| `COOKIE_FILE_PATH` | `cookies.txt` | Cookie 文件路径 |
| `USER_AGENT` | Chrome/131 | 请求 UA，需伪装成浏览器以绕过风控 |
| `IMPERSONATE_NAME` | `chrome` | TLS 指纹伪装目标 |
| `SOCKET_TIMEOUT` | 60 | 单次请求超时（秒） |
| `MAX_RETRIES` | 3 | 单个请求的重试次数 |
| `MAX_ATTEMPTS` | 5 | 整体提取的重试次数 |
| `UP_INFO_FILE_NAME` | `up.json` | up 主信息文件名 |
| `VIDEO_INFO_FILE_NAME` | `videos.json` | 视频明细文件名 |
