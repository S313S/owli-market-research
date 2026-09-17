"""§D-082：零引擎重算正式稿确定性表（tables.json），与出稿同一入口。

沿用 `scripts/acceptance/rpt1/rpt1_polish.py` 的 `ReadOnlyStore` 与工作稿路径拼法，
调 `app.report.polish.tables.collect_inputs`——与 `polish()` 第一步逐字同源，
序列化口径也同（`json.dumps(data, ensure_ascii=False, indent=2)`）。
只读库、只读工作稿，只写 <输出>（必须在本包 var/ 下）。

用法：
    ../Owli/.venv/bin/python scripts/acceptance/d082/tables_probe.py <库> <输出.json> \
        [--runs ../Owli-src5/var/runs] [--id r-3b3482ca7f8b]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.report.polish.tables import collect_inputs  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "rpt1_polish", ROOT / "scripts/acceptance/rpt1/rpt1_polish.py")
_rpt1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rpt1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("database", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--runs", type=Path, default=ROOT.parent / "Owli-src5/var/runs")
    ap.add_argument("--id", default="r-3b3482ca7f8b")
    ns = ap.parse_args()
    output = ns.output.resolve()
    if not output.is_relative_to((ROOT / "var").resolve()):
        raise SystemExit(f"拒绝：输出不在本包 var/ 下：{output}")
    store = _rpt1.ReadOnlyStore(ns.database.resolve())
    report = store.get_report(ns.id)
    if report is None:
        raise SystemExit(f"× 库里没有 {ns.id}")
    draft = _rpt1.work_draft_path(ns.runs.resolve(), ns.id, report["report_path"])
    data = collect_inputs(store, ns.id, draft.read_text("utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"database": str(ns.database), "draft": str(draft),
                      "output": str(output), "bytes": output.stat().st_size},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
