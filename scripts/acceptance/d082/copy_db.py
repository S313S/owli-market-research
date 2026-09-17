"""§D-082：从本包快照再取一份工作副本（backup API；目标必须在本包 var/ 下且不存在）。

用法：
    ../Owli/.venv/bin/python scripts/acceptance/d082/copy_db.py <源快照> <副本>
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

VAR = (Path(__file__).resolve().parents[3] / "var").resolve()


def main() -> int:
    source = Path(sys.argv[1]).resolve()
    target = Path(sys.argv[2]).resolve()
    if not target.is_relative_to(VAR):
        raise SystemExit(f"拒绝：副本不在本包 var/ 下：{target}")
    if target.exists():
        raise SystemExit(f"副本已存在，拒绝覆盖：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    print(f"{source} -> {target} {target.stat().st_size}B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
