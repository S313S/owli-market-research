"""§D-073：评级章打过分的 UGC 行，收尾回填必须重评成「代表性」尺子。

病根是 targets 入选的布尔结构——`restale` 被 `and` 关在 `not _already_agent_rated`
内侧，评级章逐条打过的行五维是齐的，于是代表性尺子在真跑里一条都落不到库上
（09-15 那轮 attempted=240 全是没被 agent 评过的 baseline 行，755 条 restale 一条没进）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

_STALE_NOTES = (
    "权威0:作者不可核验 · 时效2:时间窗内 · 交叉0:该断言仅一簇 · "
    "完整2:字段齐全 · 无关2:无可见利益关系"
)
_FRESH_NOTES = (
    "代表性2:P100 · 时效2:时间窗内 · 交叉0:该断言仅一簇 · "
    "完整2:字段齐全 · 无关2:无可见利益关系"
)
_UGC_EXTRA = {
    "authority_kind": "anonymous_or_unverifiable",
    "content_kind": "user_opinion",
    "interest_relation": "arms_length",
    "crossref_verdict": "SINGLE",
    "crossref_n_clusters": 1,
    "claim_ids": ["c-1"],
}


def _rated(report_id: str, suffix: str, *, platform: str, liked: int,
           notes: str, first: int = 0):
    """一条「评级章已经逐条评过、五维齐全」的 UGC 行。"""

    from tests.test_m4fork_followup import _evidence

    return _evidence(
        report_id, suffix, permalink=f"https://{platform}.example/{suffix}",
        platform=platform, raw_metrics={"liked_count": liked},
        score_authority=first, score_freshness=2, score_crossref=0,
        score_completeness=2, score_independence=2,
        rating_notes=notes, rated_by="agent:reliability-auditor@claude",
        extra=dict(_UGC_EXTRA),
    )


def _store(tmp_path: Path):
    """一池 21 条小红书（20 条旧写法 + 1 条已按代表性评过）+ 1 条独苗微博。

    微博那条自己一个池，池不足 20 条出不了分位——它是「无分位不得入选」的靶子。
    """

    from tests.test_m4fork_followup import _database

    _, store = _database(tmp_path)
    store.create_report(id="r-d073", title="代表性", research_question="重评",
                        created_at="2026-09-16T00:00:00Z")
    rows = [
        _rated("r-d073", f"s{index:03d}", platform="xhs",
               liked=index * 10, notes=_STALE_NOTES)
        for index in range(20)
    ]
    rows.append(_rated("r-d073", "fresh", platform="xhs",
                       liked=9999, notes=_FRESH_NOTES, first=2))
    rows.append(_rated("r-d073", "lonely", platform="weibo",
                       liked=7, notes=_STALE_NOTES))
    store.upsert_evidence_batch(rows)
    return store


def _run(store, tmp_path: Path):
    from app.reliability.backfill import backfill_report
    from tests.test_m4fork_followup import BackfillEngine

    engine = BackfillEngine()
    before = {row["id"]: dict(row) for row in store.list_evidence("r-d073")}
    result = asyncio.run(backfill_report(
        store, "r-d073", adapter=engine, runs_root=tmp_path / "runs",
    ))
    after = {row["id"]: dict(row) for row in store.list_evidence("r-d073")}
    return engine, result, before, after


def test_评级章打过分的UGC行必须进重评(tmp_path: Path) -> None:
    """靶子：有分位、UGC、理由还是「权威」写法——哪怕五维齐全也要重评。"""

    engine, result, _, after = _run(_store(tmp_path), tmp_path)

    stale_ids = [f"ev-s{index:03d}" for index in range(20)]
    assert result.attempted == 20, (
        f"20 条旧写法的行该全进 targets，实到 {result.attempted}"
    )
    assert result.failed == 0
    assert engine.calls == 0, "库里有闭集标签，本地重算即可，不该过引擎"
    for identity in stale_ids:
        assert after[identity]["rating_notes"].startswith("代表性"), (
            f"{identity} 还是旧尺子：{after[identity]['rating_notes']}"
        )
        # 换尺子不冒充本轮引擎判定：来源保持评级章原样（§RATE-4 口径）。
        assert after[identity]["rated_by"] == "agent:reliability-auditor@claude"
        assert after[identity]["extra"]["content_kind"] == "user_opinion", "标签没动"


def test_已按代表性评过的行不重复重评(tmp_path: Path) -> None:
    """防抖动：换过尺子的行再跑一轮，逐字段不动。"""

    _, _, before, after = _run(_store(tmp_path), tmp_path)

    changed = {
        identity for identity, row in after.items() if row != before[identity]
    }
    # 这一轮必须真的动过东西，否则「没被重评」是因为整轮空转，断言就是假绿。
    assert "ev-s000" in changed, "旧写法的行没被重评，这条防抖动断言量不出东西"
    assert "ev-fresh" not in changed, "已按代表性评过的行被重新算了一遍"
    assert after["ev-fresh"] == before["ev-fresh"]


def test_没有分位的行不进重评(tmp_path: Path) -> None:
    """池不足 20 条就没有分位，硬评出来的「代表性」是假的——整行不动。"""

    _, _, before, after = _run(_store(tmp_path), tmp_path)

    assert after["ev-lonely"] == before["ev-lonely"], "独苗池的行不该被重评"
    assert after["ev-lonely"]["rating_notes"] == _STALE_NOTES
