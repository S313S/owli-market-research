"""§D-082：用 SQLite backup API 取只读快照（⛔ 不用 cp，cp 会漏 WAL）。

沿用 §REISSUE-1 `scripts/acceptance/reissue1/snapshot.py`，只把研究 id 改成参数。

用法：
    ../Owli/.venv/bin/python scripts/acceptance/d082/snapshot.py <源库> <快照路径> [研究id ...]

源库一律 `file:...?mode=ro` 打开；目标已存在就拒绝（⛔ 不覆盖任何快照）。
取完打印源库读前读后 mtime、integrity_check 与每个研究的 evidence 读数。
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def _mtimes(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            stat = candidate.stat()
            out[candidate.name] = (
                f"{datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')} "
                f"{stat.st_size}B"
            )
    return out


def main() -> int:
    source = Path(sys.argv[1]).resolve()
    target = Path(sys.argv[2]).resolve()
    research_ids = sys.argv[3:]
    if not source.is_file():
        print(f"源库不存在：{source}")
        return 2
    if target.exists():
        print(f"快照已存在，拒绝覆盖：{target}")
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    before = _mtimes(source)
    taken_at = datetime.now().astimezone().isoformat(timespec="seconds")
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    after = _mtimes(source)
    check = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    readings: dict[str, object] = {}
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        user_version = check.execute("PRAGMA user_version").fetchone()[0]
        for rid in research_ids:
            rows = check.execute(
                "SELECT kind, source_type, COUNT(*), "
                "SUM(CASE WHEN COALESCE(parent_permalink,'')<>'' THEN 1 ELSE 0 END) "
                "FROM evidence WHERE report_id = ? GROUP BY kind, source_type",
                (rid,),
            ).fetchall()
            readings[rid] = [list(r) for r in rows]
    finally:
        check.close()
    print(json.dumps({
        "source": str(source), "target": str(target), "taken_at": taken_at,
        "source_mtime_before": before, "source_mtime_after": after,
        "mtime_unchanged": before == after,
        "bytes": target.stat().st_size, "integrity_check": integrity,
        "user_version": user_version, "evidence_kind_by_source_type": readings,
    }, ensure_ascii=False, indent=1))
    os.sync()
    return 0 if integrity == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
