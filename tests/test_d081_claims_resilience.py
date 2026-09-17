"""§D-081：闭集越界不再整批否决 + replay 换 id 留下的悬空断言必须显形。

真机 r-3b3482ca7f8b（§SRC-5 撰写轮成品）挖出的连环，逐条对上这四条用例：

1. 写手在 sec-4（文心一言）两条主张里把 `stance` 写成 `neutral`（闭集只收
   supports/contradicts）。**2 个越界值把 1360 条断言整批打回**，`report_validation`
   verdict=fail、`register_claims` 一次都没写成。
2. 登记失败 ⇒ `reports.extra.claims` 没被重写，仍是 replay **复制来的**那 1380 条；
   而 `import_research` 给每行 evidence **重新生成 id**（两轮 820 行 id 交集 0），
   于是复制来的 claims 里 **2001 个 evidence_ids 在本研究一个都不存在**。
3. `_audit_firsthand` 算出 0 对一声不吭 return ⇒ 成品看着有 1380 条断言、
   其实一条都对不上证据，零报警。

口径（提货单 §二，调度 2026-09-17 立卡）：
- 货 1 只把**闭集越界**降级成「按条剔除该证据链 + 逐条记账」，⛔ 不静默、
  ⛔ 不放宽闭集本身（`neutral` 不是合法取值，是写手写错了）、⛔ 别的校验一个字不动。
- 货 2 的显形阈值取「命中率 < 100%」，理由见 `audit_dangling_claims` 的注释。

每条用例在 base `6803857` 上被判红的**第一处断言**都落在病象本身，不是落在
「新出参还不存在」上——记账通道的断言一律排在行为断言之后（沿用 §D-075 的写法）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reliability.claims import (
    ClaimsRegistrationError,
    prepare_claim_registration,
    register_claims,
)

from tests.test_c1_claims import add_evidence, make_store, raw_claim, ref


URL_A = "https://www.xiaohongshu.com/explore/6a499e1b00000000070217d7"
URL_B = "https://www.xiaohongshu.com/explore/6a499e1b00000000070217d8"
URL_C = "https://news.ycombinator.com/item?id=45000001"


def _prepare_store(tmp_path: Path):
    store = make_store(tmp_path)
    add_evidence(store, "r-c1", "ev-a", platform="xhs", permalink=URL_A, author="甲")
    add_evidence(store, "r-c1", "ev-b", platform="xhs", permalink=URL_B, author="乙")
    add_evidence(
        store, "r-c1", "ev-c", platform="web_search", permalink=URL_C, author="丙",
    )
    return store


def test_stance_越界只剔除那一条证据链_其余照常登记且留痕(tmp_path: Path) -> None:
    """货 3 条 ①：真机 c-040101/c-040102 那两条 `stance="neutral"` 的形状。

    base 判红处：`register_claims` 抛 `ClaimsRegistrationError`
    （offenders = `claims[0].evidence[0].stance 只能是 supports/contradicts`）。
    记账断言排在行为断言之后。
    """

    store = _prepare_store(tmp_path)
    claims = [
        raw_claim("c-01", [
            ref(URL_A, stance="neutral", firsthand=True),   # 越界，剔除这一条链
            ref(URL_B, stance="supports", firsthand=True),  # 合法，照常登记
        ], text="文心一言口碑"),
        raw_claim("c-02", [ref(URL_C)], text="旁证断言"),
    ]

    registered = register_claims(store, "r-c1", claims, source="chapter")

    # 行为：越界那一条链被剔除，同一条主张的其余证据与别的主张都照常登记。
    assert [claim["id"] for claim in registered] == ["c-01", "c-02"]
    assert registered[0]["evidence_ids"] == ["ev-b"]
    assert registered[1]["evidence_ids"] == ["ev-c"]
    # ⛔ 不许放宽闭集本身：被剔除的那条链不许以 neutral 的身份混进落库结果。
    assert registered[0].get("stance") is None
    assert registered[0].get("firsthand") == ["ev-b"]
    stored = store.get_report("r-c1")["extra"]["claims"]
    assert [claim["id"] for claim in stored] == ["c-01", "c-02"]
    by_id = {row["id"]: row for row in store.list_evidence("r-c1")}
    assert not by_id["ev-a"]["extra"].get("claim_ids")

    # 记账：⛔ 不许静默——哪条 claim、哪个字段、原值是什么，三样都要查得到。
    rejected: list[dict] = []
    register_claims(store, "r-c1", claims, source="chapter", rejected=rejected)
    assert rejected == [{
        "claim_id": "c-01",
        "location": "claims[0].evidence[0]",
        "permalink": URL_A,
        "field": "stance",
        "value": "neutral",
    }]


def test_两条越界不再把整批打回_走收尾链路验库与事件(
    tmp_path: Path, monkeypatch,
) -> None:
    """货 3 条 ②：真机 2/1360 端掉 1360 的那件事，判据落在库与事件上。

    base 判红处：`reports.extra.claims` 里**一条都没有**（`register_claims` 抛错，
    `set_report_claims` 一次都没被调用），`report_validation` verdict=fail。
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
        "claims": [
            raw_claim("c-01", [ref(URL_A)], text="正常主张一"),
            raw_claim("c-02", [ref(URL_B, stance="neutral"), ref(URL_C)], text="越界一"),
            raw_claim("c-03", [ref(URL_C, stance="neutral"), ref(URL_A)], text="越界二"),
            raw_claim("c-04", [ref(URL_B)], text="正常主张二"),
        ],
    }, ensure_ascii=False), encoding="utf-8")

    def prepare(store):
        add_evidence(store, "r-ledger", "ev-a", platform="xhs",
                     permalink=URL_A, author="甲")
        add_evidence(store, "r-ledger", "ev-b", platform="xhs",
                     permalink=URL_B, author="乙")
        add_evidence(store, "r-ledger", "ev-c", platform="web_search",
                     permalink=URL_C, author="丙")

    _, store, events = _finalize(tmp_path, plan, monkeypatch, prepare=prepare)

    # 库上：4 条全登记进去了，没有一条被那 2 处越界连坐。
    extra = store.get_report("r-ledger")["extra"]
    assert [claim["id"] for claim in extra["claims"]] == [
        "c-0101", "c-0102", "c-0103", "c-0104",
    ]
    assert extra["claims"][1]["evidence_ids"] == ["ev-c"]
    assert extra["claims"][2]["evidence_ids"] == ["ev-a"]

    # 报告不再被这一处判红。
    validations = [e["data"] for e in events if e.get("type") == "report_validation"]
    assert validations[-1]["verdict"] == "pass"
    assert not validations[-1]["failures"]

    # 事件上：剔除记账查得到，形制与 §D-075 的 claims_links_deduped 同族。
    rejected = [e["data"] for e in events if e.get("type") == "claims_links_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["count"] == 2
    assert rejected[0]["entries"] == [
        {"claim_id": "c-0102", "location": "claims[1].evidence[0]",
         "permalink": URL_B, "field": "stance", "value": "neutral"},
        {"claim_id": "c-0103", "location": "claims[2].evidence[0]",
         "permalink": URL_C, "field": "stance", "value": "neutral"},
    ]


def test_引用的证据在本研究一条都不存在时悬空必须显形(
    tmp_path: Path, monkeypatch,
) -> None:
    """货 3 条 ③：replay 换了 evidence id 却原样复制 claims 的那件事。

    库里先摆一份 replay 复制来的 claims（`evidence_ids` 指向上一轮的 id），本轮
    章产物里没有 claims 键（登记这一步整个跳过），于是旧值原样留着。

    base 判红处：`reports.extra.claims` 里那条全悬空的主张**原样还在**
    （`len == 1`），一条事件都没发、`report_validation` verdict=pass ——
    与真机「看着有 1380 条断言、其实一条都对不上证据」逐字同形。
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
    }, ensure_ascii=False), encoding="utf-8")

    def prepare(store):
        add_evidence(store, "r-ledger", "ev-new-a", platform="xhs",
                     permalink=URL_A, author="甲")
        add_evidence(store, "r-ledger", "ev-new-b", platform="xhs",
                     permalink=URL_B, author="乙")
        # replay 复制来的旧 claims：evidence_ids 全是上一轮的 id，本研究一个都没有。
        store.set_report_claims("r-ledger", [
            {
                "id": "c-0401", "text": "全悬空的主张",
                "evidence_ids": ["ev-old-1", "ev-old-2"],
                "claims_source": "chapter",
                "firsthand_source": "declared_by_writer",
            },
            {
                "id": "c-0402", "text": "半悬空的主张",
                "evidence_ids": ["ev-old-3", "ev-new-a"],
                "claims_source": "chapter",
                "firsthand_source": "declared_by_writer",
            },
        ])

    _, store, events = _finalize(tmp_path, plan, monkeypatch, prepare=prepare)

    # 库上：全悬空那条被移出 extra.claims，半悬空那条（还有真证据撑着）原样留下。
    extra = store.get_report("r-ledger")["extra"]
    assert [claim["id"] for claim in extra["claims"]] == ["c-0402"]
    assert extra["claims_dropped"] == [{
        "claim_id": "c-0401", "reason": "all_evidence_dangling", "permalinks": [],
    }]

    # 事件上：命中率读得到，⛔ 不许静默通过。
    dangling = [e["data"] for e in events if e.get("type") == "claims_dangling_evidence"]
    assert len(dangling) == 1
    assert dangling[0]["evidence_refs"] == 4
    assert dangling[0]["hit"] == 1
    assert dangling[0]["missing"] == 3
    assert dangling[0]["purged"] == ["c-0401"]

    # 报告侧也读得到：校验判红，收尾带 report_warning。
    validations = [e["data"] for e in events if e.get("type") == "report_validation"]
    assert validations[-1]["verdict"] == "fail"
    assert [f["validator"] for f in validations[-1]["failures"]] == [
        "claims_dangling_evidence",
    ]
    assert [e["data"]["reason"] for e in events if e.get("type") == "report_warning"] == [
        "report_validation_failed",
    ]


def test_正常数据行为不变_且结构违规照旧整批退回(tmp_path: Path) -> None:
    """货 3 条 ④ 回归锁：⛔ 不许顺手放宽别的校验，也不许改正常数据的读数。

    base 侧的**行为断言全绿**（它锁的是不许改的读数，不是病象），红只红在最后
    那两行的新出参上（`TypeError: register_claims() got an unexpected keyword
    argument 'rejected'`）——回归锁本来就该是这个形态。
    """

    store = _prepare_store(tmp_path)
    claims = [raw_claim("c-01", [
        ref(URL_A, firsthand=True),
        ref(URL_B, stance="contradicts"),
    ])]

    registered = register_claims(store, "r-c1", claims, source="chapter")
    assert registered[0]["evidence_ids"] == ["ev-a", "ev-b"]
    assert registered[0]["stance"] == {"ev-b": "contradicts"}
    assert registered[0]["firsthand"] == ["ev-a"]
    extra = store.get_report("r-c1")["extra"]
    assert extra["claims_dropped"] == []
    rejected: list[dict] = []
    register_claims(store, "r-c1", claims, source="chapter", rejected=rejected)
    assert rejected == []

    # 结构违规（id 不合法、evidence 不是 object）照旧整批退回，一条不许被剔除掩盖。
    with pytest.raises(ClaimsRegistrationError) as caught:
        prepare_claim_registration(
            store.list_evidence("r-c1"),
            [
                raw_claim("c-02", [ref(URL_A, stance="neutral")]),
                {"id": "坏 id", "text": "x", "evidence": [ref(URL_B)]},
            ],
            source="chapter",
        )
    assert any("id 不符合" in item for item in caught.value.offenders)
    assert not any("stance" in item for item in caught.value.offenders)
    assert [claim["id"] for claim in
            store.get_report("r-c1")["extra"]["claims"]] == ["c-01"]
