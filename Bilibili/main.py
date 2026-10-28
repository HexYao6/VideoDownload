"""
基于 yt-dlp 的 B 站（bilibili）视频下载。
入参为 B 站视频的 BV 号，下载保存地址（目录）通过单独变量定义并提供默认值。
每个视频按 up 主名称单独建立文件夹，同时下载视频封面，并在该文件夹下写入两个 json：
- up.json     ：up 主基本信息（名称、uid）及其视频 BV 号列表（增量、去重、按 BV 号排序）
- videos.json ：以 BV 号为 key 的视频明细（增量、覆盖、按 BV 号排序）
"""

import json
from datetime import datetime
from pathlib import Path

import requests
import yt_dlp
from yt_dlp.utils import sanitize_filename

# ==================== 可配置变量 ====================
# 视频下载保存地址（目录），默认为项目根目录下的 downloads 文件夹
DOWNLOAD_DIR_PATH = str(Path(__file__).resolve().parent.parent / "downloads")

# B 站视频 URL 前缀，最终 URL 形如 https://www.bilibili.com/video/BVxxxxxxxxx
BILIBILI_URL_PREFIX = "https://www.bilibili.com/video/"

# up 主基本信息文件名称
UP_INFO_FILE_NAME = "up.json"

# 视频基本信息文件名称（以 BV 号为 key 汇总多条记录）
VIDEO_INFO_FILE_NAME = "videos.json"

# 封面默认图片格式（无法从封面 URL 解析出扩展名时使用）
DEFAULT_THUMBNAIL_EXT = "jpg"

# 允许识别为封面的图片扩展名
IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "gif", "bmp")

# 下载/更新时间格式
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# Cookie 文件路径（用于解锁大会员画质）
COOKIE_FILE_PATH = r"cookies.txt"


# ====================================================


def _pick_thumbnail(info: dict) -> tuple[str, str]:
    """从 yt-dlp 的 info 中挑选分辨率最高的封面，返回 (封面URL, 扩展名)。"""
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        url = thumbnails[-1].get("url") or info.get("thumbnail")
    else:
        url = info.get("thumbnail")

    if not url:
        raise RuntimeError("未获取到视频封面地址。")

    # 从 URL 解析图片扩展名，解析失败则使用默认格式
    ext = DEFAULT_THUMBNAIL_EXT
    last_seg = url.split("?")[0].split("/")[-1]
    if "." in last_seg:
        candidate = last_seg.rsplit(".", 1)[-1].lower()
        if candidate in IMAGE_EXTS:
            ext = candidate
    return url, ext


def _download_thumbnail(thumb_url: str, save_path: Path) -> None:
    """下载封面到指定路径（B 站图片 CDN 需带 Referer，否则可能 403）。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    }
    resp = requests.get(thumb_url, headers=headers, stream=True)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def _load_json(path: Path, default):
    """读取 json 文件，不存在或解析失败时返回给定的默认值。"""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"⚠️ 已有的 {path.name} 解析失败，将重建该文件。")
        return default


def _merge_video_records(videos_path: Path, bvid: str, new_record: dict) -> dict:
    """视频明细增量合并（以 BV号 为 key）：新记录覆盖同 key 旧记录，
    按 BV号 升序排序后整体覆盖写回，结构为 { BV号: {视频明细} }。"""
    data = _load_json(videos_path, {})
    records = data if isinstance(data, dict) else {}

    # 新记录覆盖同 BV号 的旧记录（更新时间等字段）
    records[bvid] = new_record

    # 按 BV号 升序排序，保证文件整体有序
    result = {k: records[k] for k in sorted(records)}
    videos_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def _update_up_info(up_path: Path, uploader: str, uploader_id: str, bvid: str) -> dict:
    """更新 up 主基本信息：合并视频 BV 号列表，去重并按升序排序后覆盖写回。"""
    data = _load_json(up_path, {})
    up_info = data if isinstance(data, dict) else {}

    bvs = set(up_info.get("视频BV号列表", []))
    bvs.add(bvid)

    up_info["up主名称"] = uploader
    up_info["up主uid"] = uploader_id
    up_info["视频BV号列表"] = sorted(bvs)

    up_path.write_text(
        json.dumps(up_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return up_info


def _apply_cookie_opts(ydl_opts: dict, cookie) -> None:
    """按传入的 cookie 参数决定 yt-dlp 的认证方式（就地修改 ydl_opts）。

    - None / 空串: 回退使用全局 COOKIE_FILE_PATH（非空且文件存在时注入 cookiefile）；
    - str: 视为 Netscape cookies.txt 文件路径，注入 cookiefile；
    - tuple/list: 视为浏览器 Cookie 来源 (浏览器名, profile, keyring, container)，
      注入 cookiesfrombrowser，用于直接从已登录浏览器读取登录态。
    """
    if isinstance(cookie, (tuple, list)):
        browser_spec = tuple(cookie)
        ydl_opts["cookiesfrombrowser"] = browser_spec
        print(f"🍪 使用浏览器 Cookie: {browser_spec}")
        return

    path = cookie if (isinstance(cookie, str) and cookie) else COOKIE_FILE_PATH
    if path and Path(path).exists():
        ydl_opts["cookiefile"] = path
        print(f"🍪 使用 Cookie 文件: {path}")
    else:
        print("⚠️ 未提供有效 Cookie，未登录状态下无法下载 1080P60 等大会员画质。")


def download_bilibili_video(bvid: str, download_dir: str = DOWNLOAD_DIR_PATH, cookie=None) -> str:
    """根据 BV 号使用 yt-dlp 下载 B 站视频。

    - 每个视频按 up 主名称单独建立一个文件夹；
    - 下载视频封面，命名为 BV号 + 图片格式（如 BVxxxx.jpg）；
    - 在该文件夹下写入两个 json：
        up.json     记录 up 主名称/uid 及视频 BV 号列表（增量、去重、有序）
        videos.json 以 BV 号为 key 记录每条视频明细（增量、覆盖、有序）

    参数:
        bvid: B 站视频的 BV 号（必填），例如 "BV1GJ411x7h7"。
        download_dir: 视频保存地址（目录），默认使用 DOWNLOAD_DIR_PATH。
        cookie: Cookie 来源（可选），用于解锁大会员画质。可传：
                None（默认，回退使用 COOKIE_FILE_PATH）、cookies.txt 文件路径(str)、
                或浏览器来源元组，如 ("chrome",) / ("edge", "Default", None, None)。

    返回:
        该 up 主文件夹的路径。
    """
    if not bvid:
        raise ValueError("BV 号为必填项，不能为空。")

    # 校验 BV 号基本格式（BV + 数字/字母，不强制长度）
    if not bvid.startswith("BV"):
        raise ValueError(f"无效的 B 站 BV 号: {bvid}")

    video_url = f"{BILIBILI_URL_PREFIX}{bvid}"

    # 输出模板：以 up 主名称作为子文件夹，视频文件以 BV 号命名
    outtmpl = str(Path(download_dir) / "%(uploader)s" / f"{bvid}.%(ext)s")

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "noplaylist": True,
    }

    # 根据可选参数自由切换 Cookie 来源（文件 / 浏览器 / 默认）
    _apply_cookie_opts(ydl_opts, cookie)

    print(f"🔗 待下载视频 URL: {video_url}")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)

    uploader = info.get("uploader") or info.get("channel") or "unknown_uploader"
    uploader_id = info.get("uploader_id") or info.get("channel_id") or ""
    title = info.get("title", bvid)

    # up 主文件夹（与 %(uploader)s 使用同样的规则计算路径）
    uploader_dir = Path(download_dir) / sanitize_filename(uploader)

    print(f"👤 up主名称: {uploader} (uid: {uploader_id})")
    print(f"📹 视频标题: {title}")
    print(f"📂 up主文件夹: {uploader_dir}")

    # 下载封面，文件名为 BV号 + 图片格式
    thumb_url, thumb_ext = _pick_thumbnail(info)
    cover_name = f"{bvid}.{thumb_ext}"
    cover_path = uploader_dir / cover_name
    _download_thumbnail(thumb_url, cover_path)
    print(f"🖼️ 封面下载完成: {cover_path}")

    # 定位实际下载的视频文件（合并后扩展名可能变化）
    video_files = [
        p for p in uploader_dir.glob(f"{bvid}.*")
        if p.suffix.lower().lstrip(".") not in IMAGE_EXTS and p.suffix.lower() != ".json"
    ]
    video_file = video_files[0] if video_files else uploader_dir / f"{bvid}.mp4"

    # 分别写入两个 json：视频明细（videos.json，以 BV号 为 key）+ up 主信息（up.json）
    video_record = {
        "视频名称": title,
        "视频封面": cover_name,
        "视频下载与更新时间": datetime.now().strftime(TIME_FORMAT),
    }
    videos_path = uploader_dir / VIDEO_INFO_FILE_NAME
    records = _merge_video_records(videos_path, bvid, video_record)

    up_path = uploader_dir / UP_INFO_FILE_NAME
    _update_up_info(up_path, uploader, uploader_id, bvid)

    print(f"📝 已更新: {up_path} 与 {videos_path}（视频明细共 {len(records)} 条）")

    print(f"🎉 下载完成: {video_file}")
    return str(uploader_dir)


if __name__ == "__main__":
    BVS = [
        # "BV12YhW6dEXm",
        # "BV1uznn6fELX",
        # "BV1Syn16aErc",
        "BV1dfJk6hEjX"
    ]
    for bvid in BVS:
        download_bilibili_video(bvid)
    # 直接替换成你要下载的 B 站视频 BV 号
    # download_bilibili_video("BV12YhW6dEXm")
