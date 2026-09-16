"""§RPT-5：原声等级闸放宽到 C（D 仍排除）、稿面必标等级、不许再说假话。

三种形态各锁一条（提货单货 3）：
① 有 C 级原文——原话栏给、原声表进、等级闸放行、稿面标等级；
② 真无原文——原话栏空、编码不选、兜底话术仍写「没有」；
③ 可编码范围随闸放宽而上升（A/B → A/B/C，D 不进）。

背景：r-20271e8a5028 正式稿写「证据池未截取到评论正文原话」，而库里 S01 的
content_excerpt 就是「不许碰我的电子闺蜜[发怒]」。写不出来是 QUOTE_GRADES={A,B}
+ 评论在五维结构下天花板是 C 叠出来的死锁，不是采集缺口。
"""
from __future__ import annotations

import asyncio

ORIGINAL = "不许碰我的电子闺蜜[发怒]"
TITLE = "评论 · 放过豆包吧！它只是一个无性别的ai"


def _comment(grade, **overrides):
    row = {"id": "ev-c", "platform": "douyin", "kind": "comment", "citation_no": 1,
           "title": TITLE, "content_excerpt": ORIGINAL, "grade": grade,
           "extra": {"content_kind": "user_opinion"}}
    row.update(overrides)
    return row


def _coded(index, *, grade, quote=ORIGINAL, topics=("交互体验",)):
    return {"id": f"ev-{index:03d}", "platform": "douyin", "kind": "comment",
            "title": TITLE, "content_excerpt": ORIGINAL, "citation_no": index,
            "grade": grade,
            "extra": {"content_kind": "user_opinion", "coding": {
                "coding_version": "v1", "audience": "不明", "scenario": "陪伴",
                "attitude": "正", "topics": list(topics), "quote": quote}}}


# —— ① 有 C 级原文 ——

def test_等级集合是_ABC_不含_D():
    from app.report.polish.run import QUOTE_GRADES

    assert set(QUOTE_GRADES) == {"A", "B", "C"}


def test_C_级评论也给原话栏_D_与未评级不给():
    from app.report.polish.tables import quote_prefix

    assert quote_prefix(_comment("C")) == ORIGINAL
    assert quote_prefix(_comment("D")) is None, "D 级线索级，正文不引"
    assert quote_prefix(_comment(None)) is None, "未评级不引"


def test_等级闸_C_级放行_D_与未评级仍退回():
    from app.report.polish.run import lowgrade_quotes

    block = f"> {ORIGINAL}\n> —— 抖音 · 等级 C [S01]\n"
    assert lowgrade_quotes(block, {1: "C"}) == []
    assert lowgrade_quotes(block, {1: "D"})
    assert lowgrade_quotes(block, {})


def test_稿面必须标等级_且要标对():
    """每条原声的出处行必须写「等级 X」，X 与库里一致——读者要看得见这句是 C 级。"""
    from app.report.polish.run import unlabeled_quotes

    ok = f"> {ORIGINAL}\n> —— 抖音 · 等级 C [S01]\n"
    assert unlabeled_quotes(ok, {1: "C"}) == []
    missing = f"> {ORIGINAL}\n> —— 抖音 [S01]\n"
    problems = unlabeled_quotes(missing, {1: "C"})
    assert len(problems) == 1 and "没有标等级" in problems[0], problems
    wrong = f"> {ORIGINAL}\n> —— 抖音 · 等级 B [S01]\n"
    problems = unlabeled_quotes(wrong, {1: "C"})
    assert len(problems) == 1 and "标错" in problems[0] and "C" in problems[0], problems
    # 把握度那句也是 `>` 块，但它是写手自己的话：没角标没出处行，不上闸。
    assert unlabeled_quotes("> 本报告结论的把握度为**低**，主要因为……\n", {}) == []


def test_原声表带等级列_C_级进表_口径写明含_C_级():
    from app.report.polish.tables import build_tables

    def _build(grade):
        return build_tables(report={"id": "r-1"}, plan={},
                            evidence=[_coded(1, grade=grade)], claims=[],
                            view={"title": "t", "sources": []})

    data = _build("C")
    quotes = data["tables"]["quotes"]
    assert "等级" in quotes["columns"]
    assert quotes["rows"][0]["等级"] == "C"
    assert quotes["rows"][0]["原声"] == ORIGINAL
    assert "C 级" in quotes["basis"], "方法/口径要写明本轮原声含 C 级"
    assert "quotes" not in _build("D")["tables"], "D 级仍不进原声表"


def test_假话闸_未截取到评论正文_判红():
    """库里有正文而稿面说「未截取到」，是与库事实相反的模板句，当轮打回。"""
    from app.report.polish.run import false_fact_lines

    text = ("**原声**：本轮这一格没有可引的原声——S01、S07 均为 C 级评论，"
            "证据池未截取到评论正文原话，只能靠角标指回原帖。\n")
    hits = false_fact_lines(text)
    assert hits and hits[0][0] == 1 and "未截取到评论正文" in hits[0][1], hits
    assert false_fact_lines("本轮这一格没有可引的原声。\n") == []
    # 原声引用块里是发帖人的话，不查。
    assert false_fact_lines("> 这条评论未截取到评论正文\n> —— 抖音 · 等级 C [S01]\n") == []


# —— ② 真无原文 ——

def test_真无原文时原话栏空_编码不选_话术仍写没有():
    from app.reliability.coding import coding_targets
    from app.report.polish.run import false_fact_lines
    from app.report.polish.tables import quote_prefix

    assert quote_prefix(_comment("C", content_excerpt="")) is None
    assert coding_targets([_comment("C", content_excerpt="", title="")]) == []
    # 真没有时，兜底那句照旧合法。
    assert false_fact_lines("**原声**：本轮这一格没有可引的原声（池里没有这一格的原话栏）。\n") == []


# —— ③ 覆盖数随闸放宽而上升 ——

def test_可编码范围_ABC_三条_D_不进():
    from app.reliability.coding import quotable_targets

    rows = [_comment(grade, id=f"ev-{grade}", citation_no=index)
            for index, grade in enumerate("ABCD", start=1)]
    assert sorted(r["id"] for r in quotable_targets(rows)) == ["ev-A", "ev-B", "ev-C"]


# —— 端到端：闸接在写作重试路上 ——

class _Store:
    """S01 是 C 级评论、库里有原文；S02 是 D 级。"""

    def get_report(self, rid):
        return {"id": rid, "title": "T", "research_question": "q", "plan_snapshot": {},
                "extra": {"claims": []}}

    def list_evidence(self, rid):
        return [dict(_comment("C"), id="ev-1", citation_no=1, published_at=None, extra="{}"),
                dict(_comment("D"), id="ev-2", citation_no=2, published_at=None, extra="{}",
                     content_excerpt="随便一句")]


WORK = (f"# 工作稿\n\n{ORIGINAL}\n\n## 信息源\n\n"
        "- [S01] [帖一](https://e.com/a)\n- [S02] [帖二](https://e.com/b)\n")


def _adapter(tail: str):
    class _Adapter:
        async def run(self, task, ctx, on_event=None):
            task.output_path.write_text(
                "这一节的正文[S01]。" * 40 + "\n\n" + tail, encoding="utf-8")
            return type("R", (), {"succeeded": True, "engine_error": None})()

    return _Adapter()


def _polish(tmp_path, tail):
    from app.report.polish.run import polish

    return asyncio.run(polish(_Store(), "r-rpt5", tmp_path / "runs", WORK,
                              template="consulting", adapter=_adapter(tail)))


def test_端到端_C_级带等级标的原声一路写到底(tmp_path):
    result = _polish(tmp_path, f"> {ORIGINAL}\n> —— 抖音 · 等级 C [S01]\n")
    assert result["status"] == "ok", result.get("errors")


def test_端到端_C_级不标等级被退回(tmp_path):
    result = _polish(tmp_path, f"> {ORIGINAL}\n> —— 抖音 [S01]\n")
    assert result["status"] == "failed"
    assert any("没有标等级" in e for e in result["errors"]), result["errors"]


def test_端到端_D_级作原声仍被退回(tmp_path):
    result = _polish(tmp_path, f"> 随便一句\n> —— 抖音 · 等级 D [S02]\n")
    assert result["status"] == "failed"
    assert any("S02（D 级）" in e for e in result["errors"]), result["errors"]


def test_端到端_假话被退回(tmp_path):
    result = _polish(tmp_path, "本轮这一格没有可引的原声——证据池未截取到评论正文原话[S01]。\n")
    assert result["status"] == "failed"
    assert any("未截取到评论正文" in e and "与库事实相反" in e for e in result["errors"]), \
        result["errors"]
