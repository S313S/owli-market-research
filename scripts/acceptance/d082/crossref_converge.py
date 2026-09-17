"""§D-082 货 1 ③：在**副本**上量 §REISSUE-1 挂账「147 行交叉分没跟簇结论走」的两种收法。

- `crossref-only`：被断言引用、带合法簇结论的行，只把交叉维改成
  `CROSSREF_SCORES[extra.crossref_verdict]`，rating_notes 只换「交叉」一段
  （理由取 `CROSSREF_REASONS`），其余四维连分带理由原样；CONFLICT 的「存在反证」
  尾注跟着结论加/去。grade/score_total 是生成列，自动跟。
- `full-round`：照 `backfill.py` 收敛轮（`if rated and clustered_ids` 那段）原样走
  `_scored_payloads(freeze_others=False)`——即 §REISSUE-1 回填若 rated>0 本会发生的事，
  五维全部按库存标签的本地规则重算。

零引擎（不构造适配器）。⛔ 库必须在本包 var/ 下。

用法：
    ../Owli/.venv/bin/python scripts/acceptance/d082/crossref_converge.py <模式> <副本库>
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
    _crossref_verdict, _normalize_report, _report_claims, _scored_payloads, _stored_labels,
)
from app.reliability.scoring import (  # noqa: E402
    CROSSREF_REASONS, CROSSREF_SCORES, RATING_NOTES_PATTERN, SCORE_FIELDS,
    engagement_percentiles, grade_for_total, rating_notes_problem,
)
from app.store.dao import Store  # noqa: E402

VAR = (ROOT / "var").resolve()
RID = "r-3b3482ca7f8b"
CONFLICT_WARNING = "存在反证"


def _splice(item: dict, verdict: str) -> dict | None:
    matched = RATING_NOTES_PATTERN.fullmatch(str(item.get("rating_notes") or ""))
    if matched is None:
        return None
    score = CROSSREF_SCORES[verdict]
    head = str(item["rating_notes"]).split(" · ", 1)[0]
    tail = (matched.group(11) or "").removeprefix(" ⚠️")
    warnings = [w for w in tail.split("；") if w and w != CONFLICT_WARNING]
    if verdict == "CONFLICT":
        warnings.append(CONFLICT_WARNING)
    notes = (f"{head} · 时效{matched.group(3)}:{matched.group(4)} · "
             f"交叉{score}:{CROSSREF_REASONS[verdict]} · 完整{matched.group(7)}:{matched.group(8)} · "
             f"无关{matched.group(9)}:{matched.group(10)}")
    if warnings:
        notes += f" ⚠️{'；'.join(warnings)[:30]}"
    payload = {k: v for k, v in item.items() if k not in {"score_total", "grade"}}
    payload.update(score_crossref=score, rating_notes=notes)
    problem = rating_notes_problem(notes, payload)
    if problem is not None:
        raise AssertionError(f"{item['id']}: {problem}")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("crossref-only", "full-round"))
    ap.add_argument("database", type=Path)
    ns = ap.parse_args()
    database = ns.database.resolve()
    if not database.is_relative_to(VAR):
        raise SystemExit(f"拒绝：库不在本包 var/ 下：{database}")
    store = Store(database)
    report = store.get_report(RID)
    rows = store.list_evidence(RID)
    referenced = {str(e) for c in _report_claims(report) for e in (c.get("evidence_ids") or [])}
    targets = [r for r in rows if str(r["id"]) in referenced]
    stats: Counter = Counter(targets=len(targets))
    if ns.mode == "crossref-only":
        payloads = []
        for item in targets:
            verdict = _crossref_verdict(item.get("extra") or {})
            if verdict is None:
                stats["no_verdict"] += 1
                continue
            if item.get("score_crossref") == CROSSREF_SCORES[verdict]:
                stats["already_consistent"] += 1
                continue
            if any(item.get(f) is None for f in SCORE_FIELDS if f != "score_crossref"):
                stats["other_dims_null"] += 1
            payload = _splice(dict(item), verdict)
            if payload is None:
                stats["notes_unparsable"] += 1
                continue
            payloads.append(payload)
    else:
        computed_at = str(report.get("completed_at") or max(
            (str(i.get("fetched_at") or "") for i in rows), default=""))
        normalized = _normalize_report(rows, computed_at)
        percentiles = engagement_percentiles(normalized.values())
        resettle = [normalized[str(i["id"])] for i in targets if str(i["id"]) in normalized]
        labels = _stored_labels(resettle)
        if labels is None:
            print(json.dumps({"mode": ns.mode, "error": "_stored_labels 返回 None：收敛轮整段不写"},
                             ensure_ascii=False))
            return 1
        payloads = _scored_payloads([(i, l, False) for i, l in zip(resettle, labels)],
                                    "claude", percentiles=percentiles, freeze_others=False)
    stats["written"] = len(payloads)
    if payloads:
        store.upsert_evidence_batch(payloads)
    print(json.dumps({"mode": ns.mode, "database": str(database), **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
