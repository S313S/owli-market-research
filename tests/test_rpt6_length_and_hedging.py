"""§RPT-6 正式稿偏短 + 限定词过密（09-16 16:56 新稿 check_polished 两条黄）。

零引擎、零采集：只喂离线夹具给合并器、提示词与尺子。

定因（读 `r-20271e8a5028` 的产物拿的读数，不是猜的）：

- ⒜ 限定词 4 处 > 上限 2 —— **规则的单位是「节」，写作的单位是「片」**。
  `writing-rules.md §5.1` 写的是「限定词一节最多两处」，而 `consulting/SKILL.md`
  主题段五步第 4 步要求**每条发现**写一句反证或限定；分片之后一片 = 一条发现，
  兄弟片只拿到**标题行**不拿正文（`run._task_head` 有意如此，给了正文提示词按片翻倍）。
  真稿逐片实测 0 / 1 / 1 / 2 处——**每片单独都守住了上限 2**，合并成节就是 4 处。
  这与 §RULE-1 修过的「假设与不确定性出现 5 处」是同一类病：提示词按片发，尺子按节量。
  且 4 处里 3 处说的是同一件事（「只有单条 C 级信号，不能外推为普遍」），
  那是**整份样本的属性**，程序已经在摘要末尾那句把握度里说过一次了。

- ⒝ 写手正文 5 998 字符 < 下限 7 000 —— **预算表只有上限没有下限**。
  那一轮的打回台账里这一节零打回、零超时，`_timeout_hint` 的「压到三句以内」
  降级提示词**一次都没被用到**，所以不是墙钟或重写打回压出来的。
  逐节实测全部落在上限的 57–74%：执行摘要 581/800、每片 617–743/1000、
  论据与数据 549/800、对不同读者的含义 857/1500、附录 1 142/1800。
  预算表周围全是单向措辞（「这份稿要短一半」「别写长」「超预算就删」），
  写手没有任何理由往上写；每节写到六七成，合计必然低于下限。

- 货 3（调度 09-17 加）：`_MISSING_REASON['empty_result']` 渲染成「这一段跑完了但没采到
  任何内容」，读者读成「你们没采到」。而 `empty_result` 在本项目里是有定义的——
  `prompts/common/sources-v1.md` 第 35–40 行与 `source_mcp.SourceUnavailableError`
  （§D-066）明写「源不可用」与「搜到 0 条」是两回事，**只有工具正常返回空列表才算
  真的搜到 0 条**。所以两种形态在账本里分得出来，缺的只是稿面上的人话。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "rpt6"
SKILL_MD = ROOT / "app" / "skills" / "report-polish" / "consulting" / "SKILL.md"

_spec = importlib.util.spec_from_file_location(
    "check_polished_rpt6", ROOT / "scripts" / "acceptance" / "rpt1" / "check_polished.py")
check_polished = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_polished)


def _real_shards() -> list[str]:
    return [(FIXTURES / f"02-关键发现.shard-{i}.md").read_text(encoding="utf-8").strip()
            for i in range(1, 5)]


def _write_shards(tmp_path: Path, bodies):
    from app.report.polish.sharding import shard_paths

    section = tmp_path / "02-关键发现.md"
    paths = shard_paths(section, len(bodies))
    for path, body in zip(paths, bodies):
        path.write_text(body, encoding="utf-8")
    return paths


# ── 货 1：跨片重复的限定收尾段，在合并处收 ────────────────────────────────


def test_真稿四片合并后限定词从4处降到节上限内(tmp_path):
    """判据拿真稿量。四片逐片 0/1/1/2，合并 4 处；收完 ≤2。"""
    from app.report.polish.sharding import HEDGE_PER_SECTION, hedge_count, merge_shards

    bodies = _real_shards()
    assert [hedge_count(b) for b in bodies] == [0, 1, 1, 2], "夹具变了，定因读数对不上"
    assert hedge_count("\n\n".join(bodies)) == 4

    merged = merge_shards(_write_shards(tmp_path, bodies))
    assert hedge_count(merged) <= HEDGE_PER_SECTION


def test_真稿收完之后尺子那一条黄也灭了(tmp_path):
    """收的是不是「这件事」——直接拿验收尺子 ⒜ 量合并后的节，不自造尺子。"""
    from app.report.polish.sharding import merge_shards

    merged = merge_shards(_write_shards(tmp_path, _real_shards()))
    markdown = "# 关键发现\n\n" + merged + "\n"
    assert check_polished.hedge_density(markdown) == []


def test_留下的是节内第一处限定_收的是第二遍第三遍(tmp_path):
    """第一遍把话说到了；读者读到第三遍开始跳过（§5.1 的立法理由）。

    真稿里这三句说的是同一件事，按文档序：第 2 片「不能外推为国内用户的普遍评价」、
    第 3 片「不能外推为唱歌功能的普遍表现」、第 4 片「不能外推为国内用户的普遍态度」。
    从后往前收，留下的就是第 2 片那一句。
    """
    from app.report.polish.sharding import merge_shards

    merged = merge_shards(_write_shards(tmp_path, _real_shards()))
    assert "不能外推为国内用户的普遍评价" in merged, "节内第一处「不能外推」不许动"
    assert "不能外推为唱歌功能的普遍表现" not in merged, "第二遍该收掉"
    assert "不能外推为国内用户的普遍态度" not in merged, "第三遍该收掉"


def test_被收的限定段原样留在片文件里_一个字都没丢(tmp_path):
    """收在**合并处**，不在片上：片文件是写手交的活，一个字都不改。

    ⛔ 与「不许靠删限定句压篇幅」不冲突——那条禁的是写手为了压字数删限定；
    这里是同一句话说了三遍，收的是第二遍第三遍，第一遍原样留在稿上。
    """
    from app.report.polish.sharding import merge_shards

    bodies = _real_shards()
    paths = _write_shards(tmp_path, bodies)
    merge_shards(paths)
    for path, body in zip(paths, bodies):
        assert path.read_text(encoding="utf-8") == body


def test_限定没超节上限时一个字节都不动(tmp_path):
    """没超就别动——分片往返「逐字节相同」那条判据不许被这一改动破了。"""
    from app.report.polish.sharding import merge_shards

    bodies = ["## 一\n\n正文[S01]。\n\n这条结论在样本外不能外推[S01]。",
              "## 二\n\n正文[S02]。\n\n证据待核实[S02]。"]
    merged = merge_shards(_write_shards(tmp_path, bodies))
    assert merged == "\n\n".join(bodies)


def test_角标只剩这一处时不收_改收前面收得动的那一段(tmp_path):
    """信息源清单只列正文实引过的角标：收掉最后一处等于把一条源从清单里抹了。

    末片那段带的 S09 全节只此一处，跳过它；往前收第 2 片那段（S02 别处还在），
    照样收到上限——守卫保的是角标，不是「收不动就放弃」。
    """
    from app.report.polish.sharding import HEDGE_PER_SECTION, hedge_count, merge_shards

    bodies = ["## 一\n\n正文[S01]。\n\n样本单源[S01]。",
              "## 二\n\n正文[S02]。\n\n证据待核实[S02]。",
              "## 三\n\n正文[S03]。\n\n这一条不能外推[S09]。"]
    merged = merge_shards(_write_shards(tmp_path, bodies))
    assert "[S09]" in merged and "这一条不能外推" in merged, "S09 只在这一段出现过，不许收"
    assert "证据待核实" not in merged, "S02 别处还在，这一段收得动"
    assert hedge_count(merged) <= HEDGE_PER_SECTION


def test_整片只有一段时不收_不把这一条发现掏空(tmp_path):
    from app.report.polish.sharding import merge_shards

    bodies = ["## 一\n\n正文单源[S01]。",
              "## 二\n\n正文待核实[S02]。",
              "## 三\n\n这一条不能外推[S03]，正文[S03]。"]
    merged = merge_shards(_write_shards(tmp_path, bodies))
    assert merged.count("## ") == 3
    assert "正文[S03]" in merged


def test_不是收尾段的限定不收_那是这条发现的结论句(tmp_path):
    """真稿末片那句「不足以直接推动产品或品牌决策」是**开篇结论句**，收了这条发现就散了。"""
    from app.report.polish.sharding import merge_shards

    merged = merge_shards(_write_shards(tmp_path, _real_shards()))
    assert "不足以直接推动产品或品牌决策" in merged


def test_表格与引用块里的限定不当收尾段收(tmp_path):
    from app.report.polish.sharding import merge_shards

    bodies = ["## 一\n\n正文[S01]。\n\n样本单源[S01]。",
              "## 二\n\n正文[S02]。\n\n> 这事待核实，不能外推\n> —— 抖音 · 等级 C [S02]"]
    merged = merge_shards(_write_shards(tmp_path, bodies))
    assert "> 这事待核实，不能外推" in merged, "原声是发帖人的话，程序不许动"


def test_生产与验收共用同一份限定词表(tmp_path):
    """同一个概念两处两个定义，是本项目现形过的一种假绿。"""
    from app.report.polish import sharding

    assert check_polished.HEDGE_WORDS is sharding.HEDGE_WORDS
    assert check_polished.HEDGE_PER_SECTION == sharding.HEDGE_PER_SECTION


# ── 货 2：篇幅预算要有下限 ────────────────────────────────────────────────

#: 预算表的行：`| 标签 | 下限–上限 | 备注 |`。破折号用 `–`（en dash）或 `-` 都认。
_BUDGET_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*[–-]\s*(\d+)\s*\|", re.MULTILINE)
_PER_FINDING = re.compile(r"关键发现.*?(\d+)\s*条时")


def _budget_rows() -> list[tuple[str, int, int]]:
    text = SKILL_MD.read_text(encoding="utf-8")
    block = text.split("## 篇幅预算", 1)
    assert len(block) == 2, "consulting 模板里找不到「篇幅预算」这一节"
    return [(m.group(1), int(m.group(2)), int(m.group(3)))
            for m in _BUDGET_ROW.finditer(block[1].split("\n## ", 1)[0])]


def test_预算表每一行都给区间_不只给上限():
    """⒝ 的定因就在这里：只给上限，写手每节写到六七成，合起来必然低于下限。"""
    rows = _budget_rows()
    assert len(rows) >= 5, f"预算表没解析出几行（解析到 {len(rows)} 行），行格式变了？"
    for label, low, high in rows:
        assert 0 < low < high, f"「{label}」这一行不是区间：{low}–{high}"


#: 货 1 那一刀落在写手交稿**之后**：合并「关键发现」时收掉跨片重复的限定收尾段。
#: 09-16 真稿实测收掉 171 字符（5 998 → 5 827）。所以预算表的下限得比尺子的下限
#: 高出这么多富余，否则写手照表写到下限、被收一刀就掉到线下——两货各自都对、
#: 接起来不对，正是「交活要报接缝」说的那种缺口。取 300 是给两三段留的量。
FOLD_HEADROOM = 300


def test_预算表的区间加起来正好落在尺子的带宽里():
    """接缝：SKILL 的预算表与 `check_polished` 的 7 000–9 000 是同一件事的两头。

    ⛔ 这条用例**不许**靠改 `LENGTH_MIN_CHARS` 变绿——那是改尺子作弊。
    要变绿只能把预算表的下限抬到够得着尺子。
    """
    rows = _budget_rows()
    per_finding = {int(m.group(1)): (low, high) for label, low, high in rows
                   if (m := _PER_FINDING.search(label))}
    fixed = [(low, high) for label, low, high in rows if not _PER_FINDING.search(label)]
    assert set(per_finding) == {3, 4, 5}, f"关键发现要按 3/4/5 条各给一档，现在是 {sorted(per_finding)}"

    floor = check_polished.LENGTH_MIN_CHARS + FOLD_HEADROOM
    for count, (low, high) in per_finding.items():
        low_sum = sum(l for l, _ in fixed) + count * low
        high_sum = sum(h for _, h in fixed) + count * high
        assert low_sum >= floor, (
            f"{count} 条发现时，各节下限加起来才 {low_sum} 字符，够不着 {floor}"
            f"（尺子下限 {check_polished.LENGTH_MIN_CHARS} + 合并那一刀的富余 "
            f"{FOLD_HEADROOM}）——写手照表写满，被收掉重复的限定段之后仍会掉到线下")
        assert high_sum <= check_polished.LENGTH_MAX_CHARS, (
            f"{count} 条发现时，各节上限加起来 {high_sum} 字符，"
            f"越过尺子的上限 {check_polished.LENGTH_MAX_CHARS}——照表写满反而超")


def _shard_prompt(count: int = 4) -> str:
    from app.report.polish.run import build_prompt
    from app.report.polish.sharding import parse_findings
    from app.report.polish.skills import get_template

    summary = "\n".join(f"{i}. 【C】第 {i} 条结论[S0{i}]" for i in range(1, count + 1))
    findings = parse_findings(summary)
    assert len(findings) == count
    data = {"research_question": "q", "objectives": [], "entities": [], "subjects": [],
            "sources": [], "tables": {}, "counts": {}, "audience": {}}
    return build_prompt(get_template("consulting"), data, "# 工作稿\n",
                        Path("/tmp/02-关键发现.shard-1.md"),
                        parts=[("执行摘要", Path("/tmp/01.md")), ("关键发现", Path("/tmp/02.md"))],
                        current="关键发现", finding=findings[0], findings=findings)


def test_片提示词按条数指到预算表的那一档():
    """写手一片只看得见自己那条，得由程序告诉它这一节共几条、该查哪一档。"""
    prompt = _shard_prompt(4)
    assert "篇幅预算" in prompt
    assert "4 条时" in prompt


def test_片提示词要写手写到区间下限以上():
    assert "下限" in _shard_prompt(4)


def test_片提示词不再把反证或限定说成必做的第四步():
    """SKILL 原文写的是「这一步只在这条结论真的撑不住时写」，片提示词把这个条件抹掉了。"""
    prompt = _shard_prompt(4)
    head = prompt.split("# 共用硬规则", 1)[0]
    assert "反证或限定" in head
    assert "撑不住" in head, "片提示词把 SKILL 第 4 步的条件抹掉了，于是每片都补一句"


def test_片提示词告诉写手兄弟片看不见彼此():
    """不说破的话，每片都合规、合起来就超——这就是 ⒜ 的成因。"""
    head = _shard_prompt(4).split("# 共用硬规则", 1)[0]
    assert "看不见" in head
    assert "把握度" in head, "整份样本共有的局限归摘要末尾那句，得说明白"


# ── 货 3：「真实无料」与「没采到」要分得开 ────────────────────────────────


def _why(reason: str, yielded: int = 0, cited: int = 0) -> str:
    """缺口清单里这一行的「为什么缺」。`yielded` = 这一段实际落库的条数。

    §RPT-7 货 3 ①：`cited` 与 `yielded` 分开给。本包之前这里写的是 `cited=yielded`
    ——顺手写的，不是本项目的事实（HN 那一章 7 条入库、只有 2 条进了引用池）。
    而「正文未能引用它们」那一支现在按 `cited` 判，混在一起就量不出它。
    有角标进正文的那一支由 `tests/test_rpt7_appendix_truth.py` 锁。
    """
    from app.report.polish.run import missing_table

    chapters = [{"goal_id": "goal-1", "chapter_id": "ch-15", "chapter_type": "collection",
                 "goal_title": "口碑画像", "display_name": "d", "entity": "豆包",
                 "platforms": ["Hacker News"], "yielded": yielded, "cited": cited}]
    table = missing_table([{"goal_id": "goal-1", "chapter_id": "ch-15", "reason": reason}],
                          [{"goal_id": "goal-1", "objective": "采 Product Hunt 上豆包的条目"}],
                          chapters=chapters)
    row = [line for line in table.splitlines() if line.startswith("|")][-1]
    return row.split("|")[2].strip()


def test_源正常返回零结果写成真实无料_不写成没采到():
    """用户已拍「Product Hunt 的 0 如实写明」。

    `empty_result` 在本项目里有定义（`sources-v1.md` 第 35–40 行、§D-066
    `SourceUnavailableError`）：只有工具正常返回空列表才算它，源报错归 tool_unavailable。
    稿面上却写成「跑完了但没采到任何内容」，客户读成「你们的采集出了问题」。
    """
    why = _why("empty_result")
    assert "没报错" in why or "正常" in why, f"读不出「渠道是好的」：{why}"
    assert "没采到" not in why, f"仍写成我们没采到：{why}"


def test_源接不上仍旧写成渠道接不上():
    """形态 2：源报错／没配好且一条都没落库（实例：X 那一轮缺配置）。"""
    assert "接不上" in _why("tool_unavailable")


def test_已入库的那一段不许写成没采到_也不许赖渠道():
    """形态 3：账本记「接不上」，内容其实已经落库（实例：Hacker News 那 7 条）。

    对读者是双重失实：既不是渠道的问题，也不是没采到。判据落在 `yielded` 上——
    它数的是库里真有多少行，所以「内容进没进库」这件事账本答得了。
    """
    why = _why("tool_unavailable", yielded=7)
    assert "采到 7 条" in why and "已入库" in why
    assert "没采到" not in why, f"内容就在库里，不许说没采到：{why}"
    assert "接不上" not in why, f"不是渠道的问题，不许赖渠道：{why}"


def test_已入库时不认领死因_账本分不出就不写():
    """⛔ 「是上游断了还是我们自己拦的」账本分不出，硬写一句就是编。"""
    why = _why("tool_unavailable", yielded=7)
    for guess in ("接口", "配置", "拦", "拒", "故障", "报错"):
        assert guess not in why, f"认领了账本里查不到的死因「{guess}」：{why}"


def test_超时且已入库那一支的措辞一字不改():
    """§D-060 的原话是真机验过的，推广到别的理由码时不许顺手改掉它。"""
    assert _why("timeout", yielded=111) == (
        "采到 111 条，已入库并参与评级与统计；这一段的总结超时没写成，正文未能引用它们")


def test_三种形态的人话两两不同():
    """⛔ 不许拿同一句话蒙混过去。"""
    said = {"真实无料": _why("empty_result"),
            "渠道接不上": _why("tool_unavailable"),
            "已入库": _why("tool_unavailable", yielded=7)}
    assert len(set(said.values())) == 3, said


def test_缺口原因这张表不带内部词():
    """程序生成的文本照样被尺子①抓（§D-072 实测）。"""
    from app.report.polish.run import missing_table

    rows = [{"goal_id": "goal-1", "chapter_id": "ch-1", "reason": r}
            for r in ("empty_result", "tool_unavailable", "timeout", "blocked")]
    chapters = [{"goal_id": "goal-1", "chapter_id": "ch-1", "chapter_type": "collection",
                 "goal_title": "口碑画像", "display_name": "d", "entity": "豆包",
                 "platforms": ["Hacker News"], "yielded": 7, "cited": 7}]
    for where in ((), chapters):
        table = missing_table(rows, [{"goal_id": "goal-1", "objective": "采一段"}],
                              chapters=where)
        assert check_polished.check_no_internal_words("# 附录\n\n" + table) == []
        assert check_polished.machine_talk("# 附录\n\n" + table) == []
