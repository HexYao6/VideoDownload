"""后台下载任务管理。

下载是耗时且可能失败的长任务，WebUI 用轮询的方式跟踪进度：
提交下载后拿到 task_id，前端定时拉取状态、进度与清晰度。

支持多条视频同时下载：任务提交后立即排队，由信号量限制同时进行的下载数，
避免对 B 站造成过大压力。
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
import uuid
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

from starlette.concurrency import run_in_threadpool

import appconfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 任务保留时长（秒），超过后自动清理，避免内存无限增长
TASK_TTL = 6 * 3600

# 同时进行的下载数量上限
DEFAULT_CONCURRENCY = 3


def cookie_file() -> Path:
    """Cookie 文件路径（config.json 的 cookie.file）。"""
    return appconfig.cookie_file()


def max_concurrency() -> int:
    """允许同时进行的下载数量。"""
    raw = os.environ.get("VIDEODOWNLOAD_CONCURRENCY")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_CONCURRENCY


@dataclass
class DownloadTask:
    """一个下载任务的状态。"""

    task_id: str
    bvid: str
    status: str = "pending"  # pending / running / success / failed
    phase: str = "等待中"
    percent: float = 0.0
    downloaded: int = 0
    total: int = 0
    speed: float | None = None
    eta: int | None = None
    title: str = ""
    uploader: str = ""
    quality: str = ""
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "taskId": self.task_id,
            "bvid": self.bvid,
            "status": self.status,
            "phase": self.phase,
            "percent": round(self.percent, 1),
            "downloaded": self.downloaded,
            "total": self.total,
            "speed": self.speed,
            "eta": self.eta,
            "title": self.title,
            "uploader": self.uploader,
            "quality": self.quality,
            "error": self.error,
            "createdAt": self.created_at,
            "finishedAt": self.finished_at,
        }


class _Quiet:
    """把被调用方的输出丢掉。

    下载进度已经通过 progress_hook 结构化上报，滚动日志没有展示价值，
    这里只是避免刷屏（真正的错误仍然会通过异常抛出来）。
    """

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def _make_progress_hook(task: DownloadTask):
    """构造 yt-dlp 进度回调，把下载状态同步到任务对象上。"""

    def hook(data: dict) -> None:
        # yt-dlp 传入的元数据键是 info_dict
        info = data.get("info_dict") or data.get("info") or {}
        if info.get("title"):
            task.title = str(info["title"])
        if info.get("uploader"):
            task.uploader = str(info["uploader"])
        if info.get("height"):
            from Bilibili.main import _quality_label

            task.quality = _quality_label(info.get("height"), info.get("fps"))

        status = data.get("status")
        if status == "downloading":
            downloaded = data.get("downloaded_bytes") or 0
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            task.downloaded = int(downloaded)
            task.total = int(total)
            task.percent = (downloaded / total * 100) if total else 0.0
            task.speed = data.get("speed")
            task.eta = data.get("eta")
            task.phase = "下载中"
        elif status == "finished":
            # 字节下载完毕，接下来是合并音视频流
            task.percent = 100.0
            task.phase = "合并处理中"
        elif status == "error":
            task.phase = "出错"

    return hook


def _download_sync(bvid: str, task: DownloadTask) -> None:
    """真正执行下载的同步函数（运行在线程池里）。"""
    from Bilibili.main import download_bilibili_video

    cookie_path = cookie_file()
    cookie = str(cookie_path) if cookie_path.is_file() else None
    quiet = _Quiet()
    with redirect_stdout(quiet), redirect_stderr(quiet):
        download_bilibili_video(
            bvid,
            cookie=cookie,
            progress_hook=_make_progress_hook(task),
        )


class TaskManager:
    """下载任务集合，支持并发执行。"""

    def __init__(self) -> None:
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = threading.Lock()
        self._semaphore: asyncio.Semaphore | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        """惰性创建信号量（需要绑定到当前事件循环）。"""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(max_concurrency())
        return self._semaphore

    def list(self) -> list[DownloadTask]:
        """按创建时间倒序列出所有任务。"""
        with self._lock:
            return sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)

    def get(self, task_id: str) -> DownloadTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def _prune(self) -> None:
        """清理过期任务。"""
        now = time.time()
        with self._lock:
            stale = [
                tid
                for tid, task in self._tasks.items()
                if task.finished_at is not None and now - task.finished_at > TASK_TTL
            ]
            for tid in stale:
                self._tasks.pop(tid, None)

    def start(self, bvid: str) -> DownloadTask:
        """登记一个下载任务并排队执行。"""
        self._prune()
        task = DownloadTask(task_id=uuid.uuid4().hex[:12], bvid=bvid, status="pending")
        with self._lock:
            self._tasks[task.task_id] = task
        return task


async def run_task(task: DownloadTask, semaphore: asyncio.Semaphore) -> None:
    """在后台执行下载并更新任务状态。"""
    async with semaphore:
        task.status = "running"
        task.phase = "解析中"
        try:
            await run_in_threadpool(_download_sync, task.bvid, task)
        except Exception as exc:  # 下载失败不应影响服务本身
            task.status = "failed"
            task.phase = "失败"
            task.error = str(exc) or exc.__class__.__name__
        else:
            task.status = "success"
            task.phase = "已完成"
            task.percent = 100.0
        finally:
            task.finished_at = time.time()
