"""下载库索引：扫描 downloads 目录，构建 up主 → 视频 的两级索引。

数据全部来自落盘的文件（up.json / videos.json），因此 WebUI 展示的内容与
命令行下载的结果始终一致，不存在额外索引文件需要维护。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import aiofiles

from Bilibili.main import DOWNLOAD_DIR_PATH, _normalize_duration

# 视频文件扩展名（按优先级排列，取第一个命中的）
VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".flv", ".mov", ".m4v", ".ts")
# 图片扩展名
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


@dataclass(slots=True)
class VideoItem:
    """一条视频记录。"""

    bvid: str
    title: str
    description: str = ""
    cover: str | None = None
    duration: int | None = None
    updated_at: str = ""
    has_video: bool = False
    has_cover: bool = False

    def to_dict(self) -> dict:
        return {
            "bvid": self.bvid,
            "title": self.title,
            "description": self.description,
            "cover": self.cover,
            "duration": self.duration,
            "updatedAt": self.updated_at,
            "hasVideo": self.has_video,
            "hasCover": self.has_cover,
        }


@dataclass(slots=True)
class UploaderItem:
    """一个 up 主及其视频列表。"""

    name: str
    uid: str = ""
    videos: list[VideoItem] = field(default_factory=list)

    @property
    def poster(self) -> str | None:
        """用最新一条视频的封面作为 up 主卡片封面。"""
        for video in self.videos:
            if video.has_cover:
                return video.cover
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "uid": self.uid,
            "videoCount": len(self.videos),
            "poster": self.poster,
            "videos": [v.to_dict() for v in self.videos],
        }


async def _read_json(path: Path) -> dict:
    """异步读取 json 文件，不存在或损坏时返回空字典。"""
    if not path.is_file():
        return {}
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _pick_video_file(folder: Path, bvid: str) -> Path | None:
    """在 up 主目录下找到该 BV 号对应的视频文件。"""
    for ext in VIDEO_EXTS:
        candidate = folder / f"{bvid}{ext}"
        if candidate.is_file():
            return candidate
    # 兜底：匹配任意非图片、非 json 的同名文件
    for path in sorted(folder.glob(f"{bvid}.*")):
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTS or suffix == ".json" or suffix == ".part":
            continue
        if path.is_file():
            return path
    return None


def _pick_cover_file(folder: Path, bvid: str, declared: str | None) -> Path | None:
    """确定封面文件：优先用 videos.json 里记录的，否则按 BV 号在目录里找。"""
    if declared:
        candidate = folder / declared
        if candidate.is_file():
            return candidate
    for ext in IMAGE_EXTS:
        candidate = folder / f"{bvid}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _build_video(folder: Path, bvid: str, record: dict) -> VideoItem:
    """把 videos.json 中的一条记录与磁盘上的文件对应起来。"""
    record = record if isinstance(record, dict) else {}
    video_path = _pick_video_file(folder, bvid)
    cover_path = _pick_cover_file(folder, bvid, record.get("视频封面"))

    title = (record.get("视频名称") or "").strip() or bvid
    description = (record.get("视频简介") or "").strip()
    duration = _normalize_duration(record.get("视频时长"))

    return VideoItem(
        bvid=bvid,
        title=title,
        description=description,
        cover=cover_path.name if cover_path else None,
        duration=duration,
        updated_at=(record.get("视频下载与更新时间") or ""),
        has_video=video_path is not None,
        has_cover=cover_path is not None,
    )


async def load_library(download_dir: str | Path | None = None) -> list[UploaderItem]:
    """扫描下载目录，返回 up主列表（按视频数量倒序）。"""
    root = Path(download_dir or DOWNLOAD_DIR_PATH)
    if not root.is_dir():
        return []

    uploaders: list[UploaderItem] = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue

        up_info = await _read_json(folder / "up.json")
        videos_raw = await _read_json(folder / "videos.json")

        # 磁盘上存在但尚未写进 videos.json 的视频也要能展示出来
        bvids = set(videos_raw)
        for path in folder.iterdir():
            if path.is_file() and path.stem.startswith("BV") and path.suffix.lower() in VIDEO_EXTS:
                bvids.add(path.stem)

        videos = [_build_video(folder, bvid, videos_raw.get(bvid, {})) for bvid in bvids]
        # 最新更新的排在前面
        videos.sort(key=lambda v: v.updated_at, reverse=True)

        name = (up_info.get("up主名称") or "").strip() or folder.name
        uploaders.append(
            UploaderItem(
                name=name,
                uid=str(up_info.get("up主uid") or ""),
                videos=videos,
            )
        )

    uploaders.sort(key=lambda u: (len(u.videos), u.name), reverse=True)
    return uploaders


async def find_video(bvid: str, download_dir: str | Path | None = None) -> tuple[UploaderItem, VideoItem] | None:
    """按 BV 号定位视频，返回 (up主, 视频)；找不到时返回 None。"""
    for uploader in await load_library(download_dir):
        for video in uploader.videos:
            if video.bvid == bvid:
                return uploader, video
    return None


def find_media_file(bvid: str, *, video: bool, download_dir: str | Path | None = None) -> Path | None:
    """在下载目录中定位某个 BV 号对应的视频文件或封面图片。

    播放/封面请求会频繁到达，这里直接按目录查找，不构建完整索引。
    """
    root = Path(download_dir or DOWNLOAD_DIR_PATH)
    if not root.is_dir():
        return None
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        if video:
            found = _pick_video_file(folder, bvid)
        else:
            found = _pick_cover_file(folder, bvid, None)
        if found is not None:
            return found
    return None
