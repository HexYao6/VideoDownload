"""WebUI 启动入口。

用法：
    uv run python -m webui            # 默认 127.0.0.1:8000
    uv run python -m webui --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 VideoDownload WebUI")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    parser.add_argument("--reload", action="store_true", help="代码变更时自动重载（开发用）")
    args = parser.parse_args()

    print(f"🎬 VideoDownload WebUI: http://{args.host}:{args.port}")
    uvicorn.run("webui.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
