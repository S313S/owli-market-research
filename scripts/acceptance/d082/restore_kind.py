"""§D-082：按 permalink 从复制链源头恢复 evidence 的 kind / parent_permalink。

货 1 只在本包 `var/` 下的副本上用（⛔ 默认拒绝写 `var/` 以外的库）；
货 2 写沙盒库要显式 `--sandbox-ok` 且给出已存在的写前快照 `--snapshot`。

用法：
    ../Owli/.venv/bin/python scripts/acceptance/d082/restore_kind.py <目标库> \
        --source var/wx1-source.db [--source-id r-20271e8a5028] \
        [--id r-3b3482ca7f8b] [--apply]

不加 --apply 只打印将改多少行。源库一律 `mode=ro` ATTACH。
只改两列；源头没有同 permalink 的行（补采的 X/HN）不动。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

VAR = (Path(__file__).resolve().parents[3] / "var").resolve()
SANDBOX = (Path(__file__).resolve().parents[4] / "Owli-src5/var/src5-backfill.db").resolve()


def _readings(con: sqlite3.Connection, rid: str) -> dict:
    kinds = con.execute(
        "SELECT platform, kind, COUNT(*), SUM(COALESCE(parent_permalink,'')<>'') "
        "FROM evidence WHERE report_id=? GROUP BY 1,2 ORDER BY 1,2", (rid,)
    ).fetchall()
    mismatch = con.execute(
        "SELECT COUNT(*) FROM evidence t JOIN src.evidence s "
        "ON s.report_id=:sid AND s.permalink=t.permalink "
        "WHERE t.report_id=:rid AND (t.kind IS NOT s.kind "
        "OR t.parent_permalink IS NOT s.parent_permalink)",
        {"rid": rid, "sid": _readings.sid},
    ).fetchone()[0]
    unmatched = con.execute(
        "SELECT platform, kind, COUNT(*) FROM evidence t WHERE t.report_id=:rid AND NOT EXISTS "
        "(SELECT 1 FROM src.evidence s WHERE s.report_id=:sid AND s.permalink=t.permalink) "
        "GROUP BY 1,2", {"rid": rid, "sid": _readings.sid},
    ).fetchall()
    return {"by_platform_kind": [list(r) for r in kinds],
            "mismatch_vs_source": mismatch,
            "not_in_source": [list(r) for r in unmatched]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", type=Path)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--source-id", default="r-20271e8a5028")
    ap.add_argument("--id", default="r-3b3482ca7f8b")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sandbox-ok", action="store_true")
    ap.add_argument("--snapshot", type=Path)
    ns = ap.parse_args()
    target = ns.target.resolve()
    if not target.is_file():
        raise SystemExit(f"目标库不存在：{target}")
    if not target.is_relative_to(VAR):
        if not (ns.sandbox_ok and target == SANDBOX):
            raise SystemExit(f"拒绝：目标不在本包 var/ 下：{target}")
        if ns.snapshot is None or not ns.snapshot.resolve().is_file():
            raise SystemExit("拒绝：写沙盒库必须给出已存在的写前快照 --snapshot")
    _readings.sid = ns.source_id
    # 目标库按 URI 打开，ATTACH 才认 `?mode=ro`（否则只读参数被当成文件名的一部分）。
    con = sqlite3.connect(f"file:{target}", uri=True)
    con.execute("ATTACH DATABASE ? AS src", (f"file:{ns.source.resolve()}?mode=ro",))
    if con.execute("SELECT COUNT(*) FROM src.evidence WHERE report_id=?",
                   (ns.source_id,)).fetchone()[0] == 0:
        raise SystemExit(f"源库里没有 {ns.source_id} 的证据行，尺子取错了库")
    before = _readings(con, ns.id)
    changed = 0
    if ns.apply:
        with con:
            cur = con.execute(
                "UPDATE evidence SET kind = (SELECT s.kind FROM src.evidence s "
                "WHERE s.report_id=:sid AND s.permalink=evidence.permalink), "
                "parent_permalink = (SELECT s.parent_permalink FROM src.evidence s "
                "WHERE s.report_id=:sid AND s.permalink=evidence.permalink) "
                "WHERE report_id=:rid AND EXISTS (SELECT 1 FROM src.evidence s "
                "WHERE s.report_id=:sid AND s.permalink=evidence.permalink "
                "AND (s.kind IS NOT evidence.kind OR s.parent_permalink IS NOT evidence.parent_permalink))",
                {"rid": ns.id, "sid": ns.source_id},
            )
            changed = cur.rowcount
    after = _readings(con, ns.id)
    con.close()
    print(json.dumps({"target": str(target), "apply": ns.apply, "changed_rows": changed,
                      "before": before, "after": after}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
