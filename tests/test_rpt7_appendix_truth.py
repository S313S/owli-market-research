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


def _section(md: str, heading: str) -> str:
    """整节原文（说明句 + 表），不只是表格行——说明句也是印给客户的字。"""
    start = md.index(heading)
    end = md.find("\n## ", start + len(heading))
    return md[start:end if end > 0 else len(md)]


def test_non_collection_chapters_move_out_and_drop_the_collection_wording():
    """标签章、一致性检查章一条都不在采，不许套「这一段采集超时没跑完」。

    量的是**整节**，不只是表格行：说明句写「这几段不在采集范围内」照样是在
    客户眼前提「采集」——他刚被那张表误导过一次，这两个字一出现就又要读一遍。
    """
    md = missing_table(MISSING, OBJECTIVES, chapters=_chapters())
    assert len(_blocks(md)[PROCESS_HEADING]) == 3
    assert "采集" not in _section(md, PROCESS_HEADING), _section(md, PROCESS_HEADING)


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


# ── 货 2：章型标签 ──────────────────────────────────────────────────────────
def test_process_rows_never_print_the_internal_step_name():
    """「标签」「一致性检查」是本项目内部的工序名，客户读不懂也不该看见。

    量的是**第一格的字面**：`display_name` 原样漏出去就是「标签（Kimi…）」
    「一致性检查（豆包…）」这两种形状。⛔ 不量整段是否出现「标签」二字——
    「给采到的内容打主题标签」是说这一步在干什么，不是把工序名甩给客户。
    """
    md = missing_table(MISSING, OBJECTIVES, chapters=_chapters())
    cells = [row.split("|")[1].strip()
             for rows in _blocks(md).values() for row in rows]
    assert cells and not [c for c in cells if c.startswith(("标签（", "一致性检查"))], cells


def test_every_chapter_type_in_the_closed_set_gets_a_client_label():
    """章型是闭集，逐个过一遍：谁都不许把 `display_name` 原样漏出去。"""
    from app.plan.chapters import CHAPTER_TYPES
    from app.report.polish.run import _chapter_label

    leaked = []
    for kind in sorted(CHAPTER_TYPES):
        if kind == "collection":
            continue        # 采集章走渠道（实体），另有用例锁
        entry = {"chapter_type": kind, "display_name": "一致性检查",
                 "goal_title": "豆包在国内用户与媒体中的口碑画像", "platforms": [], "entity": ""}
        if "一致性检查" in _chapter_label(entry, None, []):
            leaked.append(kind)
    assert leaked == [], leaked


def test_an_unknown_chapter_type_still_does_not_leak_the_internal_name():
    """章型缺失/越出闭集：退成中性说法，⛔ 不退回 `display_name`，也不编含义。"""
    from app.report.polish.run import _chapter_label

    entry = {"chapter_type": "", "display_name": "标签",
             "goal_title": "Kimi 在国内用户与媒体中的口碑画像", "platforms": [], "entity": ""}
    label = _chapter_label(entry, None, [])
    assert "标签" not in label and label.startswith("中间处理步骤"), label


def test_comparison_chapter_reads_as_a_report_section_not_a_step():
    """goal-6 的横向对比章 `chapter_type=comparison`、`display_name=报告撰写`——
    它是撰写章，按报告那一支写，不该被当成一道内部处理步骤。"""
    from app.report.polish.run import _chapter_label

    entry = {"chapter_type": "comparison", "display_name": "报告撰写",
             "goal_title": "豆包与四款对手的横向对比与观点综合", "platforms": [], "entity": ""}
    assert _chapter_label(entry, "sec-1", ["豆包的口碑画像"]) == (
        "「豆包与四款对手的横向对比与观点综合」的报告·第 1 节（豆包的口碑画像）")


# ── 货 3 ① ：有角标进了正文就不许写「正文未能引用它们」 ────────────────────
def test_timeout_tail_stops_claiming_uncited_when_the_body_did_cite_them():
    """HN 那一章 `cited=2`（S38 在正文真被引）。

    `_YIELDED_TAIL["timeout"]` 写死「正文未能引用它们」，而 `chapter_rows` 早就
    算好了 `cited`——本稿走 `tool_unavailable` 分支侥幸没撞上，换个死因就是假话。
    """
    timeout_hn = [{"goal_id": "goal-1", "chapter_id": "ch-13", "reason": "timeout"}]
    md = missing_table(timeout_hn, OBJECTIVES, chapters=_chapters())
    assert "正文未能引用它们" not in md, md
    assert "采到 7 条，已入库并参与评级与统计；" in md, md


def test_timeout_tail_keeps_the_old_wording_when_nothing_was_cited():
    """一条角标都没进正文：§D-060 那句真机验过的措辞一个字不动。"""
    rows = [{"agent_name": "hn-collect", "goal_id": "goal-1", "platform": "hn",
             "citation_no": None} for _ in range(7)]
    md = missing_table([{"goal_id": "goal-1", "chapter_id": "ch-13", "reason": "timeout"}],
                       OBJECTIVES, chapters=chapter_rows(PLAN, rows))
    assert "这一段的总结超时没写成，正文未能引用它们" in md, md


# ── 货 3 ② ：「各表口径」不许把给写手的指令与内部版本号漏给客户 ──────────────
#: 逐字取自已交用户那份稿的 tables.json（r-3b3482ca7f8b）。
REAL_BASIS = {
    "topic_polarity": {
        "title": "主题提及量与极性词命中（Top 8）",
        "basis": "固定词表 v1 命中计数，不是情感判断；只能说「提及…的条数」，"
                 "不得说「X% 用户认为」。所用词表随报告版本固定，不随单次调研调整。"},
    "attitude_by_topic": {
        "title": "UGC 逐条编码：主题 × 态度条数",
        "basis": "对 90 条已编码的 UGC逐条模型编码后计数（模型编码（v2），另抽 30 条复核、"
                 "28 条与模型判读一致；表内均为条数，不是全网比例。）。"
                 "没命中任何主题的归入「未归主题」，不设它这一格四成条目会凭空消失。"},
    "quotes": {
        "title": "UGC 代表原声（每格按互动量取前 3）",
        "basis": "「代表性」栏标了「无人点赞或评论」的那几条是这一格里没有更好的了才收的，"
                 "⛔ 不得把它们写成多数人的看法、也不得单独拎去当某一方的头号声音。"
                 "本轮原声含 C 级 2 条（「等级」栏标出）——C 级只作旁证，"
                 "正文引它时出处行必须写「等级 C」，读者据此把它当例子，不当依据。"},
}


def test_basis_table_drops_the_orders_aimed_at_the_writer():
    from app.report.polish.run import basis_table

    md = basis_table(REAL_BASIS)
    assert "⛔" not in md, md
    assert "不得把它们写成" not in md and "不得说「X% 用户认为」" not in md, md
    assert "不设它这一格" not in md and "必须写「等级 C」" not in md, md


def test_basis_table_drops_internal_version_tags_but_not_the_real_recheck_numbers():
    from app.report.polish.run import basis_table

    md = basis_table(REAL_BASIS)
    assert "v1" not in md and "v2" not in md, md
    # ⛔ 复核读数是真数，一个都不许动（§D-072 的原话）。
    assert "另抽 30 条复核、28 条与模型判读一致" in md, md
    assert "固定词表命中计数" in md and "模型编码，另抽" in md, md


def test_the_writer_facing_basis_is_left_alone():
    """同一段字进提示词时是写手的护栏（`build_prompt` 整块塞过去），⛔ 不许改源。"""
    from app.report.polish.run import basis_table

    before = REAL_BASIS["quotes"]["basis"]
    basis_table(REAL_BASIS)
    assert REAL_BASIS["quotes"]["basis"] == before
    assert "⛔ 不得把它们写成多数人的看法" in before


def test_quotes_tail_gets_the_same_scrub_as_the_basis_table():
    """同一段口径句在附录里出现两处（口径表 + 原声表表尾），两处必须同形。"""
    from app.report.polish.run import quotes_reference_table

    table = dict(REAL_BASIS["quotes"], columns=["主题"], n=1,
                 rows=[{"主题": "功能与能力", "marks": [96]}])
    md = quotes_reference_table({"quotes": table})
    assert "⛔" not in md and "必须写「等级 C」" not in md, md


# ── 货 4：原声表表尾的样本量要跟表内行数对得上 ────────────────────────────
#: 真机形状（r-3b3482ca7f8b）：`quotes.n = 6`、`rows` 只有 4 行——
#: `coding_tables` 出表时 `n=len(data["quotes"])` 数的是**挑出来的 6 条**，
#: 而 `rows` 又过了一道「没角标就不进表」的筛。表尾于是在 4 行表下写「样本量 6 条」。
def _quotes_table(rows: int = 4, n: int = 6) -> dict:
    return {"quotes": {
        "title": "UGC 代表原声（每格按互动量取前 3）", "n": n,
        "columns": ["主题", "态度", "原声"],
        "rows": [{"主题": "功能与能力", "态度": "正", "原声": f"第 {i} 句",
                  "marks": [96 + i]} for i in range(rows)],
        "basis": "从原文逐字摘出、程序校验过是正文子串的原声。"}}


def test_quotes_tail_counts_the_rows_it_sits_under():
    from app.report.polish.run import quotes_reference_table

    md = quotes_reference_table(_quotes_table())
    assert "样本量 4 条" in md, md
    assert "样本量 6 条" not in md, md


def test_quotes_tail_says_where_the_rest_went():
    """⛔ 不许把差额悄悄抹掉：没进表的那几条要交代一句，且不认领挑选逻辑。"""
    from app.report.polish.run import quotes_reference_table

    md = quotes_reference_table(_quotes_table())
    assert "另有 2 条" in md and "角标" in md, md
    # 不多不少：表内行数与表尾一致时不许多出这半句。
    assert "另有" not in quotes_reference_table(_quotes_table(rows=4, n=4))


def test_quotes_rows_themselves_are_untouched():
    """⛔ 不许改 `quotes` 的挑选逻辑：几行还是几行，顺序也不动。"""
    from app.report.polish.run import quotes_reference_table

    md = quotes_reference_table(_quotes_table())
    body = [line for line in md.splitlines()
            if line.startswith("| 功能与能力")]
    assert len(body) == 4
    assert [line.split("|")[3].strip() for line in body] == [f"第 {i} 句" for i in range(4)]


def test_the_other_appendix_tables_keep_their_own_sample_size():
    """词表命中表的 `n` 数的是证据条数、行是主题——它跟行数本来就不该相等。"""
    from app.report.polish.run import lexicon_reference_table

    md = lexicon_reference_table({"topic_polarity": {
        "title": "主题提及量", "n": 942, "columns": ["主题", "条数"],
        "rows": [{"主题": "价格", "条数": 17}, {"主题": "速度", "条数": 9}],
        "basis": "固定词表命中计数。"}})
    assert "样本量 942 条" in md, md
