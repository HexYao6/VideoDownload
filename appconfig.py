"""常规配置。

配置来源（后者覆盖前者）：

1. 内置默认值（见 :data:`DEFAULTS`）
2. 项目根目录的 ``config.json``
3. 环境变量

所有路径都相对项目根目录解析，所以整个项目可以随意搬动。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_FILE = PROJECT_ROOT / "config.json"

# 内置默认值
DEFAULTS: dict[str, Any] = {
    "ffmpeg": {
        # 存放 ffmpeg / ffprobe 可执行文件的目录
        "dir": "tools/ffmpeg",
        # 指定具体的 ffmpeg 可执行文件；留空则用上面的目录里的
        "path": "",
    },
    "download": {
        # 视频保存目录
        "dir": "downloads",
    },
    "cookie": {
        # Cookie 文件（Netscape 格式），留空则不注入
        "file": "cookies.txt",
    },
    "server": {
        # WebUI 监听地址与端口
        "host": "0.0.0.0",
        "port": 8000,
    },
}

# 环境变量覆盖：{(节, 键): 环境变量名}
ENV_OVERRIDES: dict[tuple[str, str], str] = {
    ("ffmpeg", "path"): "VIDEODOWNLOAD_FFMPEG_PATH",
    ("ffmpeg", "dir"): "VIDEODOWNLOAD_FFMPEG_DIR",
    ("download", "dir"): "VIDEODOWNLOAD_DOWNLOAD_DIR",
    ("cookie", "file"): "VIDEODOWNLOAD_COOKIE_FILE",
    ("server", "host"): "VIDEODOWNLOAD_HOST",
    ("server", "port"): "VIDEODOWNLOAD_PORT",
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个字典，override 优先。"""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict:
    """读取并合并全部配置。"""
    config = _deep_merge(DEFAULTS, {})

    if CONFIG_FILE.is_file():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                config = _deep_merge(config, data)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"⚠️ 配置文件解析失败（{CONFIG_FILE}）: {exc}")

    for (section, key), env_name in ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if value not in (None, ""):
            config.setdefault(section, {})[key] = value

    return config


def resolve_path(value: str | os.PathLike) -> Path:
    """把配置里的路径解析成绝对路径（相对路径按项目根目录）。"""
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def ffmpeg_dir() -> Path:
    """存放 ffmpeg 可执行文件的目录。"""
    return resolve_path(load_config()["ffmpeg"]["dir"])


def ffmpeg_path() -> Path | None:
    """解析实际使用的 ffmpeg 可执行文件。

    优先级：配置里指定的 path → 配置的 dir 目录下的 ffmpeg → 系统 PATH。
    找不到时返回 None（此时调用方应给出明确提示）。
    """
    config = load_config()["ffmpeg"]

    explicit = (config.get("path") or "").strip()
    if explicit:
        candidate = resolve_path(explicit)
        if candidate.is_file():
            return candidate
        print(f"⚠️ 配置指定的 ffmpeg 不存在: {candidate}")

    bundled = ffmpeg_dir() / "ffmpeg"
    if bundled.is_file():
        return bundled

    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def download_dir() -> Path:
    """视频保存目录。"""
    return resolve_path(load_config()["download"]["dir"])


def cookie_file() -> Path:
    """Cookie 文件路径。"""
    return resolve_path(load_config()["cookie"]["file"])


def server_host() -> str:
    """WebUI 监听地址。"""
    return str(load_config()["server"]["host"])


def server_port() -> int:
    """WebUI 监听端口。"""
    try:
        return int(load_config()["server"]["port"])
    except (TypeError, ValueError):
        return 8000
