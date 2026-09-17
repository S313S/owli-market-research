"""§D-082 尺子：同一研究两份库的派生数据逐项比（只读）。

比什么：evidence 五维分 / score_total / grade / rating_notes / citation_no / id，
extra 里的簇回填键；reports.extra.claims 的 verdict / k / clusters / firsthand；
另给等级分布、「score_crossref 与簇结论对得上」的行数、原声等级闸（A/B/C）进出。

用法：
    ../Owli/.venv/bin/python scripts/acceptance/d082/diff_derived.py <库A> <库B> [--show 5]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter

RID = "r-3b3482ca7f8b"
SCORE = ("score_authority", "score_freshness", "score_crossref",
         "score_completeness", "score_independence")
CROSSREF_SCORES = {"PASS": 2, "WEAK": 1, "SINGLE": 0, "CONFLICT": 0}
XKEYS = ("claim_ids", "origin_key", "crossref_cluster", "crossref_n_clusters",
         "crossref_peers", "crossref_conflicts", "crossref_verdict", "crossref_secondary")
QUOTE_GRADES = {"A", "B", "C"}


def _load(db: str):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = {r["permalink"]: dict(r) for r in con.execute(
        "SELECT * FROM evidence WHERE report_id=?", (RID,))}
    for r in rows.values():
        r["extra"] = json.loads(r["extra"] or "{}")
    extra = json.loads(con.execute("SELECT extra FROM reports WHERE id=?", (RID,)).fetchone()[0])
    con.close()
    return rows, {c["id"]: c for c in extra.get("claims", [])}


def _referenced(claims: dict) -> set[str]:
    return {str(e) for c in claims.values() for e in (c.get("evidence_ids") or [])}


def _consistent(rows: dict, ids: set[str]) -> tuple[int, int]:
    hit = [r for r in rows.values() if r["id"] in ids]
    ok = sum(1 for r in hit if r["extra"].get("crossref_verdict") in CROSSREF_SCORES
             and r["score_crossref"] == CROSSREF_SCORES[r["extra"]["crossref_verdict"]])
    return ok, len(hit)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--show", type=int, default=5)
    ns = ap.parse_args()
    ra, ca = _load(ns.a)
    rb, cb = _load(ns.b)
    assert set(ra) == set(rb), "两侧 permalink 集合不同，尺子取错了库"
    kind_of = {p: f"{rb[p]['kind']}/{rb[p]['source_type']}" for p in rb}
    out: dict = {}
    for col in ("id", "citation_no", *SCORE, "score_total", "grade", "rating_notes", "rated_by"):
        bad = [p for p in ra if ra[p][col] != rb[p][col]]
        if bad:
            out[col] = {"rows": len(bad), "by_kind": dict(Counter(kind_of[p] for p in bad)),
                        "samples": Counter((str(ra[p][col])[:60], str(rb[p][col])[:60])
                                           for p in bad).most_common(ns.show)}
    for key in XKEYS:
        bad = [p for p in ra if ra[p]["extra"].get(key) != rb[p]["extra"].get(key)]
        if bad:
            out[f"extra.{key}"] = {"rows": len(bad), "by_kind": dict(Counter(kind_of[p] for p in bad))}
    other = Counter()
    for p in ra:
        for key in set(ra[p]["extra"]) | set(rb[p]["extra"]):
            if key not in XKEYS and ra[p]["extra"].get(key) != rb[p]["extra"].get(key):
                other[key] += 1
    out["extra.其它键不等"] = dict(other)
    for field in ("verdict", "k", "clusters", "firsthand", "firsthand_source", "evidence_ids"):
        bad = [c for c in ca if ca[c].get(field) != cb.get(c, {}).get(field)]
        if bad:
            item = {"claims": len(bad)}
            if field == "verdict":
                item["transitions"] = dict(Counter(f"{ca[c].get('verdict')}→{cb[c].get('verdict')}"
                                                   for c in bad))
            out[f"claims.{field}"] = item
    out["claims.verdict 分布"] = {"A": dict(Counter(c.get("verdict") for c in ca.values())),
                                "B": dict(Counter(c.get("verdict") for c in cb.values()))}
    out["grade 分布"] = {"A": dict(Counter(r["grade"] for r in ra.values())),
                       "B": dict(Counter(r["grade"] for r in rb.values()))}
    cited = [p for p in rb if rb[p]["citation_no"] is not None]
    out["被引行 grade 分布"] = {"A": dict(Counter(ra[p]["grade"] for p in cited)),
                            "B": dict(Counter(rb[p]["grade"] for p in cited))}
    gate = [p for p in cited if (ra[p]["grade"] in QUOTE_GRADES) != (rb[p]["grade"] in QUOTE_GRADES)]
    out["原声等级闸进出（被引行）"] = [(rb[p]["citation_no"], ra[p]["grade"], rb[p]["grade"],
                                  kind_of[p]) for p in gate]
    ids_a, ids_b = _referenced(ca), _referenced(cb)
    out["被断言引用行 score_crossref 与簇结论对得上"] = {"A": _consistent(ra, ids_a),
                                                "B": _consistent(rb, ids_b)}
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
