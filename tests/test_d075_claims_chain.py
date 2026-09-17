"""§D-075：同一条主张内逐字节重复的 permalink 不再把整批主张退回。

真机 r-20271e8a5028：1380 条主张里**只有 1 条**在自己的 evidence 列表里把同一条
小红书评论链接写了两遍（第 0 条与第 2 条逐字节相同），`prepare_claim_registration`
判它违规后抛错退回整批，`set_report_claims` 一次都没被调用，`reports.extra` 里连
`claims` 键都不存在，正式稿 `counts.claims=0`、交叉验证表整张空。

口径（调度 2026-09-17 拍）：这一处**只治「同一条主张内的逐字节重复」**——去重保留
第一条 + 逐条记账，⛔ 不静默去重（静默去重等于把证据质量问题藏起来），
⛔ 不放宽别的校验（结构违规照旧整批退回）。

每条用例在 base `9bbe8fa` 上被判红的**第一处断言**都落在病象本身
（`ClaimsRegistrationError` / `reports.extra` 没有 `claims` 键），
不是落在「新出参还不存在」上——记账通道的断言一律排在行为断言之后。
`test_真正不同的链接一条都不许被并掉` 是防「改过头」的哨兵，两侧都绿。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.reliability.claims import (
    ClaimsRegistrationError,
    prepare_claim_registration,
    register_claims,
)

from tests.test_c1_claims import add_evidence, make_store, raw_claim, ref


#: 真机那条重复的形状：小红书同帖同评论，带一次性 xsec_token，两条逐字节相同。
XHS_COMMENT = (
    "https://www.xiaohongshu.com/explore/6a499e1b00000000070217d7"
    "?xsec_token=YBBjaEurSkMj0Wh9e-1UdUXgnuCaIE1nxd2IfsrZ413Tg%3D"
    "&xsec_source=pc_feed&owli_comment=6a4e62b3000000002203e624"
)
XHS_OTHER_COMMENT = (
    "https://www.xiaohongshu.com/explore/6a499e1b00000000070217d7"
    "?xsec_token=YBBjaEurSkMj0Wh9e-1UdUXgnuCaIE1nxd2IfsrZ413Tg%3D"
    "&xsec_source=pc_feed&owli_comment=6a4e0b26000000002a033316"
)

#: 真机 claims[732] 的形状：evidence[0] 与 evidence[2] 逐字节相同，中间夹一条别的。
REAL_SHAPE = [
    ref(XHS_COMMENT, firsthand=True),
    ref(XHS_OTHER_COMMENT, firsthand=True),
    ref(XHS_COMMENT, firsthand=True),
]


def _prepare_store(tmp_path: Path):
    store = make_store(tmp_path)
    add_evidence(
        store, "r-c1", "ev-dup", platform="xhs",
        permalink=XHS_COMMENT, author="甲",
    )
    add_evidence(
        store, "r-c1", "ev-other", platform="xhs",
        permalink=XHS_OTHER_COMMENT, author="乙",
    )
    return store


def test_一条重复不再连坐整批_其余主张照常登记(tmp_path: Path) -> None:
    """条 ②①：真机 1/1380 端掉 1380 的那件事。

    base 判红处：`register_claims` 抛 `ClaimsRegistrationError`
    （offenders = `claims[1].evidence[2].permalink 在断言内重复`）。
    """

    store = _prepare_store(tmp_path)
    registered = register_claims(
        store,
        "r-c1",
        [
            raw_claim("c-01", [ref(XHS_OTHER_COMMENT, firsthand=True)], text="旁证断言"),
            raw_claim("c-02", REAL_SHAPE, text="真机那条重复"),
        ],
        source="chapter",
    )

    # 整批都进来了，没有一条被那处重复连坐。
    assert [claim["id"] for claim in registered] == ["c-01", "c-02"]
    stored = store.get_report("r-c1")["extra"]["claims"]
    assert [claim["id"] for claim in stored] == ["c-01", "c-02"]
    # 去重保留第一条，同一条 evidence 不在 evidence_ids 里出现两遍。
    assert stored[1]["evidence_ids"] == ["ev-dup", "ev-other"]
    # 双向可达也跟着建起来了，且 claim_ids 不重复追加。
    by_id = {row["id"]: row for row in store.list_evidence("r-c1")}
    assert by_id["ev-dup"]["extra"]["claim_ids"] == ["c-02"]
    assert by_id["ev-other"]["extra"]["claim_ids"] == ["c-01", "c-02"]


def test_去重必须留痕_去了几条哪条主张哪个链接都查得到(tmp_path: Path) -> None:
    """条 ②①：⛔ 不许静默去重——静默去重等于把证据质量问题藏起来。

    base 判红处：第一处断言（`register_claims` 不抛错）就红，
    抛的是 `ClaimsRegistrationError`；记账断言排在它后面。
    """

    store = _prepare_store(tmp_path)
    claims = [raw_claim("c-02", REAL_SHAPE, text="真机那条重复")]

    # 先验行为：base 在这一行就红（抛错退回整批）。
    assert [c["id"] for c in register_claims(
        store, "r-c1", claims, source="chapter",
    )] == ["c-02"]

    # 再验记账通道。
    deduped: list[dict] = []
    register_claims(store, "r-c1", claims, source="chapter", deduped=deduped)
    assert deduped == [{
        "claim_id": "c-02",
        "location": "claims[0].evidence[2]",
        "permalink": XHS_COMMENT,
    }]


def test_真正不同的链接一条都不许被并掉(tmp_path: Path) -> None:
    """条 ②②：防「改过头」的哨兵，去重只认逐字节重复。两侧都绿。"""

    store = _prepare_store(tmp_path)
    registered = register_claims(
        store,
        "r-c1",
        [raw_claim("c-01", [
            ref(XHS_COMMENT, firsthand=True),
            ref(XHS_OTHER_COMMENT, firsthand=True),
        ])],
        source="chapter",
    )
    assert registered[0]["evidence_ids"] == ["ev-dup", "ev-other"]


def test_无重复时落库逐字节不变_且结构违规照旧整批退回(tmp_path: Path) -> None:
    """条 ③ 回归锁：⛔ 不许顺手放宽别的校验，也不许改无重复时的读数。两侧都绿。"""

    store = _prepare_store(tmp_path)
    claims = [raw_claim("c-01", [
        ref(XHS_COMMENT, firsthand=True),
        ref(XHS_OTHER_COMMENT, stance="contradicts"),
    ])]

    def raw_extra() -> str:
        with sqlite3.connect(tmp_path / "r-c1.db") as connection:
            return connection.execute(
                "SELECT extra FROM reports WHERE id = ?", ("r-c1",)
            ).fetchone()[0]

    register_claims(store, "r-c1", claims, source="chapter")
    first = raw_extra()
    register_claims(store, "r-c1", claims, source="chapter")
    assert raw_extra() == first

    # 结构违规照旧整批退回：同一批里既有重复又有违规时，违规那处不许被去重掩盖。
    with pytest.raises(ClaimsRegistrationError) as caught:
        prepare_claim_registration(
            store.list_evidence("r-c1"),
            [raw_claim("c-02", [
                ref(XHS_COMMENT, stance="maybe"),
                ref(XHS_COMMENT),
            ])],
            source="chapter",
        )
    assert any("stance 只能是" in item for item in caught.value.offenders)
    extra = store.get_report("r-c1")["extra"]
    assert [claim["id"] for claim in extra["claims"]] == ["c-01"]


def test_runtime_章成稿后带重复链接的主张仍真写进库(
    tmp_path: Path, monkeypatch,
) -> None:
    """条 ②：走完整收尾链路，判据落在库与事件上，不看日志。

    base 判红处：`reports.extra` 里**连 `claims` 键都不存在**（`KeyError: 'claims'`），
    与真机 r-20271e8a5028 的读数逐字同形。
    """

    from tests.test_m3h_finalize import _finalize, _plan

    path = "goals/goal-3/report.json"
    plan = _plan(report_format="json", path=path)
    plan.goals[2].agents[0].output["shape"] = "object"
    artifact = tmp_path / "runs/r-ledger" / path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps({
        "title": "报告",
        "chapter_id": "ch-3",
        "sections": [{
            "section_id": "ch-3/sec-1", "goal_id": "goal-1", "title": "节",
            "markdown": "## 结论\n\n- 运行期断言。\n\n## 信息源\n\n- 无。",
        }],
        "缺失清单": [],
        "claims": [raw_claim("c-01", REAL_SHAPE)],
    }, ensure_ascii=False), encoding="utf-8")

    def prepare(store):
        add_evidence(store, "r-ledger", "ev-dup", platform="xhs",
                     permalink=XHS_COMMENT, author="甲")
        add_evidence(store, "r-ledger", "ev-other", platform="xhs",
                     permalink=XHS_OTHER_COMMENT, author="乙")

    _, store, events = _finalize(tmp_path, plan, monkeypatch, prepare=prepare)

    # 库上：主张真写进去了，不是「键不存在」。
    extra = store.get_report("r-ledger")["extra"]
    assert [claim["id"] for claim in extra["claims"]] == ["c-0101"]
    assert extra["claims"][0]["evidence_ids"] == ["ev-dup", "ev-other"]
    assert [row["id"] for row in store.list_evidence("r-ledger")
            if row["extra"].get("claim_ids")] == ["ev-dup", "ev-other"]

    # 报告不再被这一处判红。
    validations = [e["data"] for e in events if e.get("type") == "report_validation"]
    assert validations[-1]["verdict"] == "pass"
    assert not validations[-1]["failures"]

    # 事件上：去重记账查得到。
    deduped = [e["data"] for e in events if e.get("type") == "claims_links_deduped"]
    assert len(deduped) == 1
    assert deduped[0]["count"] == 1
    assert deduped[0]["entries"] == [{
        "claim_id": "c-0101",
        "location": "claims[0].evidence[2]",
        "permalink": XHS_COMMENT,
    }]
