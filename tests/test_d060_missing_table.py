"""§D-060 货 2：附录「哪些没采到」表要说真话。

零引擎。夹具照 r-3e04f808dffd 的四行 missing 与计划快照形状造，先造红再造绿。
根因：`_MISSING_REASON` 把 timeout 一律译成「采集超时没跑完」，不看落库条数——
§D-039 之后 timeout 的语义是「超时判 missing、已落库产物不作废」；「缺的是哪一段」
按 goal 取目标整句截 34 字，缺的单位却是单源子章，三行同目标长得一模一样。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from app.report.polish.run import (COLLECTED_HEADING, MISSING_HEADING,
                                   PROCESS_HEADING, missing_table)
from app.report.polish.tables import chapter_rows

ROOT = Path(__file__).resolve().parents[1]


def _forbidden_hits(text: str) -> list[str]:
    spec = importlib.util.spec_from_file_location(
        "cp", ROOT / "scripts" / "acceptance" / "rpt1" / "check_polished.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    return [m.group(0) for pattern in cp.FORBIDDEN for m in re.finditer(pattern, text)]


def _agent(agent_id, chapter_id, kind, display, sources=(), entity=""):
    return {"agent_id": agent_id, "display_name": display, "entity": entity,
            "capability": {"sources": list(sources)},
            "chapter": {"chapter_id": chapter_id, "chapter_type": kind}}


PLAN = {"goals": [
    {"goal_id": "goal-1", "title": "豆包官方产品定位与功能资料采集",
     "objective": "从豆包官网、字节跳动官方公告、应用市场页与Doubao英文官方页采集产品定位。",
     "agents": [_agent("data-collection", "ch-1", "collection", "小红书数据抓取·豆包", ["xhs"], "豆包"),
                _agent("reliability-audit", "ch-2", "audit", "可靠度审计")]},
    {"goal_id": "goal-2", "title": "国内社媒与测评渠道对豆包的用户口碑采集",
     "objective": "从知乎、微博、小红书、B站、贴吧、App Store与安卓应用市场评论采集口碑。",
     "agents": [_agent("data-collection-3", "ch-1", "collection", "微博数据抓取·Doubao", ["weibo"], "Doubao"),
                _agent("data-collection-4", "ch-3", "collection", "微信公众号数据抓取·文心一言",
                       ["wechat_mp"], "文心一言")]},
    {"goal_id": "goal-3", "title": "国内同类AI助手竞品对照素材采集",
     "objective": "采集DeepSeek、Kimi、文心一言的产品定位、能力侧重与国内用户口碑要点。",
     "agents": [_agent("data-collection-6", "ch-3", "collection", "Reddit 数据抓取·豆包", ["reddit"], "豆包"),
                _agent("report-writing-3", "ch-6", "report", "报告撰写")]},
]}
OBJECTIVES = [{"goal_id": g["goal_id"], "objective": g["objective"]} for g in PLAN["goals"]]
MISSING = [
    {"goal_id": "goal-1", "chapter_id": "ch-1", "reason": "timeout"},
    {"goal_id": "goal-2", "chapter_id": "ch-3", "reason": "empty_result"},
    {"goal_id": "goal-3", "chapter_id": "ch-3", "reason": "timeout"},
    {"goal_id": "goal-3", "chapter_id": "ch-6/sec-1", "reason": "conclusion_invalid"},
]


def _rows():
    """证据行：小红书 296 条记在 goal-2 名下（实测就是这样标错的），Reddit 111 条；公众号 0。"""
    rows = [{"agent_name": "data-collection", "goal_id": "goal-2", "platform": "xhs",
             "citation_no": 23 if i < 12 else None} for i in range(296)]
    rows += [{"agent_name": "data-collection-6", "goal_id": "goal-3", "platform": "reddit",
              "citation_no": None} for _ in range(111)]
    rows += [{"agent_name": "data-collection-3", "goal_id": "goal-2", "platform": "weibo",
              "citation_no": 33} for _ in range(27)]
    return rows


def _lines(md: str) -> list[str]:
    """§RPT-7 前的取法：整份产物只有一张表，按出现顺序取数据行。

    ⚠️ 只剩「不给 chapters」那一路还在用它——那一路仍旧只出一张表，逐字未变。
    """
    lines = md.splitlines()
    return [ln for index, ln in enumerate(lines)
            if ln.startswith("| ") and lines[index + 1:index + 2] != ["|---|---|"]]


def _rows_of(md: str, heading: str) -> list[str]:
    """§RPT-7 货 1 之后：一份产物最多三张表，行要按表取。

    旧版 `_lines` 把三张表的行拉平了按下标断言，换表之后下标全串位——
    那不是「尺子被作弊改了」，是它锁的正是被替换掉的那条语义（一张表装三件事）。
    """
    lines = md.splitlines()
    out: list[str] = []
    current = ""
    for index, line in enumerate(lines):
        if line.startswith("## "):
            current = line.strip()
        elif (line.startswith("| ") and current == heading
              and lines[index + 1:index + 2] != ["|---|---|"]):
            out.append(line)
    return out


# ── 造红：旧口径对本研究四行的字面，与 09-11 成稿第 ③ 行相同 ─────────────────
def test_old_wording_calls_111_reddit_rows_not_collected():
    md = missing_table(MISSING, OBJECTIVES)
    assert _lines(md)[2] == "| 采集DeepSeek、Kimi、文心一言的产品定位、能力侧重与国内用… | 这一段采集超时没跑完 |"
    assert _lines(md)[2].split("|")[1] == _lines(md)[3].split("|")[1], "③④ 两行段落名一模一样"


def test_new_wording_says_collected_but_timed_out():
    chapters = chapter_rows(PLAN, _rows())
    md = missing_table(MISSING, OBJECTIVES, chapters=chapters)
    # §RPT-7 货 1：有货的章从「哪些没采到」搬到了「采到了但没写成段落」，措辞未变。
    lines = _rows_of(md, COLLECTED_HEADING)
    # §RPT-3 货 5 改了文案：「未纳入本章分析」失实——这些行照常评级、进统计表，缺的只是角标。
    tail = "已入库并参与评级与统计；这一段的总结超时没写成，正文未能引用它们"
    assert lines[1] == f"| Reddit（豆包） | 采到 111 条，{tail} |"
    assert lines[0] == f"| 小红书（豆包） | 采到 296 条，{tail} |"
    assert _rows_of(md, MISSING_HEADING) == [
        "| 微信公众号（文心一言） | 这一段的信息渠道正常跑通、没报错，"
        "是它在本次检索范围内确实没有相关内容 |"]


def test_yield_is_counted_by_agent_not_by_the_mislabelled_goal():
    """证据表把小红书记在 goal-2、计划记 goal-1——按 agent_name 数才是 296，按 goal 数是 0。"""
    chapters = {(c["goal_id"], c["chapter_id"]): c for c in chapter_rows(PLAN, _rows())}
    assert chapters[("goal-1", "ch-1")]["yielded"] == 296
    assert chapters[("goal-1", "ch-1")]["cited"] == 12


def test_a_real_gap_still_names_the_channel_and_is_not_erased():
    """不能把真缺改没了：公众号×文心一言 0 条，仍旧单独成行，段落名是渠道（实体）。

    §RPT-6 货 3 换了这一行的**措辞**、没换它的存在：`empty_result` 指的是
    「渠道正常跑通、检索范围内确实没有内容」（`sources-v1.md` 第 35–40 行；
    §D-066 的 `SourceUnavailableError` 已经把「源不可用」那一支分了出去），
    写成「没采到」会让客户以为是我们的采集坏了。这条用例锁的是
    「真缺照样列出来、并且写清是哪个渠道」。
    """
    md = missing_table(MISSING, OBJECTIVES, chapters=chapter_rows(PLAN, _rows()))
    (row,) = _rows_of(md, MISSING_HEADING)
    assert row.startswith("| 微信公众号（文心一言） |")
    assert "确实没有相关内容" in row and "没采到" not in row


def test_timeout_with_zero_rows_keeps_the_old_reason():
    rows = [r for r in _rows() if r["agent_name"] != "data-collection-6"]
    md = missing_table(MISSING, OBJECTIVES, chapters=chapter_rows(PLAN, rows))
    # 一条都没入库的采集章：仍是「没采到」，仍走采集口径的理由句。
    assert _rows_of(md, MISSING_HEADING)[1] == "| Reddit（豆包） | 这一段采集超时没跑完 |"


def test_report_section_names_the_goal_and_the_section_not_the_ids():
    md = missing_table(MISSING, OBJECTIVES, chapters=chapter_rows(PLAN, _rows()))
    # §RPT-7 货 1：撰写章不是采集章，归「哪些环节没跑完」；段落名的写法一字未改。
    assert _rows_of(md, PROCESS_HEADING)[0].startswith(
        "| 「国内同类AI助手竞品对照素材采集」的报告·第 1 节（豆包官方产品定位与功能资料采集） |")
    assert _forbidden_hits(md) == [], _forbidden_hits(md)


def test_without_chapters_the_table_is_byte_for_byte_unchanged():
    """老调用方、老产物：不给 chapters 一个字都不变。"""
    assert missing_table(MISSING, OBJECTIVES) == missing_table(MISSING, OBJECTIVES, chapters=())


def test_unknown_chapter_falls_back_to_the_objective_sentence():
    md = missing_table([{"goal_id": "goal-9", "chapter_id": "ch-1", "reason": "timeout"}],
                       OBJECTIVES, chapters=chapter_rows(PLAN, _rows()))
    assert "第 1 段" in md and _forbidden_hits(md) == []


def test_chapter_rows_use_the_platform_display_name():
    rows = {c["agent_id"]: c for c in chapter_rows(PLAN, [])}
    assert rows["data-collection-4"]["platforms"] == ["微信公众号"]
    assert rows["data-collection-6"]["platforms"] == ["Reddit"]
    assert rows["report-writing-3"]["chapter_type"] == "report"
