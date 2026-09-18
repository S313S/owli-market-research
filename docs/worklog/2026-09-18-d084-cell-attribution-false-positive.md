# §D-084 工作日志 · 判据 ⑮ 把「不再只是 X，而是 Y」误判成给 X 那一格归因

worktree `../Owli-d084`，分支 `d084-cell-attribution-form`，签 **a21a1b5**。
解释器 `../Owli/.venv/bin/python`。零引擎、不写库、不出稿、不重跑正式稿。

## 〇、先核「同一概念有没有第二份定义」（提货单一.4）

用 `grep -rn "ATTRIBUTION_WORDS|check_cell_attribution|attitude_by_topic"` 扫全仓：

- `ATTRIBUTION_WORDS` / `check_cell_attribution` **只在** `scripts/acceptance/rpt1/check_polished.py`
  出现，`app/` 下一处都没有。
- `app/` 侧同一概念的落点是**提示词**，不是代码闸：
  `app/skills/report-polish/_shared/writing-rules.md` §5.9「编码表的某一格，只能用这一格
  自己的证据解释」，两条规矩（只引格内角标 / 覆盖不到三分之一就只写条数）与判据 ⑮ 一一对应。
- `app/reliability/coding.py` 只负责**造** `attitude_by_topic` 这张表（条数与 marks），
  不做任何归因判断。

结论：**没有生产侧的第二份定义**，不需要动 `app/`，也不构成「碰禁区」。
提示词那一份是自然语言规矩、由写手执行，本包不动它——它说的正是判据要守的那件事，
而这次要修的是尺子把「被否定掉的那半句」错当成主张。

## 一、修前读数（base a21a1b5，原样命令）

```
../Owli/.venv/bin/python scripts/acceptance/rpt1/check_polished.py \
  ../Owli-src5/var/runs/r-3b3482ca7f8b/exports/r-3b3482ca7f8b.polished.consulting.md \
  ../Owli-src5/var/runs/r-3b3482ca7f8b/exports/r-3b3482ca7f8b.polished.consulting.tables.json \
  var/d084/working.json
```

工作稿：`curl --noproxy '*' -s http://127.0.0.1:8981/api/researches/r-3b3482ca7f8b/report`
（HTTP 200、98964 B，落 `var/d084/working.json`，只读、未动服务）。

落盘 `var/d084/check_before.txt`：**EXIT=1，16 PASS / 1 FAIL**，唯一的红是

> FAIL ⑮ 归因只引该格内的角标（1 处）
> · 第 35 行在给「回答质量」这一格归因，但这一格 20 条里只有 4 条进了引用池——
>   只准写「20 条，本轮未进引用」：这张表说明，豆包的媒体参照系已经变化：衡量它的
>   不再只是回答质量或模型强弱，而是能

**读原文确认红的是这件事**（`writer_text` 第 35 行原话）：

> 这张表说明，豆包的媒体参照系已经变化：衡量它的不再只是回答质量或模型强弱，
> 而是能否接住一项完整工作。豆包与千问办公同档，……

「回答质量」是「不再只是 X，而是 Y」里**被否定掉的 X**；整段讲的是媒体定位表
（表下角标 `[S01][S10]` 正是这张表自己的），没有一个字在解释「回答质量」这一格的
编码语义。词面撞上 `而是` + 主题名就判红——与 §D-083「顺口提一句被当成结构信号」同族。

真机那一格的读数（tables.json）：回答质量 正 12（S19/S36）、负 5（无）、
混合 2（S05/S06）、中 1（无）= 20 条 / 4 条带角标，4 < 20×1/3，所以踩的是第一支。

## 二、货 2（先造红）：四条用例，两侧都在 base 上量过

写在 `tests/test_rule1_content_rules.py`（§RULE-1 货 6 那一段之后），**先于修改提交**，
这样「尺子原本管得住」有独立证据，不是修完回头补的。

| 用例 | 喂什么 | 期望 | base a21a1b5 实测 |
| --- | --- | --- | --- |
| ① `test_a_topic_only_in_the_negated_half_is_not_attribution` | 真机第 35 行原话（`REAL_NEGATED_HALF`），格夹具照真机 20 条 / 4 marks | 不判红 | **FAILED**（就是要修掉的假红，红文与真机同形：「这一格 20 条里只有 2 条进了引用池」） |
| ② `test_the_0907_symptom_stays_red` | 「价格与付费 19 条负向，其实是嫌豆包太便宜[S02]」，格内 19 条只 1 条进池 | 判红「未进引用」 | PASSED（红） |
| ③ `test_a_negated_topic_that_still_names_the_cell_stays_red` | 「这 19 条负向说的并非价格与付费太贵，而是嫌豆包收费变了[S02]」——主题名挪进否定句，但句里还念着这一格的条数与态度 | 判红「未进引用」 | PASSED（红） |
| ④ `test_the_asserted_half_after_the_pivot_is_still_judged` | 「用户抱怨的不是速度与稳定，而是价格与付费在变着法涨价[S99]」——`而是` 右边的主题名 + 别格角标 | 判红「不在这一格」（第二支） | PASSED（红） |

③ 是本包最要紧的护栏：它把「豁免会不会被写手用一句否定句绕过去」这条路堵死。
④ 同时锁住两件事——被否定的只有左半句，以及第二支（引了别格角标）没被修哑。
回归锁：`test_rule1_content_rules.py` 原有 35 条用例一条不改，其中
`test_attribution_on_a_cell_with_thin_citation_is_red`、
`test_attribution_citing_a_mark_outside_the_cell_is_red`、
`test_stating_the_count_without_attributing_passes`、
`test_the_gate_is_silent_without_a_coding_table` 正是 ⑮ 的现有真红/真绿样本。

原样命令与落盘：

```
../Owli/.venv/bin/python -m pytest tests/test_rule1_content_rules.py \
  -k "negated or 0907 or pivot or asserted_half" -v --no-header   # → var/d084/newtests_on_base.txt
```
读数：`1 failed, 3 passed, 35 deselected`，EXIT=1。

## 三、货 1：收紧触发条件

改 `scripts/acceptance/rpt1/check_polished.py`，两处：

1. 新增 `NEGATED_HALF`：从否定词（`不再只是 / 不再是 / 不只是 / 不仅（仅）是 / 并非 /
   并不是 / 不是` …）起，到 `而是 / 而非 / 而在于` 或逗号止，切出「被否定掉的那半句」。
   跨度**到 `而是` 为止**，所以右半句（这句真正主张的那一半）里的主题名照旧要管。
2. `_cell_attribution_problems` 里加一道闸：**主题名只出现在被否定的那半句里**，
   并且句子**再没有别的东西把它钉在这一格上**时，才跳过。

「钉在这一格上」= 句里写了正/负向等态度词（`wanted` 非空）、或引了**这一格自己的**角标、
或念出了这一格的条数。三样有一样就照旧判红。

⛔ 这**不是**「有角标就放行」——恰好相反：带这一格的角标反而让豁免失效。
⛔ 也不是整体放宽：`ATTRIBUTION_WORDS`、`CELL_MARK_COVERAGE`、两支判词一个字没动，
豁免只在「主题名全部落在被否定的那半句、且句子没有任何一处指向这一格」时生效。

代码原样（`scripts/acceptance/rpt1/check_polished.py`）：

```python
NEGATED_HALF = re.compile(
    r"(?:不再只是|不再仅仅是|不再仅是|不再是|不只是|不仅仅是|不仅是|"
    r"并非只是|并非|并不是|不是)"
    r"(?:(?!而是|而非|而在于)[^，,])*")
```

抠掉这些跨度后主题名还在不在，决定它是不是「被否定掉的那一半」——替换成全角空格
而不是删掉，免得抠完把两截拼出一个原本不存在的主题名。

## 四、修后读数

| 判据 | 命令 | 读数 |
| --- | --- | --- |
| 判据 1 新用例 | `pytest tests/test_rule1_content_rules.py -v` | **39 passed / EXIT=0**（4 新 + 35 旧全绿，`var/d084/newtests_after.txt`）——① 由红转绿，②③④ 仍红 |
| 判据 2 全量 | `pytest tests/ -q`（落盘看 `$?`，⛔ 不走管道） | **2258 passed / 3 skipped / EXIT=0**（基线 2254/3，+4 恰是新用例，`var/d084/pytest_full.txt`） |
| 判据 3 真稿 | 见第一节原样命令 | 修前 EXIT=1 / 16 PASS 1 FAIL → 修后 **17 PASS / EXIT=0**（`var/d084/check_after.txt`） |

判据 3 的 `diff var/d084/check_before.txt var/d084/check_after.txt` 只有三处：
⑮ 那两行 FAIL→PASS、末行 `× 未过…`→`√ 17 条判据全过`、`EXIT=1`→`EXIT=0`。
**①–⑭、⑯⑰ 与 ⒜–⒡ 六条软检一行未变**——没有顺手动到别的判据。

## 五、自补的回归扫（用户没要求，是本包自加的护栏）

把 base 版与修后版的 `check_cell_attribution` 同时加载，喂全机器上**所有**能配对的
真机正式稿（`*/exports/*.polished.*.md` + 同名 tables.json，跳过禁区 `../Owli-wx1`），
逐条比对两侧报出来的问题列表。落盘 `var/d084/sweep_48_samples.txt`：

```
样本总数=48 行为不变=47 行为有变=1
```

唯一变的就是要修的那一处（r-3b3482ca7f8b × consulting 第 35 行）。
48 份历史真稿里没有第二处被放过——豁免面确实只有「被否定掉的那半句」这么宽。
（只读，未改任何 runs / 快照。）

## 六、挂账与自拍

- 挂账 1：豁免按**词面否定式**认，认的是 `不再只是 / 并非 / 不是…` 这一族。写手若用
  「与其说是回答质量，不如说是……」这类没被收进表的说法，判据仍会判红（假红形态不变）。
  真机 48 份稿里一例都没出现，本包不扩表——扩表就是在没有病象的地方放宽尺子。
- 挂账 2：「主题名落在否定句里、句里也没有条数/态度词/该格角标，但用代词回指这一格」
  （如「这 19 条并非在夸它，而是在骂它贵」——「它」指上一句的格）这种写法豁免会放过。
  词面尺子做不到代词消解；已用条数与态度词两道钉子把最常见的形态钉住（用例 ③）。
- 自拍（本包自己拍的，未上呈）：不动 `app/`（核出没有第二份定义，提示词那份是自然
  语言规矩、说的正是判据要守的事）；豁免条件里加「句子仍指向这一格就照旧判」这道
  反向闸（提货单给的两条可选思路只要满足其一，这里两条合起来用，比任一条都更紧）；
  自加第五节的 48 份真稿回归扫。
- ⛔ 全程零引擎、未写库、未出稿、未重跑正式稿、未动任何端口（8981 只发了一次
  只读 GET 取工作稿）。
