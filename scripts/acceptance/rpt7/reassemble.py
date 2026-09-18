#!/usr/bin/env python3
"""§RPT-7 复验：拿一份**已经写完**的稿子，只重跑组装。

    python3 scripts/acceptance/rpt7/reassemble.py \
        --parts  ../Owli-src5/var/runs/r-3b3482ca7f8b/goals/polished/consulting-parts \
        --tables ../Owli-src5/var/runs/r-3b3482ca7f8b/exports/r-3b3482ca7f8b.polished.consulting.tables.json \
        --work   ../Owli-src5/var/runs/r-3b3482ca7f8b/goals/goal-6/cross-comparison-report.json \
        --out    var/rpt7/after/r-3b3482ca7f8b.polished.consulting.md

⛔ 零引擎、零库、零写入原树：
- **不重跑写手**——写手那几节的产物（`consulting-parts/NN-*.md`）只读进来；
- **不读库**——`collect_inputs` 的产物（`*.tables.json`）是上一轮 `polish()` 自己
  落的盘，照读即可，本脚本一次都不连 sqlite；
- **只往 `--out` 写**——附录这几块是程序拼的，改完重跑一次组装就拿得到真稿复验，
  不必也不许覆盖已经交给用户的那一份（那棵树是运行时）。

分节文件按文件名前缀的序号排，节名从文件名取——与 `run.section_paths`
（`{index:02d}-{name}.md`）同一个形状，⛔ 不另立一套命名。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.report.polish.run import (assemble, basis_table,  # noqa: E402
                                   confidence_tables, contrast_reference_table,
                                   lexicon_reference_table, missing_table,
                                   quotes_reference_table, timespan_block)

#: 分片文件（`02-关键发现.shard-1.md`）不是节产物，合并稿已经在 `NN-节名.md` 里了。
_SHARD = ".shard-"


def section_parts(parts_dir: Path) -> list[tuple[str, Path]]:
    picked = sorted(p for p in parts_dir.glob("[0-9][0-9]-*.md") if _SHARD not in p.name)
    return [(p.stem.split("-", 1)[1], p) for p in picked]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts", required=True, help="写手分节产物目录（只读）")
    parser.add_argument("--tables", required=True, help="上一轮 polish 落的 tables.json（只读）")
    parser.add_argument("--work", required=True, help="工作稿（只读），缺失清单从它取")
    parser.add_argument("--out", required=True, help="重组装后的稿子落点（只写这一个）")
    args = parser.parse_args(argv[1:])

    from app.report.render import parse_report

    data = json.loads(Path(args.tables).read_text(encoding="utf-8"))
    work = Path(args.work).read_text(encoding="utf-8")
    parts = section_parts(Path(args.parts))
    if not parts:
        raise SystemExit(f"× {args.parts} 下没有分节产物")
    tables = data.get("tables") or {}
    markdown = assemble(
        parts, data.get("sources") or [], tables=tables,
        subjects=data.get("subjects") or (), counts=data.get("counts") or {},
        # ⛔ 这一串与 `run.polish()` 里那一串逐字同序：附录块少一块或换个顺序，
        # 量出来的就不是生产会出的那份稿。
        appendix_blocks=(
            confidence_tables(tables),
            missing_table(parse_report(work).get("missing") or [],
                          data.get("objectives") or [], chapters=data.get("chapters") or []),
            basis_table(tables),
            lexicon_reference_table(tables),
            quotes_reference_table(tables),
            contrast_reference_table(tables),
            timespan_block(tables),
        ))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    print(json.dumps({"out": str(out), "bytes": len(markdown.encode("utf-8")),
                      "sections": [name for name, _ in parts]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
