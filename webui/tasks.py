"""后台下载任务管理。

下载是耗时且可能失败的长任务，WebUI 用轮询的方式跟踪进度：
提交下载后拿到 task_id，前端定时拉取状态与日志。
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

from starlette.concurrency import run_in_threadpool

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# main.py 里的 COOKIE_FILE_PATH 是相对当前工作目录的，这里按项目根目录解析
COOKIE_FILE = PROJECT_ROOT / "cookies.txt"

# 任务保留时长（秒），超过后自动清理，避免内存无限增长
TASK_TTL = 6 * 3600


@dataclass
class DownloadTask:
    """一个下载任务的状态。"""

    task_id: str
    bvid: str
    status: str = "pending"  # pending / running / success / failed
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def to_dict(self, since: int = 0) -> dict:
        """返回状态字典；since 用于只取增量日志。"""
        return {
            "taskId": self.task_id,
            "bvid": self.bvid,
            "status": self.status,
            "error": self.error,
            "logs": self.logs[since:],
            "logOffset": len(self.logs),
            "createdAt": self.created_at,
            "finishedAt": self.finished_at,
        }


class _LogCollector:
    """在后台线程里收集输出（同时转发到服务端 stdout，便于排查）。"""

    def __init__(self, task: DownloadTask) -> None:
        self._task = task
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        with self._lock:
            for line in text.splitlines():
                self._task.logs.append(line)
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


class TaskManager:
    """下载任务集合。"""

    def __init__(self) -> None:
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = threading.Lock()

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
        """登记并启动一个下载任务。"""
        self._prune()
        task = DownloadTask(task_id=uuid.uuid4().hex[:12], bvid=bvid, status="running")
        with self._lock:
            self._tasks[task.task_id] = task
        return task


def _download_sync(bvid: str, collector: _LogCollector) -> None:
    """真正执行下载的同步函数（运行在线程池里）。"""
    from Bilibili.main import download_bilibili_video

    cookie = str(COOKIE_FILE) if COOKIE_FILE.is_file() else None
    with redirect_stdout(collector), redirect_stderr(collector):
        download_bilibili_video(bvid, cookie=cookie)


async def run_task(task: DownloadTask) -> None:
    """在后台执行下载并更新任务状态。"""
    collector = _LogCollector(task)
    try:
        await run_in_threadpool(_download_sync, task.bvid, collector)
    except Exception as exc:  # 下载失败不应影响服务本身
        task.status = "failed"
        task.error = str(exc) or exc.__class__.__name__
    else:
        task.status = "success"
    finally:
        task.finished_at = time.time()
