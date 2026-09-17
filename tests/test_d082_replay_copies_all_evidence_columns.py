"""§D-082 守卫：replay 复制研究时，evidence 每一列都要跟着过去（id / report_id 除外）。

09-17 事故：`import_research._EVIDENCE_COLUMNS` 是 §CMT-1（schema v10）之前的手写清单，
`kind`、`parent_permalink` 两列没跟上 ⇒ 复制后 563 条评论全落成 dao 默认的 `kind='post'`、
父链为空，正式稿平台表写成「其中评论 0」、态度表把 51 条评论算成「在说研究主体」。

这条用例不按列名逐个点——那等于再抄一份会过期的清单。它按 `PRAGMA table_info(evidence)`
逐列比源行与新行；并反过来要求夹具那条评论行**每一列都不是空、不是表默认值**，
将来谁给 evidence 加列却没进夹具，这里先红，而不是静默地「默认值等于默认值」绿过去。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from plan_factory import make_plan_dict

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "app" / "store" / "schema.sql"
SOURCE_ID = "r-01JXOWLI0000000000D082"
POST = "https://www.xiaohongshu.com/explore/d082post"
COMMENT = f"{POST}?owli_comment=d082c1"
IDENTITY = {"id", "report_id"}


def _norm_context(computed_at: str) -> dict:
    return {"scope": "batch", "platform": "xhs", "metric": "liked_count", "n": 20,
            "formula": "count(x<v)/(n-1)", "stats": {"min": 0, "max": 9},
            "computed_at": computed_at}


def _row(identity: str, permalink: str, **overrides) -> dict:
    fetched = "2026-09-15T06:00:00+00:00"
    row = {
        "id": identity, "report_id": SOURCE_ID, "goal_id": "goal-1",
        "agent_name": "data-collection-1", "engine": "codex", "platform": "xhs",
        "source_type": "post", "platform_item_id": f"item-{identity}",
        "permalink": permalink, "title": "豆包真的好用吗", "content_excerpt": "正文摘录",
        "author_name": "作者甲", "author_meta": {"verified": True, "followers": 12},
        "source_keyword": "豆包", "fetch_method": "third_party_api",
        "published_at": "2026-09-10T00:00:00+00:00", "fetched_at": fetched,
        "raw_metrics": {"liked_count": 9}, "normalized_score": 0.5,
        "norm_method": "percentile_in_batch", "norm_context": _norm_context(fetched),
        "score_authority": 1, "score_freshness": 2, "score_crossref": 0,
        "score_completeness": 1, "score_independence": 2,
        "rating_notes": "代表性1:P50 · 时效2:近90天内 · 交叉0:该断言仅一簇 · 完整1:内容较短 · 无关2:无利益关系",
        "rated_by": "agent:reliability-audit-1@claude", "citation_no": 3,
        "extra": {"content_kind": "user_opinion", "claim_ids": ["c-010101"]},
        "kind": "post", "parent_permalink": None,
    }
    row.update(overrides)
    return row


def _seed(database: Path, runs: Path) -> None:
    from app.adapters.selfcheck import initialize_and_check
    from app.store.dao import Store

    initialize_and_check(database, SCHEMA_PATH)
    store = Store(database)
    snapshot = make_plan_dict()
    store.create_report(
        id=SOURCE_ID, title=snapshot["title"],
        research_question=snapshot["research_question"], use_case=snapshot["use_case"],
        status="completed", created_at="2026-09-15T00:00:00+00:00", plan_snapshot=snapshot,
    )
    store.add_evidence_batch([
        _row("ev-d082-post", POST),
        _row("ev-d082-comment", COMMENT, source_type="comment", kind="comment",
             parent_permalink=POST, title="评论 · 豆包真的好用吗", content_excerpt="读者说挺好",
             author_name="读者乙", raw_metrics={"likes": 7}, citation_no=4,
             rating_notes="代表性1:评论·P50 · 时效2:近90天内 · 交叉0:该断言仅一簇 · 完整1:内容较短 · 无关2:无利益关系",
             extra={"content_kind": "user_opinion", "comment_of": POST,
                    "parent_origin_key": "xiaohongshu.com/explore/d082post"}),
    ])
    (runs / SOURCE_ID / "goals" / "goal-1").mkdir(parents=True, exist_ok=True)


def _columns(connection: sqlite3.Connection) -> list[tuple[str, str | None]]:
    return [(row[1], row[4]) for row in connection.execute("PRAGMA table_info(evidence)")]


def _rows(connection: sqlite3.Connection, report_id: str) -> dict[str, sqlite3.Row]:
    connection.row_factory = sqlite3.Row
    return {row["permalink"]: row for row in connection.execute(
        "SELECT * FROM evidence WHERE report_id = ?", (report_id,))}


def test_夹具那条评论每一列都不是空也不是默认值(tmp_path: Path) -> None:
    database, runs = tmp_path / "owli.db", tmp_path / "runs"
    _seed(database, runs)
    connection = sqlite3.connect(database)
    comment = _rows(connection, SOURCE_ID)[COMMENT]
    lazy = []
    for name, default in _columns(connection):
        if name in IDENTITY:
            continue
        value = comment[name]
        literal = None if default is None else default.strip("'")
        if value is None or (literal is not None and str(value) == literal):
            lazy.append(name)
    connection.close()
    assert not lazy, (
        f"evidence 这些列在夹具评论行里是空或默认值，逐列比对对它们不起作用：{lazy}——"
        "新加的列请给夹具填一个非默认值")


def test_replay复制后evidence逐列与源行相等(tmp_path: Path) -> None:
    from app.replay.import_research import import_research
    from app.store.dao import Store

    database, runs = tmp_path / "owli.db", tmp_path / "runs"
    _seed(database, runs)
    imported = import_research(
        store=Store(database), source_database=database, source_runs=runs,
        source_research_id=SOURCE_ID, runs_root=runs,
        now_iso="2026-09-18T00:00:00+00:00",
    )

    connection = sqlite3.connect(database)
    columns = [name for name, _ in _columns(connection) if name not in IDENTITY]
    source = _rows(connection, SOURCE_ID)
    copied = _rows(connection, imported.research_id)
    connection.close()
    assert set(copied) == set(source) == {POST, COMMENT}
    mismatches = {
        f"{'comment' if permalink == COMMENT else 'post'}.{name}": (source[permalink][name],
                                                                   copied[permalink][name])
        for permalink in source for name in columns
        if source[permalink][name] != copied[permalink][name]
    }
    assert not mismatches, "replay 复制丢列（源值, 新值）：" + json.dumps(
        mismatches, ensure_ascii=False)
    assert {copied[p]["id"] for p in copied}.isdisjoint({source[p]["id"] for p in source})
