"""WebUI 的 Starlette 应用。

路由分两类：
- 页面：/、/u/{up主}、/v/{BV号}、/download 都返回同一个前端外壳，由前端做路由；
- 接口：/api/** 提供 JSON 数据，/media/** 提供视频与封面文件。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from webui.auth import TokenAuthMiddleware
from webui.library import find_video, load_library
from webui.tasks import TaskManager, run_task

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

# 下载任务管理器
manager = TaskManager()


def _shell() -> HTMLResponse:
    """返回前端外壳页面。"""
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


async def page_index(request):
    """up主列表页。"""
    return _shell()


async def page_uploader(request):
    """up主详情页（视频列表）。"""
    return _shell()


async def page_video(request):
    """视频播放页。"""
    return _shell()


async def page_download(request):
    """下载页。"""
    return _shell()


async def api_library(request):
    """整个下载库的索引。"""
    uploaders = await load_library()
    return JSONResponse({"uploaders": [u.to_dict() for u in uploaders]})


async def api_uploader(request):
    """单个 up 主的详情。"""
    name = request.path_params["name"]
    for uploader in await load_library():
        if uploader.name == name or uploader.uid == name:
            return JSONResponse(uploader.to_dict())
    return JSONResponse({"error": "未找到该 up 主"}, status_code=404)


async def api_video(request):
    """单个视频的详情（含所属 up 主）。"""
    bvid = request.path_params["bvid"]
    found = await find_video(bvid)
    if not found:
        return JSONResponse({"error": "未找到该视频"}, status_code=404)
    uploader, video = found
    payload = video.to_dict()
    payload["uploader"] = {"name": uploader.name, "uid": uploader.uid}
    return JSONResponse(payload)


async def media_video(request):
    """视频文件（支持 Range 请求，可拖动进度条）。"""
    bvid = request.path_params["bvid"]
    path = await _find_media(bvid, video=True)
    if path is None:
        return JSONResponse({"error": "未找到视频文件"}, status_code=404)
    return FileResponse(path, media_type="video/mp4")


async def media_cover(request):
    """视频封面图片。"""
    bvid = request.path_params["bvid"]
    path = await _find_media(bvid, video=False)
    if path is None:
        return JSONResponse({"error": "未找到封面"}, status_code=404)
    return FileResponse(path, media_type="image/jpeg")


async def _find_media(bvid: str, *, video: bool) -> Path | None:
    """在下载目录中定位视频或封面文件。"""
    from webui.library import find_media_file

    return find_media_file(bvid, video=video)


async def api_download_start(request):
    """提交下载任务，支持一次提交多个 BV 号。"""
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"error": "请求体不是合法 JSON"}, status_code=400)

    # 兼容单个 bvid 与批量 bvids 两种写法
    raw = payload.get("bvids")
    if raw is None:
        raw = [payload.get("bvid")]
    if not isinstance(raw, list):
        raw = [raw]

    bvids: list[str] = []
    invalid: list[str] = []
    for item in raw:
        bvid = str(item or "").strip()
        if not bvid:
            continue
        if not bvid.startswith("BV"):
            invalid.append(bvid)
            continue
        if bvid not in bvids:
            bvids.append(bvid)

    if not bvids:
        if invalid:
            return JSONResponse(
                {"error": f"BV 号应以 BV 开头，例如 BV1dfJk6hEjX（无效：{', '.join(invalid)}）"},
                status_code=400,
            )
        return JSONResponse({"error": "请输入 BV 号"}, status_code=400)

    semaphore = manager._get_semaphore()
    tasks = []
    for bvid in bvids:
        task = manager.start(bvid)
        asyncio.create_task(run_task(task, semaphore))
        tasks.append(task)

    return JSONResponse({"tasks": [t.to_dict() for t in tasks], "invalid": invalid})


async def api_downloads(request):
    """列出全部下载任务（用于页面恢复与多任务并行展示）。"""
    return JSONResponse({"tasks": [t.to_dict() for t in manager.list()]})


async def api_download_status(request):
    """查询单个下载任务的状态与进度。"""
    task_id = request.path_params["task_id"]
    task = manager.get(task_id)
    if task is None:
        return JSONResponse({"error": "任务不存在或已过期"}, status_code=404)
    return JSONResponse(task.to_dict())


def create_app() -> Starlette:
    """构造 Starlette 应用。"""
    routes = [
        Route("/", page_index),
        Route("/u/{name}", page_uploader),
        Route("/v/{bvid}", page_video),
        Route("/download", page_download),
        Route("/api/library", api_library),
        Route("/api/uploaders/{name}", api_uploader),
        Route("/api/videos/{bvid}", api_video),
        Route("/api/download", api_download_start, methods=["POST"]),
        Route("/api/downloads", api_downloads),
        Route("/api/download/{task_id}", api_download_status),
        Route("/media/video/{bvid}", media_video),
        Route("/media/cover/{bvid}", media_cover),
        Mount("/static", StaticFiles(directory=STATIC_DIR), name="static"),
    ]
    return Starlette(
        routes=routes,
        middleware=[Middleware(TokenAuthMiddleware)],
    )


app = create_app()
