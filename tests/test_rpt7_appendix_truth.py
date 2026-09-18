"""§RPT-7：附录「哪些没采到」把没丢的和非采集工序都算了进去，还漏了内部工序名。

零引擎。夹具照 r-3b3482ca7f8b 的五行 missing 与计划快照形状造：
① HN 章 `yielded=7 / cited=2`，内容早已入库、S38 还进了正文，却被列在「哪些没采到」；
② `chapter_type=audit` 的一致性检查章、`tagging` 的标签章 `platforms=[]`、`yielded=0`，
   一条都不在采，却被套上采集口径文案「这一段采集超时没跑完」；
③ `_chapter_label` 只认 collection/report，其余落 `display_name` 兜底，
   于是内部工序名「标签」「一致性检查」原样印给客户。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from app.report.polish.run import (COLLECTED_HEADING, MISSING_HEADING,
                                   PROCESS_HEADING, PROGRAM_APPENDIX_HEADINGS,
                                   missing_table)
from app.report.polish.tables import chapter_rows

ROOT = Path(__file__).resolve().parents[1]


def _check_polished():
    spec = importlib.util.spec_from_file_location(
        "cp_rpt7", ROOT / "scripts" / "acceptance" / "rpt1" / "check_polished.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _forbidden_hits(text: str) -> list[str]:
    cp = _check_polished()
    return [m.group(0) for pattern in cp.FORBIDDEN for m in re.finditer(pattern, text)]


def _agent(agent_id, chapter_id, kind, display, sources=(), entity=""):
    return {"agent_id": agent_id, "display_name": display, "entity": entity,
            "capability": {"sources": list(sources)},
            "chapter": {"chapter_id": chapter_id, "chapter_type": kind}}


#: 照 r-3b3482ca7f8b 的形状：goal-1 的 HN（有货）、Product Hunt（真 0 条）、
#: 一致性检查（audit）；goal-2 / goal-3 的标签章（tagging）。
PLAN = {"goals": [
    {"goal_id": "goal-1", "title": "豆包在国内用户与媒体中的口碑画像",
     "objective": "采集豆包在国内社媒、媒体与海外社区上的口碑。",
     "agents": [
         _agent("hn-collect", "ch-13", "collection", "HN 数据抓取·豆包", ["hacker_news"], "豆包"),
         _agent("ph-collect", "ch-15", "collection", "Product Hunt 数据抓取·豆包",
                ["product_hunt"], "豆包"),
         _agent("consistency-check", "ch-18", "audit", "一致性检查"),
     ]},
    {"goal_id": "goal-2", "title": "DeepSeek 在国内用户与媒体中的口碑画像",
     "objective": "采集 DeepSeek 在国内社媒与媒体上的口碑。",
     "agents": [_agent("tagging-2", "ch-4", "tagging", "标签")]},
    {"goal_id": "goal-3", "title": "Kimi 在国内用户与媒体中的口碑画像",
     "objective": "采集 Kimi 在国内社媒与媒体上的口碑。",
     "agents": [_agent("tagging-3", "ch-4", "tagging", "标签")]},
]}
OBJECTIVES = [{"goal_id": g["goal_id"], "objective": g["objective"]} for g in PLAN["goals"]]
#: 真机那五行，reason 逐字照抄 `cross-comparison-report.json` 的缺失清单。
MISSING = [
    {"goal_id": "goal-1", "chapter_id": "ch-13", "reason": "tool_unavailable"},
    {"goal_id": "goal-1", "chapter_id": "ch-15", "reason": "empty_result"},
    {"goal_id": "goal-1", "chapter_id": "ch-18", "reason": "timeout"},
    {"goal_id": "goal-2", "chapter_id": "ch-4", "reason": "retry_exhausted"},
    {"goal_id": "goal-3", "chapter_id": "ch-4", "reason": "timeout"},
]


def _rows():
    """HN 采到 7 条、其中 2 条进了引用池（S38 在正文真被引）；Product Hunt 一条都没有。"""
    return [{"agent_name": "hn-collect", "goal_id": "goal-1", "platform": "hn",
             "citation_no": 38 if i == 0 else (91 if i == 1 else None)} for i in range(7)]


def _chapters():
    return chapter_rows(PLAN, _rows())


def _blocks(md: str) -> dict[str, list[str]]:
    """按二级标题切块 → {标题: 该块的**数据行**}。附录这几节是平级的三张表。

    表头行按「下一行是 `|---|`」认，⛔ 不按表头字面认——三张表的表头各不相同，
    照字面剔会把某一张的表头当成数据行数进去。
    """
    lines = md.splitlines()
    out: dict[str, list[str]] = {}
    current = ""
    for index, line in enumerate(lines):
        if line.startswith("## "):
            current = line.strip()
            out[current] = []
        elif line.startswith("| ") and not lines[index + 1:index + 2][:1] == ["|---|---|"]:
            out.setdefault(current, []).append(line)
    return out


# ── 货 1：三张表分流 ────────────────────────────────────────────────────────
def test_collected_chapter_leaves_the_not_collected_table():
    """HN 采到 7 条、已入库，它不该出现在「哪些没采到」里。"""
    blocks = _blocks(missing_table(MISSING, OBJECTIVES, chapters=_chapters()))
    assert all("Hacker News" not in row for row in blocks[MISSING_HEADING])
    assert any("Hacker News" in row for row in blocks[COLLECTED_HEADING])


def test_not_collected_table_keeps_only_the_real_zero_yield_collection_gap():
    """真缺的只有 Product Hunt 一行：渠道跑通了、这轮确实没有内容。"""
    blocks = _blocks(missing_table(MISSING, OBJECTIVES, chapters=_chapters()))
    assert len(blocks[MISSING_HEADING]) == 1
    assert blocks[MISSING_HEADING][0].startswith("| Product Hunt（豆包） |")
    assert "确实没有相关内容" in blocks[MISSING_HEADING][0]


def test_non_collection_chapters_move_out_and_drop_the_collection_wording():
    """标签章、一致性检查章一条都不在采，不许套「这一段采集超时没跑完」。"""
    md = missing_table(MISSING, OBJECTIVES, chapters=_chapters())
    blocks = _blocks(md)
    assert len(blocks[PROCESS_HEADING]) == 3
    assert "采集" not in "\n".join(blocks[PROCESS_HEADING])
    assert all("采集" not in row for row in blocks[COLLECTED_HEADING])


def test_three_blocks_come_in_a_fixed_order_and_empty_ones_are_not_printed():
    md = missing_table(MISSING, OBJECTIVES, chapters=_chapters())
    order = [line.strip() for line in md.splitlines() if line.startswith("## ")]
    assert order == [MISSING_HEADING, COLLECTED_HEADING, PROCESS_HEADING]
    only_process = missing_table(MISSING[3:], OBJECTIVES, chapters=_chapters())
    assert [line.strip() for line in only_process.splitlines()
            if line.startswith("## ")] == [PROCESS_HEADING]


def test_new_headings_are_registered_as_program_blocks():
    """尺子按 `PROGRAM_APPENDIX_HEADINGS` 剜程序块；漏登记就会被当成写手正文量篇幅。"""
    assert COLLECTED_HEADING in PROGRAM_APPENDIX_HEADINGS
    assert PROCESS_HEADING in PROGRAM_APPENDIX_HEADINGS


def test_nothing_missing_still_says_so_once():
    assert missing_table([], OBJECTIVES, chapters=_chapters()).count("## ") == 1


def test_unknown_chapter_still_falls_back_to_the_not_collected_table():
    """对不上章的行（源对账那路 chapter_id=source/xxx）章型未知，仍留在原来那张表。"""
    md = missing_table([{"goal_id": "goal-9", "chapter_id": "ch-1", "reason": "timeout"}],
                       OBJECTIVES, chapters=_chapters())
    assert [line.strip() for line in md.splitlines()
            if line.startswith("## ")] == [MISSING_HEADING]


def test_no_internal_words_in_any_of_the_three_blocks():
    md = missing_table(MISSING, OBJECTIVES, chapters=_chapters())
    assert _forbidden_hits(md) == [], _forbidden_hits(md)
