"""VideoDownload 的简易 WebUI。

基于 Starlette，提供 up主列表 → 视频列表 → 播放 的三级浏览，以及一个按 BV 号下载的页面。
"""

from webui.app import create_app

__all__ = ["create_app"]
