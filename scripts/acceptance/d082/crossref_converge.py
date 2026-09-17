"""§D-082 货 1 ③ / 货 2 ④：收 §REISSUE-1 挂账「被断言引用行的交叉分没跟簇结论走」。

调度批甲（09-18）：只收交叉维，**分与理由一律由生产函数算**，不手写公式：
- 口径与 `backfill_report` 收敛轮同源：`_normalize_report` → `engagement_percentiles` →
  `_stored_labels` → `_scored_payloads(freeze_others=False)`（其内 `_scoring_view` →
  `_crossref_verdict` → `score_evidence_partial` → `score_evidence`）。
- 从生产载荷里**只取**交叉维：`score_crossref` 与 rating_notes 的「交叉」一段
  （`RATING_NOTES_PATTERN` 第 5/6 组）与「存在反证」尾注有无；其余四维连分带理由
  保留库里原样（与 `_first_dimension_only` 换第一维的做法对称）。
- 回写前用生产校验 `rating_notes_problem(notes, payload)` 过一遍；
  `score_total`/`grade` 是库的 GENERATED 列，写后再用 `grade_for_total` 逐行核。
- 缺闭集标签的行（`_stored_labels` 判 None，本研究是 6 行补采 X/HN，content_kind 空）：
  **不写**；用生产 `score_evidence_partial`（标签取库里 extra 原值）只核「交叉分是否已对」，
  对不上就计 `unlabeled_mismatch` 并报错退出，不猜口径。

模式：
- `crossref-only`：上述收法。
- `full-round`：照收敛轮原样整批走（货 1 量过：`_stored_labels` 整批 None，一行不写）。

库默认必须在本包 var/ 下；写沙盒库要 `--sandbox-ok --snapshot <已存在的写前快照>`。

用法：
    ../Owli/.venv/bin/python scripts/acceptance/d082/crossref_converge.py <模式> <库> \
        [--sandbox-ok --snapshot var/xxx.db] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.reliability.backfill import (  # noqa: E402
    _crossref_verdict, _normalize_report, _report_claims, _scored_payloads,
    _scoring_view, _stored_labels,
)
from app.reliability.scoring import (  # noqa: E402
    RATING_NOTES_PATTERN, SCORE_FIELDS, engagement_percentiles, grade_for_total,
    rating_notes_problem, score_evidence_partial,
)
from app.store.dao import Store  # noqa: E402

VAR = (ROOT / "var").resolve()
SANDBOX = (ROOT.parent / "Owli-src5/var/src5-backfill.db").resolve()
RID = "r-3b3482ca7f8b"
CONFLICT_WARNING = "存在反证"


def guard(database: Path, sandbox_ok: bool, snapshot: Path | None) -> Path:
    database = database.resolve()
    if database.is_relative_to(VAR):
        return database
    if not (sandbox_ok and database == SANDBOX):
        raise SystemExit(f"拒绝：库不在本包 var/ 下：{database}")
    if snapshot is None or not snapshot.resolve().is_file():
        raise SystemExit("拒绝：写沙盒库必须给出已存在的写前快照 --snapshot")
    return database


def _warnings(tail: str | None) -> list[str]:
    return [w for w in (tail or "").removeprefix(" ⚠️").split("；") if w]


def crossref_only_payload(stored: dict, fresh: dict) -> dict:
    """库里原行 + 生产载荷 → 只换交叉维的回写载荷。"""

    old = RATING_NOTES_PATTERN.fullmatch(str(stored.get("rating_notes") or ""))
    new = RATING_NOTES_PATTERN.fullmatch(str(fresh["rating_notes"]))
    if old is None or new is None:
        raise ValueError(f"{stored['id']}: rating_notes 解析不了")
    notes = str(stored["rating_notes"])
    start, end = old.span(5)[0] - len("交叉"), old.span(6)[1]
    notes = notes[:start] + f"交叉{new.group(5)}:{new.group(6)}" + notes[end:]
    body = notes.split(" ⚠️", 1)[0]
    warnings = [w for w in _warnings(old.group(11)) if w != CONFLICT_WARNING]
    if CONFLICT_WARNING in _warnings(new.group(11)):
        warnings.append(CONFLICT_WARNING)
    notes = body + (f" ⚠️{'；'.join(warnings)[:30]}" if warnings else "")
    payload = {k: v for k, v in stored.items() if k not in {"score_total", "grade"}}
    payload.update(score_crossref=fresh["score_crossref"], rating_notes=notes)
    problem = rating_notes_problem(notes, payload)
    if problem is not None:
        raise AssertionError(f"{stored['id']}: {problem}")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("crossref-only", "full-round"))
    ap.add_argument("database", type=Path)
    ap.add_argument("--sandbox-ok", action="store_true")
    ap.add_argument("--snapshot", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ns = ap.parse_args()
    database = guard(ns.database, ns.sandbox_ok, ns.snapshot)
    store = Store(database)
    report = store.get_report(RID)
    rows = store.list_evidence(RID)
    referenced = {str(e) for c in _report_claims(report) for e in (c.get("evidence_ids") or [])}
    targets = [r for r in rows if str(r["id"]) in referenced]
    # 与 backfill_report 同口径（backfill.py 收敛轮上游那几行）。
    computed_at = str(report.get("completed_at") or max(
        (str(i.get("fetched_at") or "") for i in rows), default=""))
    normalized = _normalize_report(rows, computed_at)
    percentiles = engagement_percentiles(normalized.values())
    stats: Counter = Counter(targets=len(targets))
    changes: list[dict] = []
    payloads: list[dict] = []
    if ns.mode == "full-round":
        resettle = [normalized[str(i["id"])] for i in targets]
        labels = _stored_labels(resettle)
        if labels is None:
            print(json.dumps({"mode": ns.mode, "written": 0,
                              "note": "_stored_labels 整批 None，收敛轮一行不写"}, ensure_ascii=False))
            return 0
        payloads = _scored_payloads([(i, l, False) for i, l in zip(resettle, labels)],
                                    "claude", percentiles=percentiles, freeze_others=False)
    else:
        for stored in targets:
            view_item = normalized[str(stored["id"])]
            verdict = _crossref_verdict(stored.get("extra") or {})
            if verdict is None:
                stats["no_verdict"] += 1
                continue
            labels = _stored_labels([view_item])
            if labels is None:
                extra = stored.get("extra") or {}
                label = {k: extra.get(k) for k in ("authority_kind", "content_kind", "interest_relation")}
                fresh = score_evidence_partial(
                    _scoring_view(view_item, label,
                                  engagement_percentile=percentiles.get(str(stored["id"]))),
                    cluster_stats={"verdict": verdict})
                key = "unlabeled_consistent" if fresh["score_crossref"] == stored["score_crossref"] \
                    else "unlabeled_mismatch"
                stats[key] += 1
                continue
            fresh = _scored_payloads([(view_item, labels[0], False)], "claude",
                                     percentiles=percentiles, freeze_others=False)[0]
            if fresh["score_crossref"] == stored["score_crossref"]:
                stats["labeled_consistent"] += 1
                continue
            payload = crossref_only_payload(dict(stored), fresh)
            payloads.append(payload)
            changes.append({"id": stored["id"], "citation_no": stored.get("citation_no"),
                            "verdict": verdict, "crossref": [stored["score_crossref"],
                                                             payload["score_crossref"]],
                            "grade_before": stored.get("grade")})
        if stats["unlabeled_mismatch"]:
            print(json.dumps({"mode": ns.mode, "error": "缺标签行交叉分对不上，口径待拍",
                              **stats}, ensure_ascii=False))
            return 1
    stats["written"] = 0 if ns.dry_run else len(payloads)
    if payloads and not ns.dry_run:
        store.upsert_evidence_batch(payloads)
        after = {str(r["id"]): r for r in store.list_evidence(RID)}
        for change in changes:
            row = after[change["id"]]
            total = sum(row[f] for f in SCORE_FIELDS)
            assert row["score_total"] == total and row["grade"] == grade_for_total(total), change
            change["grade_after"] = row["grade"]
    print(json.dumps({"mode": ns.mode, "database": str(database), "dry_run": ns.dry_run,
                      **stats, "changes": changes}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
