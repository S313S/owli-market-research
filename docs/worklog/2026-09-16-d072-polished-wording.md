# §D-072 worklog · 正式稿内部词 + 摘要态度行插入点

- worktree：`../Owli-d072`，分支 `d072-polished-wording`，base `768c2b5`
- python：`../Owli/.venv/bin/python`
- 提货单：`docs/handoff/d-072-polished-internal-word-and-attitude-line.md`
- ⛔ 本包不重出正式稿、不重启 8980，未 push、未合 main。

## 货 1 · 各表口径去掉内部角色名（`app/reliability/coding.py`）

`coding_tables()` 的 `method_note` 是写死文案，原样进客户正式稿的附录「各表口径」。

- 旧：`模型编码（v2），包终端复核 30 条一致 28 条；表内均为条数，不是全网比例。`
- 新：`模型编码（v2），另抽 30 条复核、28 条与模型判读一致；表内均为条数，不是全网比例。`

改的只是「谁复核的」这半句。**复核读数 30 / 28 一个数字没动**——那是 v2 词表的真实
复核读数，改数字＝造假。`tests/test_code1_tables.py` 的断言从「`包终端复核` in note」
换成两头都锁：内部角色词一个都不许在、`30 条` 与 `28 条` 必须在。旧断言锁的正是
被替换掉的那一版措辞（参照「既有用例会锁住旧语义」），不是改尺子作弊。

commit `d03328d`。

## 货 2 · 尺子 ① 补收内部角色词（`scripts/acceptance/rpt1/check_polished.py`）

`FORBIDDEN` 此前只收了切块词（`goal-` / `sec-` / `ch-` / 本片 / 本节样本）与
表名 / 字段名 / 代码路径 / 抓取时间，**内部角色名一条都没收**——这才是病象 1 能
17 条判据全过还出厂的原因（假绿：判据落在「收了一批词」上，没落在「这一类词收没收」上）。

补收五个：`包终端` / `调度会话` / `提货单` / `奏折` / `哨兵`。条目数 23 → 28。

### 造红 / 复绿两侧读数

底料：`../Owli-wx1/var/runs/r-20271e8a5028/exports/r-20271e8a5028.polished.consulting.md`
（**只读**，未改动、未重出）。判据 ① = `check_no_internal_words()`。

| 尺子 | 稿 | 判据 ① 命中数 |
|---|---|---|
| 旧尺子（HEAD:768c2b5） | 旧稿 | **0**（假绿） |
| 新尺子 | 旧稿 | **1** —— 第 187 行命中内部词 `'包终端'` |
| 新尺子 | 货 1 修后文案 | **0**（复绿） |

第 187 行原文（节选）：
`| UGC 逐条编码：主题 × 态度条数 | …对 1 条引用池里的评论逐条模型编码后计数（模型编码（v2），包终端复核 30 条一致 28 条；…`

复绿用的「修后文案」= 拿修后 `coding.py` 真实产出的那句，替换旧稿里的旧串
（旧串在旧稿中出现 **1** 次），落 `/tmp/d072_fixed_polished.md`。⛔ 没有重出正式稿。

用例锁在 `tests/test_shard1_polish_shards.py`，**复用**该文件已有的 `_internal_word_hits()`
（那个 helper 本来就是「复用尺子①那份词表，不另造一份」），两头都锁：
旧措辞必须被抓 == `["包终端"]`、`coding_tables()` 现在产出的口径句必须干净且保留 30/28。

commit `1224058`。

## 货 3 · 态度行插入点改锚关键发现列表（`app/report/polish/run.py`）

**真因**：`_inject_before_confidence()` 只认**引用块**里的把握度
（`text.lstrip().startswith(">") and "把握度" in text`）。写手常把把握度写成普通段落
——r-20271e8a5028 咨询体稿就是普通段落——于是匹配失灵，走 `hit is None` 的兜底
`body.rstrip() + "\n\n" + line`，把态度行扔到**节末**，也就是落在把握度句之后。
RATE-5 报的「把握度句不是引用块，插入点匹配失败」说的就是这一步。

**修法**：新 `_inject_after_findings()`，锚**关键发现编号列表**，不锚把握度句的形态。
态度行回答的是「整体正多还是负多」，读者读完那 3–5 条发现正想问这个。

- 列表定位**复用** `sharding.FINDING_LINE`（把原 `_FINDING_LINE` 转正）——切片数片
  按的就是它；两处各写一份正则，写手换个写法会一处跟得上一处跟不上。
- 折行容错：跨过紧跟其后的非空续行（markdown 惰性续行），但撞到把握度那行就停，
  免得把态度行插进某条发现中间、或反而又跑到把握度后面去。
- 两级兜底都是老行为，不是新失败：读不出发现列表 → 退回「把握度之前」
  （这一级由新 `_confidence_index()` 认词不认 `>`，否则老病象换个入口原地复发）；
  再找不到 → 接节末。

### 尺子自己也验过（「验收尺子自己也要验」）

新增三条用例，**先在老代码上真红过一次**（临时把老插入点装回，跑完还原）：

| 用例 | 老代码 | 新代码 |
|---|---|---|
| 把握度句是普通段落 | FAIL「态度行没紧跟发现列表」 | PASS |
| 把握度句缺席 | FAIL「态度行没紧跟发现列表」 | PASS |
| 没有发现列表（兜底级） | FAIL `IndexError`（行落到了节末，后面没有行了） | PASS |

提货单要的「把握度句在场 / 缺席两种形态各一条」是前两条，第三条是兜底级自补。

commit `2f40b51`。

## pytest

```
../Owli/.venv/bin/python -m pytest -q > /tmp/d072_pytest_full.txt 2>&1; echo exit=$?
exit=0
2165 passed, 3 skipped in 32.32s
```

基线 2161 passed / 3 skipped → **2165 / 3**，+4 正是本包新增的四条用例（货 2 一条、货 3 三条）。
⛔ 全程未用 `| tail` 吞退出码（落盘后另读）。

## commit 列表

| commit | 货 | 路径 |
|---|---|---|
| `d03328d` | 货 1 | `app/reliability/coding.py`、`tests/test_code1_tables.py` |
| `1224058` | 货 2 | `scripts/acceptance/rpt1/check_polished.py`、`tests/test_shard1_polish_shards.py` |
| `2f40b51` | 货 3 | `app/report/polish/run.py`、`app/report/polish/sharding.py`、`tests/test_rpt4_client_lens.py` |

## 挂账 / 呈调度的观察（本包**未动**）

1. **`_inject_after_confidence()` 还是只认 `>`**。它管的是把「主张 N 条 …」那行插在
   把握度之后，走的是同一条失灵路：把握度写成普通段落时，它同样匹配失败、
   把主张行扔到节末。在 r-20271e8a5028 咨询体稿上，`confidence_line()` 这轮返回空
   （没 crossref 读数），所以病象没显形——但路是同一条，换一份有交叉验证读数的稿
   就会显形。本包只改态度行（提货单货 3 的范围），动它属**范围变更**，留给调度拍。
2. 货 1 / 货 3 都是**下一次出稿才生效**的改动。现有那份 09-15 正式稿里的病象 1、3
   仍在原样，按提货单 ⛔ 不重出正式稿，等编码范围（态度行 n=1）那条拍完一次做完。
3. 顺带量到：那份稿的态度行是「已编码评论 **1** 条」——`scenario_attitude` 的 n=1。
   这正是提货单里押后的 ② 要拍的那件事，本包不碰。
