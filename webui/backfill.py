"""回填 videos.json 中缺失的元数据（视频简介、时长等）。

早期版本下载的视频只记录了名称与封面，WebUI 需要简介才能展示，
可以用本模块把已有下载补齐：

    uv run python -m webui.backfill
    uv run python -m webui.backfill --force   # 强制重新抓取全部元数据
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from Bilibili.main import DOWNLOAD_DIR_PATH, _normalize_duration, fetch_video_info

VIDEO_INFO_FILE_NAME = "videos.json"
# 已经记录了简介的视频视为最新，无需重复请求接口
NEED_KEY = "视频简介"


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def backfill(download_dir: str | Path | None = None, force: bool = False) -> int:
    """回填所有 up 主目录下缺失的元数据，返回更新的视频数量。"""
    root = Path(download_dir or DOWNLOAD_DIR_PATH)
    if not root.is_dir():
        print(f"下载目录不存在: {root}")
        return 0

    updated = 0
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        videos_path = folder / VIDEO_INFO_FILE_NAME
        records = _read_json(videos_path)
        if not records:
            continue

        changed = False
        for bvid, record in list(records.items()):
            if not isinstance(record, dict):
                continue
            if not force and (record.get(NEED_KEY) or record.get("视频时长")):
                continue

            print(f"→ 回填 {folder.name}/{bvid} …")
            try:
                info = fetch_video_info(bvid)
            except Exception as exc:
                print(f"  ✗ 失败: {exc}")
                continue

            description = (info.get("description") or "").strip()
            duration = _normalize_duration(info.get("duration"))
            # 只补空字段，不覆盖已有内容
            if description and not record.get(NEED_KEY):
                record[NEED_KEY] = description
            if duration and not record.get("视频时长"):
                record["视频时长"] = duration
            changed = True
            updated += 1

        if changed:
            videos_path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"  ✓ 已更新 {videos_path}")

    print(f"共回填 {updated} 个视频")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="回填 videos.json 中缺失的视频简介与时长")
    parser.add_argument("--dir", default=None, help="下载目录（默认使用项目内的 downloads）")
    parser.add_argument("--force", action="store_true", help="强制重新抓取全部元数据")
    args = parser.parse_args()
    backfill(args.dir, force=args.force)


if __name__ == "__main__":
    main()
