"""WebUI 启动入口。

监听地址与端口默认取自 config.json 的 server 节。

用法：
    uv run python -m webui                          # 用配置里的地址端口（局域网可访问）
    uv run python -m webui --host 127.0.0.1         # 仅本机访问
    uv run python -m webui --port 8080
"""

from __future__ import annotations

import argparse
import socket
import sys

import uvicorn

import appconfig
from webui.auth import TOKEN_ENV, get_token

# 默认值取自 config.json 的 server 节
DEFAULT_HOST = appconfig.server_host()
DEFAULT_PORT = appconfig.server_port()


def detect_lan_ip() -> str | None:
    """探测本机的局域网地址。

    连接到 TEST-NET-1（192.0.2.1）不会真的发包，只是让内核按默认路由
    选出出口网卡，从而拿到该网卡的地址。
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.2)
            sock.connect(("192.0.2.1", 9))
            ip = sock.getsockname()[0]
    except OSError:
        return None
    return None if ip.startswith("127.") else ip


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 VideoDownload WebUI")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"监听地址（默认 {DEFAULT_HOST}，即所有网卡；仅本机请用 127.0.0.1）",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"监听端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--reload", action="store_true", help="代码变更时自动重载（开发用）")
    args = parser.parse_args()

    print("🎬 VideoDownload WebUI 已启动：")
    print(f"   本机:   http://127.0.0.1:{args.port}")
    if args.host in ("0.0.0.0", "::"):
        lan_ip = detect_lan_ip()
        if lan_ip:
            print(f"   局域网: http://{lan_ip}:{args.port}   ← 用同一局域网的设备打开")
        else:
            print("   局域网: 未探测到可用地址")
    else:
        print(f"   监听:   http://{args.host}:{args.port}（仅本机可达）")

    if args.host in ("0.0.0.0", "::") and not get_token():
        print()
        print("⚠️  已监听所有网卡且未设置访问口令，同网段任何设备都能访问并触发下载。")
        print(f"    如需加口令：export {TOKEN_ENV}=你的口令")
    sys.stdout.flush()

    uvicorn.run("webui.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
