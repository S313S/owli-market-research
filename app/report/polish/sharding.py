"""正式稿的「一条发现一片」分片：片数从已写成的执行摘要里读，不写死。

**为什么要切**：撰写已经拆到「节」，没拆到「片」；「关键发现」实测单节 2–22 分钟
（`run.py` 的 `SECTION_TIMEOUT_SECONDS` 注释），而本机代理把单次流式响应掐在 5–6 分钟
——09-07 那一格两轮独立复现（4 分 59 秒 / 5 分 47 秒），墙钟从 900 放宽到 1800 照样死。
问题不是时间不够，是**单次长流本身撑不住**，所以往下切。

**为什么不复用工作稿那套**（`orchestrator/sectioning.py` 的 `write_shard_sizes` 等，
且那是本包禁区）：它切的是**证据池条目列表**，前提是「入参是一串可并列的条目」。
正式稿各片**入参完全相同**（同一份 63.7 KB 提示词），变的是**写哪一段输出**。
前提不成立，硬套等于误用。片命名抄它的形态（`02-关键发现.shard-1.md`）但不 import。

**为什么合并基本就是拼接**：正式稿的信息源清单由代码确定性生成（`run.sources_table`），
片正文是纯散文 + `## 小标题`，没有工作稿那套信封（信息源去重 / 结论行归并 / 缺失清单），
所以不用 `markdown.merge_section_shards`。

⚠️ §RPT-6 给上面这句话补了一个例外（「结论要标注适用范围」——前提变了就得退场）：
**限定句是分片之后才长出来的一个信封。** 规则的单位是「节」（`writing-rules.md §5.1`
「限定词一节最多两处」），写作的单位却是「片」，而兄弟片只拿得到标题行、拿不到正文
（`run._task_head` 有意如此）。于是每片各写一句都合规，合并成节就超——09-16 真稿
逐片实测 0 / 1 / 1 / 2 处，合并 4 处。片之间看不见彼此，这笔账只能在合并处收，
所以 `merge_shards` 多了一道 `fold_repeated_hedges`。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

#: 摘要里的发现行：行首编号 + 正文。SKILL 硬性规定「3–5 条关键发现，每条一行，
#: 格式固定 `1. 【A】结论句[S12][S18]`」。只认顶格的编号行——续行与引用块不算。
#: §D-072 货 3 把它转正（原 `_FINDING_LINE`）：`run.attitude_line` 的插入点也要按
#: 这个列表定位，两处各写一份正则的话，写手换个写法会一处跟得上一处跟不上。
FINDING_LINE = re.compile(r"^(\d+)\.[ \t]+(\S.*)$", re.MULTILINE)
_MARK = re.compile(r"\[S(\d{2,})\]")
#: 少于这么多条就不切：一条发现单独成节本来就不长，切了徒增合并面。
#: 也是解析失灵时的兜底——读不出编号列表就退回整节写一次（老行为）。
MIN_FINDINGS_TO_SHARD = 2
#: 多于这么多条不再加片：SKILL 上限是 5 条，留一点余量给写手多写一条的情况。
#: 超出的条数并进最后一片，**不丢**——丢一条发现是内容错误，比片大一点坏得多。
MAX_SHARDS = 6


@dataclass(frozen=True)
class Finding:
    """摘要里的一条关键发现。`index` 从 1 起，与片号一致。"""

    index: int
    text: str                       # 编号后的原话，原样带角标
    marks: tuple[str, ...]          # 这条发现自带的角标，升序去重

    @property
    def title_line(self) -> str:
        return f"{self.index}. {self.text}"


def parse_findings(summary_markdown: str) -> list[Finding]:
    """从写成的执行摘要里抽出关键发现编号列表。抽不出就返回空表，由调用方兜底。

    只在摘要这一节里找，所以不会撞上「建议」节那份同形状的编号列表。
    编号不连续（写手漏号）也照收，按出现次序重排——片号必须连续，否则片路径打架。
    """
    findings = []
    for order, match in enumerate(FINDING_LINE.finditer(summary_markdown or ""), 1):
        text = match.group(2).strip()
        marks = tuple(f"S{int(n):02d}" for n in sorted({int(m) for m in _MARK.findall(text)}))
        findings.append(Finding(index=order, text=text, marks=marks))
    if len(findings) <= MAX_SHARDS:
        return findings
    # 超出上限的并进最后一条，不丢：丢一条发现是内容错误。
    tail = findings[MAX_SHARDS - 1:]
    merged = Finding(index=MAX_SHARDS,
                     text="；".join(f.text for f in tail),
                     marks=tuple(sorted({m for f in tail for m in f.marks})))
    return findings[:MAX_SHARDS - 1] + [merged]


def should_shard(findings: Sequence[Finding]) -> bool:
    """够不够条数值得切。不够就退回「整节写一次」——老行为，不是新失败。"""
    return len(findings) >= MIN_FINDINGS_TO_SHARD


def shard_path(section_path: Path, index: int) -> Path:
    """`02-关键发现.md` → `02-关键发现.shard-1.md`。

    抄工作稿 `write_shard_path` 的形态，不 import（它在禁区文件里）。
    与分节文件同一个目录，所以 `clear_stale_parts` 的 `[0-9][0-9]-*.md` 一并清得掉。
    """
    return section_path.with_name(f"{section_path.stem}.shard-{index}{section_path.suffix}")


def shard_paths(section_path: Path, count: int) -> list[Path]:
    return [shard_path(section_path, i) for i in range(1, count + 1)]


#: 限定词与节级上限。**生产与验收共用这一份**——验收尺子 `check_polished.hedge_density`
#: 直接 import 它，同 `run.MACHINE_TALK_PATTERNS` / `run.singlesource_advice` 的办法。
#: 同一个概念两处两个定义是本项目现形过的一种假绿。
#: 立法理由见 `writing-rules.md §5.1`：实测一份两万字的竞品稿里免责话术出现 40 次，
#: 读者读到第三遍就开始跳过——**免责说满了，等于一句也没说**。
HEDGE_WORDS: tuple[str, ...] = ("单源", "不能外推", "待核实", "不足以")
HEDGE_PER_SECTION = 2

#: 不是散文的段落开头：标题、表格、引用块、表注、代码。限定归并只动散文段——
#: 原声引用块是**发帖人说的话**，程序一个字都不许动。
_NOT_PROSE = ("#", "|", ">", "*", "-", "`", "n=", "（", "(")
_PARAGRAPHS = re.compile(r"\n\s*\n")


def hedge_count(text: str) -> int:
    """一段文字里限定词出现的**次数**。与尺子 `hedge_density` 同一口径：数词次，不数句数。"""
    return sum(text.count(word) for word in HEDGE_WORDS)


def _is_closing_hedge(paragraph: str) -> bool:
    """这一段是不是「反证或限定」那一步写出来的收尾段：散文，且带限定词。"""
    return not paragraph.lstrip().startswith(_NOT_PROSE) and hedge_count(paragraph) > 0


def fold_repeated_hedges(bodies: Sequence[str],
                         limit: int = HEDGE_PER_SECTION) -> list[str]:
    """把跨片重复的「反证或限定」收尾段收掉，收到节上限为止。

    **收的是第二遍第三遍，第一遍原样留着。** 从最后一片往前收，所以留下的一般是节内
    第一处——第一遍已经把话说到了。（后面那些都被守卫挡住时，也会退回来收前面的；
    守卫保的是角标，不是「收不动就放弃」。）09-16 真稿里那 4 处有 3 处说的是同一件事
    （「只有单条 C 级信号，不能外推为普遍」），而那是**整份样本的属性**、不是某一条
    发现的属性，程序早已在摘要末尾那句把握度里说过一次（`run.confidence_line`）。

    ⛔ 与「不许靠删限定句压篇幅」不冲突：那条禁的是**写手为了压字数删限定**；
    这里既不为压字数（篇幅本来就偏短，见货 2），也不动片文件——收只发生在合并出来的
    那一份节正文上，写手交的片在盘上一个字不改，要复盘随时看得到。

    只收**各片最后一段**，三条守卫：
    - 整片只有一段的不收（这条发现会被掏空）；
    - 不是散文的不收（表格、原声引用块）；
    - 这一段里的角标若在别处一次都不再出现，不收——信息源清单只列正文实引过的角标
      （`run.assemble` 的 `cited`），收掉最后一处等于把一条源从清单里抹了。
      收不动就如实留着，⛔ 不硬收。
    """
    blocks = [_PARAGRAPHS.split(body.strip()) for body in bodies]
    total = sum(hedge_count(p) for block in blocks for p in block)
    out = [body.strip() for body in bodies]
    if total <= limit:
        # 没超就一个字节都不动：分片往返「逐字节相同」那条判据架在这条路上。
        return out
    for index in range(len(blocks) - 1, -1, -1):
        if total <= limit:
            break
        block = blocks[index]
        if len(block) < 2 or not _is_closing_hedge(block[-1]):
            continue
        tail = block[-1]
        rest = "\n\n".join(p for i, other in enumerate(blocks) for p in other
                           if not (i == index and p is tail))
        if not set(_MARK.findall(tail)) <= set(_MARK.findall(rest)):
            continue
        block.pop()
        total -= hedge_count(tail)
        # 按原文尾部切，不重排段落——剩下那部分逐字节保持原样。
        head = out[index].rstrip()
        out[index] = head[:head.rfind(tail)].rstrip()
    return out


def merge_shards(paths: Sequence[Path]) -> str:
    """按片序拼接片正文，顺带把跨片重复的限定收尾段收掉。片间一个空行，
    与写手在整节里写出来的形状一致。

    真稿验过逐字节往返：把 09-06 那份 8 432 B 的「关键发现」按二级标题切成 4 份再合，
    与原文一模一样（`tests/test_shard1_polish_shards.py`）。限定没超节上限时
    `fold_repeated_hedges` 原样返回，那条往返判据照旧成立。
    """
    bodies = fold_repeated_hedges(
        [path.read_text(encoding="utf-8").strip() for path in paths])
    return "\n\n".join(body for body in bodies if body)
