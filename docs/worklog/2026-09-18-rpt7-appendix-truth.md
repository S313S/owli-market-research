# §RPT-7 worklog · 附录「哪些没采到」把没丢的和非采集工序都算了进去

- base `ed1e9f7`（本地 main），worktree `../Owli-rpt7`，分支 `rpt7-appendix-truth`。
- 解释器 `../Owli/.venv/bin/python`。
- 基线：`pytest tests/` **2258 passed / 3 skipped / EXIT=0**；
  已交用户那份稿（`../Owli-src5/.../r-3b3482ca7f8b.polished.consulting.md`）
  `check_polished` **17 PASS EXIT=0**，⒜–⒡ 六条软检全 OK（0 处）。
  落盘：`var/rpt7/pytest-base.txt`、`var/rpt7/check-baseline-shipped.txt`。

## 货 1 · 缺失表分类（一张表拆成三张）

**造红**：`tests/test_rpt7_appendix_truth.py` 在 base 上 5 红 3 绿
（`var/rpt7/red-h1.txt`）。读红出来的原文，红的正是这件事：

```
AssertionError: assert 5 == 1
 +  where 5 = len(['| hn（豆包） | 采到 7 条，已入库并参与评级与统计；…但内容本身没丢 |',
                   '| producthunt（豆包） | …确实没有相关内容 |',
                   '| 一致性检查（豆包…） | 这一段采集超时没跑完 |',
                   '| 标签（DeepSeek…） | 这一段重试用尽仍未成功 |',
                   '| 标签（Kimi…） | 这一段采集超时没跑完 |'])
KeyError: '## 采到了但没写成段落'
KeyError: '## 哪些环节没跑完'
```

**改法**：`missing_table` 按**账本查得到的两件事**分流，⛔ 不按章名猜——
`yielded > 0` → `COLLECTED_HEADING`；`chapter_type != collection` → `PROCESS_HEADING`；
其余留在 `MISSING_HEADING`。非采集章另走一套理由码 `_PROCESS_REASON`，
一个「采集」字都不带。对不上章的行（源对账那路 `chapter_id=source/<平台>`）章型未知，
仍留在原表不猜。两个新标题登记进 `PROGRAM_APPENDIX_HEADINGS`——
`check_polished.writer_body` 按它剜程序块，漏登记就会把程序表当成写手正文量篇幅。

**两个新节的标题（调度让自己拍，理由记这里）**：

| 调度暂定 | 本包拍的 | 为什么改 |
|---|---|---|
| `## 采到了但没写进正文` | `## 采到了但没写成段落` | HN 那一行 `cited=2`（S38 在正文真被引），「没写进正文」对它就是假话——和货 3 ① 要堵的是同一类假话。缺的确实只有「没写成一段」。 |
| `## 哪些工序没跑完` | `## 哪些环节没跑完` | 「工序」是制造业的词，客户未必立刻对上号；而且这一节除了内部处理步骤，还会收「报告·第 N 节」这种没写成的撰写章（`chapter_type=report/comparison` 也是非采集章），「环节」两头都罩得住。 |

**既有用例**：`tests/test_d060_missing_table.py` 四条红。它们的 `_lines()` 把
三张表的行拉平了按下标断言——锁的正是被替换掉的那条语义（一张表装三件事），
不是「改尺子作弊」。改法是加 `_rows_of(md, heading)` 按表取行，
每条断言的**字面一个字没动**，只是换成在它该在的那张表里找。

**读数**：`pytest tests/` **2266 passed / 3 skipped / EXIT=0**（`var/rpt7/pytest-h1b.txt`）。

## 货 2 · 章型标签（不许把内部工序名印给客户）

**造红**：新增四条，在货 1 的树上（`_chapter_label` 与 base 逐字相同）4 红。红出来的原文：

```
AssertionError: ['Product Hunt（豆包）', 'Hacker News（豆包）',
                 '一致性检查（豆包在国内用户与媒体中的口碑画像）',
                 '标签（DeepSeek 在国内用户与媒体中的口碑画像）',
                 '标签（Kimi 在国内用户与媒体中的口碑画像）']
AssertionError: ['audit', 'code_execution', 'comparison', 'cross_validation',
                 'data_cleaning', 'excel_generation', …]      # 闭集里一个都没客户说法
AssertionError: 标签（Kimi 在国内用户与媒体中的口碑画像）       # 章型未知也照漏
AssertionError: '报告撰写（豆包与四款对手的横向对比与观点综合）' == '「…」的报告·第 1 节（…）'
```

**改法**：`_chapter_label` 的兜底从「`display_name`（目标名）」换成
按 `chapter_type` 取 `_CHAPTER_TYPE_LABEL`，认不出就退 `中间处理步骤`，
⛔ 一律不再退回 `display_name`——内部工序名就是从那儿漏出去的。

⛔ **不编库里没有的含义**，逐条对过：
- `tagging` → 「给采到的内容打主题标签」：真机 goal-2/ch-4 的 task 原文就是
  「对清洗后的 DeepSeek 语料按…四个主题维度打标签」。
- `audit` → 「证据的质量核查」：这一个章型下挂着两种活（`可靠度审计` 给证据评级、
  `一致性检查` 查同源矛盾/时间线冲突），所以只能写两者都成立的那一句，⛔ 不挑一种写死。
- `transport` → 走兜底：它是闭集成员，但 `_KIND_CHAPTER_TYPES` 里没有任何一种
  agent kind 排得出它，编不出它干什么就不编。
- `comparison` 归撰写章（与 `report` 同一支）：真机 goal-6/ch-4 的 `display_name`
  是「报告撰写」而章型记的是 `comparison`，它是稿子的一节，不是一道处理步骤。

**判红的量法**：量的是**第一格的字面**（`标签（` / `一致性检查` 开头），
⛔ 不量整段是否出现「标签」二字——「给采到的内容打主题标签」是在说这一步干什么，
不是把工序名甩给客户；那样量会把修好的写法也判红。

**读数**：`pytest tests/` **2270 passed / 3 skipped / EXIT=0`（`var/rpt7/pytest-h2b.txt`）。

## 货 3 · 两处假话闸

**造红**（在货 2 的树上，`_yielded_tail` 与 `basis_table` 都还是 base 那一版）4 红：

```
assert '正文未能引用它们' not in
  '| Hacker News（豆包） | 采到 7 条，已入库并参与评级与统计；这一段的总结超时没写成，正文未能引用它们 |'
assert '⛔' not in '## 各表口径\n…C 级只作旁证，正文引它时出处行必须写「等级 C」…'
assert ('v1' not in md and 'v2' not in md)
assert '⛔' not in '## 代表原声（逐字摘录，按互动量排序）…'
```

### ① 有角标进了正文就不许写「正文未能引用它们」

`_YIELDED_TAIL["timeout"]` 写死那半句，而 `chapter_rows` 早就算好了 `cited`。
真机 HN 那一章 `yielded=7 / cited=2`（S38 在正文真被引），只因死因记的是
`tool_unavailable` 才侥幸没走到这一支——**换个死因这句就是假话**。
闸落在 `cited > 0` 上（账本查得到的事实），不落在死因上。`cited=0` 的那一支
§D-060 的原话一个字没动。

**既有用例**：`test_rpt6_length_and_hedging::_why` 的夹具写的是 `cited=yielded`
——顺手写的，不是本项目的事实（HN 7 条入库、只有 2 条进池）。拆成两个参数，
默认 `cited=0`，那条「措辞一字不改」的断言字面未动。
`test_d060::test_new_wording_says_collected_but_timed_out` 的小红书那一行
`cited=12`，按新语义走不认领死因的那句；Reddit（`cited=0`）逐字不变。

### ② 「各表口径」不许把给写手的指令与内部版本号漏给客户

口径句是**两用**的：同一段字既进写手提示词（`build_prompt` 把 `tables[*]`
除 `name` 外整块塞过去，那里它是护栏），又原样印进客户稿的「各表口径」。
⇒ **只在呈现层改**，`tables[*].basis` 一个字不动
（`test_quote1_zero_engagement.py:66` 正锁着那句原文，改源等于拆写手的护栏；
本包另加一条用例锁「源没被改」）。

改法：`client_voice()` 逐句把指令改成陈述句 + 削内部版本尾巴 + 兜底删 ⛔ 残句；
`basis_words() = client_voice(plain_words())` 成为附录印口径句的唯一一条路。
⛔ 逐句改写、不做通用改写——口径句里有真实复核数（30/28），机械正则迟早削到数字上。
真机渲染后 `⛔ / v1 / v2` 全消失，`另抽 30 条复核、28 条与模型判读一致` 逐字还在。

**自补（非提货单点名）**：同一段口径句在附录里出现两处——「各表口径」表和
「代表原声 / 词表命中 / 对照实体」三张表的表尾。提货单只点了前者；
但那是**同一段字**，只改一处会出现「同一句话在一份稿里两种形态」，
是本项目现形过的假绿。四处共用 `basis_words`，一处改全处改。

**读数**：`pytest tests/` **2276 passed / 3 skipped / EXIT=0**（`var/rpt7/pytest-h3b.txt`）。

## 货 4 · 原声表表尾的样本量

**造红**（货 3 的树上）2 红：

```
assert '样本量 4 条' in '…| 功能与能力 | 正 | 第 3 句 | [99] |\n\n样本量 6 条｜口径：…'
assert '另有 2 条' in md
```

**病因**：`coding_tables` 出表时 `n=len(data["quotes"])` 数的是**挑出来的 6 条**，
而同一个 `_shell` 的 `rows` 又过了一道「没角标就不进表」的筛（4 行）。
表尾紧挨着行，于是 4 行表底下写着「样本量 6 条」，读者数得出来对不上。

**拍 `rows` 为准，依据**：这张表**一行就是一条样本**（别的附录表不是——词表命中表的
`n` 是证据条数、行是主题，本来就不该相等，所以那几张照旧用 `n`，另有用例锁）。
表尾说的必须是它底下这几行。

**为什么在呈现层改、不去改 `n`**：`n` 同时进写手提示词（`build_prompt` 把
`tables[*]` 整块塞过去），在那边它的语义是「挑出来几条」，是对的；
`coding_tables` 也不在本包可动范围。⇒ 只改附录渲染。

**差额不抹掉**：`n > 行数` 时补一句「另有 N 条入选原声没有可引用的角标，未列入本表」
——只说账本查得到的事实（没有角标），⛔ 不认领挑选逻辑，⛔ 不动 `quotes` 的挑句。
行数与 `n` 相等时这半句不出现（用例锁）。

**读数**：`pytest tests/` **2280 passed / 3 skipped / EXIT=0**（`var/rpt7/pytest-h4b.txt`）。

## 复验（判据 2 / 3）：零引擎重组装

新脚本 `scripts/acceptance/rpt7/reassemble.py`：只读写手分节产物 + 上一轮
`polish()` 自己落的 `*.tables.json` + 工作稿，**只重跑 `assemble`**。
⛔ 不重跑写手、不连库、不写 `../Owli-src5`（附录块那一串与 `run.polish()` 里逐字同序，
少一块或换个序量出来的就不是生产会出的那份稿）。

**先验尺子**（自造脚本造过七次假数据，量出异常先怀疑尺子）：
把 `run.py` 临时换回 base `ed1e9f7` 跑一遍 → `var/rpt7/before/…md`
与**已经交给用户那一份** `diff` **逐字节相同**（38199 B, IDENTICAL）。
⇒ 这条复验路确实走的是生产那条路。

`before` vs `after` 的 diff **只有四货，没有第五处**（32 行增删）。

| 判据 2 读数 | 结果 |
|---|---|
| HN 那行不再出现在「哪些没采到」 | ✅（该表只剩 Product Hunt 一行） |
| 两个 tagging 章与 audit 章不在采集缺口表、不带「采集」字样 | ✅（整节零「采集」，含说明句） |
| 正文再无「标签」「一致性检查」等内部工序名 | ✅（全稿 `一致性检查` 出现 0 次） |
| 口径表无 ⛔ 指令体、无内部版本号 | ✅（`⛔ / v1 / v2` 全 0），真实复核数「另抽 30 条复核、28 条与模型判读一致」逐字还在 |
| 原声表行数与样本量一致 | ✅ 4 行 ↔「样本量 4 条（另有 2 条…未列入本表）」 |

**判据 3**：`check_polished` 对**重组装后的稿**跑 → **17 PASS、EXIT=0**，
⒜–⒡ 六条软检逐条 `OK`（与基线逐条相同）。落盘 `var/rpt7/check-after.txt`、
基线 `var/rpt7/check-baseline-shipped.txt`。修前修后两份稿都留在
`var/rpt7/before/`、`var/rpt7/after/`。

## 自己拍的三处（提货单授权范围内，记此备查）

1. 两个新节标题（见货 1 表）。
2. 货 3 ② 的 scrub 同时作用于三张表的**表尾**，不只「各表口径」——同一段字，
   只改一处会出现「同一句话在一份稿里两种形态」。
3. 「哪些环节没跑完」的说明句从「这几段不在采集范围内」改成「这几段不去外面取内容」：
   提货单要求这一节**不带「采集」二字**，说明句也是印给客户的字，得一起算。

## 硬线自查

不 push、不合 main；没停/重启任何端口；没删任何库/runs/快照/夹具；
没改凭证与钱闸；没碰 8980 与 `../Owli-wx1`；`../Owli-src5` 只读
（近 2 小时内该树零文件改动，已核）。`git add` 只加自己的路径。
