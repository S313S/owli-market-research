"""§D-082 尺子：两份 tables.json 结构化对比（只读）。

用法：
    ../Owli/.venv/bin/python scripts/acceptance/d082/diff_tables.py <A.json> <B.json> [--show 6]

打印：顶层键差异；每张表（tables.*）行数、不等的行；omitted_tables 差异；
sources 逐角标不等字段计数；platform_mix 两侧全表。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--show", type=int, default=6)
    ns = ap.parse_args()
    a, b = _load(ns.a), _load(ns.b)
    print("顶层键不等：", sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k)))
    ta, tb = a.get("tables", {}), b.get("tables", {})
    print("只在 A 的表：", sorted(set(ta) - set(tb)), "只在 B 的表：", sorted(set(tb) - set(ta)))
    for name in sorted(set(ta) & set(tb)):
        if ta[name] == tb[name]:
            continue
        ra, rb = ta[name].get("rows", []), tb[name].get("rows", [])
        meta = sorted(k for k in set(ta[name]) | set(tb[name])
                      if k != "rows" and ta[name].get(k) != tb[name].get(k))
        print(f"\n== 表 {name}: 行数 {len(ra)} → {len(rb)}；非 rows 键不等 {meta}")
        for key in meta:
            print(f"   {key}: {json.dumps(ta[name].get(key), ensure_ascii=False)[:300]}")
            print(f"   {' ' * len(key)}→ {json.dumps(tb[name].get(key), ensure_ascii=False)[:300]}")
        sa = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in ra]
        sb = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rb]
        gone = [r for r in sa if r not in sb]
        new = [r for r in sb if r not in sa]
        print(f"   仅 A 行 {len(gone)}、仅 B 行 {len(new)}")
        for r in gone[:ns.show]:
            print("   - ", r[:400])
        for r in new[:ns.show]:
            print("   + ", r[:400])
    if a.get("omitted_tables") != b.get("omitted_tables"):
        print("\nomitted_tables A：", json.dumps(a.get("omitted_tables"), ensure_ascii=False)[:600])
        print("omitted_tables B：", json.dumps(b.get("omitted_tables"), ensure_ascii=False)[:600])
    sa = {s["mark"]: s for s in a.get("sources", [])}
    sb = {s["mark"]: s for s in b.get("sources", [])}
    fields = Counter()
    samples: dict[str, list] = {}
    for mark in sorted(set(sa) & set(sb)):
        for key in set(sa[mark]) | set(sb[mark]):
            if sa[mark].get(key) != sb[mark].get(key):
                fields[key] += 1
                samples.setdefault(key, []).append(
                    (mark, sa[mark].get(key), sb[mark].get(key)))
    print("\nsources 角标集合相同：", set(sa) == set(sb), "；逐字段不等计数：", dict(fields))
    for key, rows in samples.items():
        for mark, va, vb in rows[:ns.show]:
            print(f"   {key} {mark}: {json.dumps(va, ensure_ascii=False)[:120]} → "
                  f"{json.dumps(vb, ensure_ascii=False)[:120]}")
    for label, side in (("A", ta), ("B", tb)):
        pm = side.get("platform_mix", {}).get("rows", [])
        print(f"\nplatform_mix {label}：")
        for row in pm:
            print("   ", {k: v for k, v in row.items() if k != "marks"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
