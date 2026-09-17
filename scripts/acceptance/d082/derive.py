"""§D-082：在**副本**上零引擎重跑派生分，量「修对 kind 后变不变」。

两种模式都直接调 `app.reliability.backfill.backfill_report`（与脚本
`scripts/backfill-evidence-ratings.py` 同一个函数），适配器换成 `RefuseAdapter`：
任何一次引擎调用都**就地判失败并计数**，保证零引擎；计数非 0 就说明这条路
真跑起来要付钱（读数原样报）。

- `rescore`：`rescore_only=True`（§RATE-4 货 2 口径：只重算第一维，其余四维冻结）。
- `finish`：完整 `backfill_report`（一手性审计已结算的跳过、未结算的被拒；
  簇回填；五维补评；收敛轮；角标同步因 runs_root 指向空目录而跳过）。

⛔ runs_root 一律在本包 var/scratch-runs/ 下（不碰沙盒 runs）；库默认必须在本包 var/ 下，
货 2 写沙盒库要 `--sandbox-ok --snapshot <已存在的写前快照>`。

用法：
    ../Owli/.venv/bin/python scripts/acceptance/d082/derive.py rescore <副本库>
    ../Owli/.venv/bin/python scripts/acceptance/d082/derive.py finish <副本库>
    [--strip-crossref]  # finish 前先把 147 行上一轮簇回填持久化的键剥掉
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.reliability.backfill import backfill_report  # noqa: E402
from app.store.dao import Store  # noqa: E402

VAR = (ROOT / "var").resolve()
RESEARCH_ID = "r-3b3482ca7f8b"
#: 簇回填（`crossref.build_claim_clusters`）往 evidence.extra 写的键。
CROSSREF_KEYS = (
    "origin_key", "crossref_cluster", "crossref_n_clusters", "crossref_peers",
    "crossref_conflicts", "crossref_verdict", "crossref_secondary",
)


class _Conclusion:
    status = "failed"
    unmet: list = []


class _Refused:
    succeeded = False
    engine_error = "d082 RefuseAdapter: 货 1 零引擎"
    conclusion = _Conclusion()


class RefuseAdapter:
    def __init__(self) -> None:
        self.calls: Counter = Counter()

    async def run(self, task: Any, ctx: Any, on_event: Any = None) -> Any:
        # 审计与补评两条路 agent_kind 同为 reliability_audit，按产物目录分开计。
        parts = Path(str(getattr(task, "output_path", ""))).parts
        folder = next((p for p in ("firsthand-audit", "reliability-backfill", "ugc-coding")
                       if p in parts), str(getattr(task, "agent_kind", "?")))
        self.calls[folder] += 1
        return _Refused()


def _strip_crossref(database: Path) -> int:
    con = sqlite3.connect(str(database))
    try:
        rows = con.execute(
            "SELECT id, extra FROM evidence WHERE report_id=?", (RESEARCH_ID,)
        ).fetchall()
        changed = 0
        with con:
            for identity, raw in rows:
                extra = json.loads(raw or "{}")
                if not any(key in extra for key in CROSSREF_KEYS):
                    continue
                for key in CROSSREF_KEYS:
                    extra.pop(key, None)
                con.execute("UPDATE evidence SET extra=? WHERE id=?",
                            (json.dumps(extra, ensure_ascii=False), identity))
                changed += 1
        return changed
    finally:
        con.close()


async def _run(ns: argparse.Namespace) -> dict[str, Any]:
    database = ns.database.resolve()
    if not database.is_relative_to(VAR):
        # 货 2：写沙盒库只认这一个路径，且必须给出已存在的写前快照。
        sandbox = (ROOT.parent / "Owli-src5/var/src5-backfill.db").resolve()
        if not (ns.sandbox_ok and database == sandbox):
            raise SystemExit(f"拒绝：库不在本包 var/ 下：{database}")
        if ns.snapshot is None or not ns.snapshot.resolve().is_file():
            raise SystemExit("拒绝：写沙盒库必须给出已存在的写前快照 --snapshot")
    runs_root = (VAR / "scratch-runs" / database.stem).resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    stripped = _strip_crossref(database) if ns.strip_crossref else 0
    adapter = RefuseAdapter()
    store = Store(database)
    result = await backfill_report(
        store, RESEARCH_ID, adapter=adapter, runs_root=runs_root,
        rescore_only=(ns.mode == "rescore"),
    )
    return {"mode": ns.mode, "database": str(database), "stripped_rows": stripped,
            "engine_calls_refused": dict(adapter.calls), "result": asdict(result)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("rescore", "finish"))
    ap.add_argument("database", type=Path)
    ap.add_argument("--strip-crossref", action="store_true")
    ap.add_argument("--sandbox-ok", action="store_true")
    ap.add_argument("--snapshot", type=Path)
    ns = ap.parse_args()
    payload = asyncio.run(_run(ns))
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
