# VideoDownload

自用的视频下载工具

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 下载 B 站视频，按 up 主自动分目录保存，
同时下载封面并维护 up 主 / 视频的 json 索引。

## 环境要求

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)（推荐）

## 安装

```bash
uv sync
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
- `videos.json`：以 BV 号为 key 记录视频名称、封面与下载更新时间（增量、覆盖、按 BV 号排序）

## 配置项

可在 `Bilibili/main.py` 顶部修改：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DOWNLOAD_DIR_PATH` | `<项目根>/downloads` | 视频保存目录 |
| `BILIBILI_URL_PREFIX` | `https://www.bilibili.com/video/` | 视频 URL 前缀 |
| `COOKIE_FILE_PATH` | `cookies.txt` | Cookie 文件路径 |
| `UP_INFO_FILE_NAME` | `up.json` | up 主信息文件名 |
| `VIDEO_INFO_FILE_NAME` | `videos.json` | 视频明细文件名 |
