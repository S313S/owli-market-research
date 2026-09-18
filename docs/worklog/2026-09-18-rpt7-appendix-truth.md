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
