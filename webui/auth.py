"""可选的访问口令。

WebUI 监听在局域网时，任何同网段的设备都能打开页面、触发下载。
设置环境变量 ``VIDEODOWNLOAD_TOKEN`` 即可启用一个简单口令：

    export VIDEODOWNLOAD_TOKEN=your-secret
    uv run python -m webui

未设置该环境变量时不启用鉴权，行为与之前一致。

口令可以通过三种方式提供：
- URL 查询参数 ``?token=xxx``（首次访问时带上，校验通过后会写入 Cookie）
- Cookie（校验通过后自动下发，后续请求无需再带参数）
- 请求头 ``X-Token``
"""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse, JSONResponse

TOKEN_ENV = "VIDEODOWNLOAD_TOKEN"
COOKIE_NAME = "vd_token"
# 口令有效期（秒），默认 7 天
COOKIE_MAX_AGE = 7 * 24 * 3600


def get_token() -> str:
    """读取配置的口令，未配置则返回空字符串（表示不鉴权）。"""
    return (os.environ.get(TOKEN_ENV) or "").strip()


def _token_page(path: str) -> HTMLResponse:
    """未授权时返回的输入口令页面。"""
    import html

    safe_path = html.escape(path)
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VideoDownload · 需要口令</title>
<style>
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:#0f1115; color:#e6e8ee;
         font:15px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }}
  .box {{ background:#171a21; border:1px solid #272c37; border-radius:12px; padding:32px; width:340px; }}
  h1 {{ margin:0 0 6px; font-size:19px; }}
  p {{ color:#949bab; font-size:13px; margin:0 0 20px; }}
  input {{ width:100%; box-sizing:border-box; background:#1e222b; border:1px solid #272c37;
           color:#e6e8ee; padding:10px 14px; border-radius:9px; font-size:14px; }}
  input:focus {{ outline:none; border-color:#4a9eff; }}
  button {{ width:100%; margin-top:12px; background:#4a9eff; color:#fff; border:0;
            padding:10px; border-radius:9px; font-size:14px; cursor:pointer; }}
  button:hover {{ filter:brightness(1.1); }}
  .err {{ color:#ff6b6b; font-size:13px; margin-top:12px; }}
</style>
</head>
<body>
  <form class="box" method="get" action="{safe_path}">
    <h1>🎬 VideoDownload</h1>
    <p>该服务已启用访问口令，请输入后继续。</p>
    <input type="password" name="token" placeholder="访问口令" autofocus required>
    <button type="submit">进入</button>
  </form>
</body>
</html>""",
        status_code=401,
    )


async def token_middleware(request, call_next):
    """校验访问口令的中间件逻辑。"""
    token = get_token()
    if not token:
        return await call_next(request)

    # 已通过口令校验（Cookie）
    if request.cookies.get(COOKIE_NAME) == token:
        return await call_next(request)

    supplied = request.query_params.get("token") or request.headers.get("X-Token")
    if supplied == token:
        response = await call_next(request)
        response.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            max_age=COOKIE_MAX_AGE,
        )
        return response

    # 未授权：接口类返回 JSON，页面类返回输入口令的表单
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return _token_page(request.url.path)
    return JSONResponse({"error": "需要访问口令"}, status_code=401)


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """把口令校验挂到 Starlette 的中间件栈上。"""

    async def dispatch(self, request, call_next):
        return await token_middleware(request, call_next)
