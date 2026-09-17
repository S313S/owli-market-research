"""§D-082 尺子：两库两研究的 evidence 按 permalink 对齐，逐列比（只读，不经 Store）。

用法：
    ../Owli/.venv/bin/python scripts/acceptance/d082/diff_rows.py \
        <库A> <研究A> <库B> <研究B> [--skip col,col] [--show N]

打印：两侧行数、只在一侧的 permalink 数（分平台）、每列不等的行数与前 N 个样本；
另打印 reports.extra 的顶层键差异（键集合、值是否相等）。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter


def _rows(db: str, rid: str):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM evidence WHERE report_id = ?", (rid,)
        )]
        cols = [c[1] for c in con.execute("PRAGMA table_info(evidence)")]
        extra = con.execute("SELECT extra FROM reports WHERE id = ?", (rid,)).fetchone()
    finally:
        con.close()
    by = {r["permalink"]: r for r in rows}
    assert len(by) == len(rows), f"{db} {rid} permalink 不唯一"
    return cols, by, json.loads(extra[0] or "{}") if extra else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db_a"); ap.add_argument("rid_a")
    ap.add_argument("db_b"); ap.add_argument("rid_b")
    ap.add_argument("--skip", default="id,report_id")
    ap.add_argument("--show", type=int, default=3)
    ns = ap.parse_args()
    cols_a, a, extra_a = _rows(ns.db_a, ns.rid_a)
    cols_b, b, extra_b = _rows(ns.db_b, ns.rid_b)
    skip = set(filter(None, ns.skip.split(",")))
    print(f"A {ns.db_a} {ns.rid_a}: {len(a)} 行；B {ns.db_b} {ns.rid_b}: {len(b)} 行")
    print("列集合相同：", cols_a == cols_b)
    only_a = Counter((a[p]["platform"], a[p]["source_type"]) for p in set(a) - set(b))
    only_b = Counter((b[p]["platform"], b[p]["source_type"]) for p in set(b) - set(a))
    print("只在 A：", dict(only_a))
    print("只在 B：", dict(only_b))
    common = sorted(set(a) & set(b))
    print("共有 permalink：", len(common))
    for col in cols_a:
        if col in skip or col not in cols_b:
            continue
        bad = [p for p in common if a[p][col] != b[p][col]]
        if not bad:
            continue
        pairs = Counter((str(a[p][col])[:40], str(b[p][col])[:40]) for p in bad)
        print(f"  列 {col}: 不等 {len(bad)} 行；样本（A→B 前 {ns.show} 种）：",
              pairs.most_common(ns.show))
    keys_a, keys_b = set(extra_a), set(extra_b)
    print("reports.extra 只在 A 的键：", sorted(keys_a - keys_b))
    print("reports.extra 只在 B 的键：", sorted(keys_b - keys_a))
    diff_keys = sorted(k for k in keys_a & keys_b if extra_a[k] != extra_b[k])
    print("reports.extra 值不等的键：", diff_keys)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
