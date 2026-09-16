# §D-073 worklog · 代表性尺子 0/803 从未触发

- worktree：`../Owli-d073`，分支 `d073-representativeness-restale`，base `80535d7`
- python：`../Owli/.venv/bin/python`
- 提货单：`docs/handoff/d-073-representativeness-never-fires.md`
- ⛔ 未 push、未合 main、未写 8980 正式库、未重启任何留服端口、未起整跑或补采。
- 库上判据全部在 **backup API 取的副本**上做（`var/d073/` 下，gitignored）。

## 行号重定位

提货单给的 `1272–1283` 是按旧版 `9daa5ce`。在 `80535d7` 上实际是
`app/reliability/backfill.py:1265–1285`（`restale` 集合在 1261–1264，
`targets` 推导式在 1265–1285，出错的 `and` 在 1272–1273）。

## 货 1 · 布尔结构（commit `2c80ce8`）

```
旧： if force or ( not _already_agent_rated(item) and ( … or id in restale ) )
新： if force or id in restale or ( not _already_agent_rated(item) and ( … ) )
```

`restale` 自己已经带着两条闸——`id in percentiles`（有分位）与
`_wants_representativeness`（是 UGC、不是内容农场、理由还是「权威」写法），
所以提到外侧不会把别的行卷进来。L1280–1281 的旧注释写的意图与代码正相反。

## 货 2 · 三条用例（commit `a627cd1`）

`tests/test_d073_representativeness_restale.py`。夹具：一池 21 条小红书
（20 条旧写法 + 1 条已按代表性评过）+ 1 条独苗微博（池 < 20 条出不了分位）。

| 用例 | base `80535d7` | 货 1 之后 |
|---|---|---|
| ① 评级章打过分的 UGC 行必须进重评 | 红：`20 条旧写法的行该全进 targets，实到 0` | 绿 |
| ② 已按代表性评过的行不重复重评 | 红：`旧写法的行没被重评，这条防抖动断言量不出东西` | 绿 |
| ③ 没有分位的行不进重评 | 绿（防回归） | 绿 |

红侧原文读过：① 打出 `BackfillResult(… attempted=0, rated=0 …)`，就是真跑里
「755 条 restale 一条没进」的同一件事，不是夹具塌了。② 的红是我特意加的
「这一轮必须真的动过东西」那条——整轮空转会让防抖动断言变成假绿。

夹具自身先坏过一次（`ev-fresh` 的 `代表性2` 理由配了 `score_authority=0`，
被 dao 的 `rating_notes 分数与五维列不一致` 挡下）；那是我写错夹具，不是缺陷。
改完用最终版夹具在 base 上**重跑了一次**确认红侧仍是上表两条。

## ⚠️ 只修布尔会在真实语料上造成回归 —— 货 3

副本上跑收尾回填（非 `--rescore-only`），只有货 1 时：

```
[fixed] attempted=755 rated=755 failed=0 engine_calls=0
BEFORE {代表性: 0, 权威: 803, B级: 33, B级_UGC: 29}
AFTER  {代表性: 755, 权威: 48, B级:  5, B级_UGC:  1}
grade  BEFORE {A:19, B:33, C:389, D:362} → AFTER {A:3, B:5, C:18, D:22, NULL:755}
```

代表性确实落库 755 条，**但 755 行的 `score_crossref` 与 `grade` 一起变成 NULL**。

根因：`r-20271e8a5028` 的 `reports.extra.claims` 是 **0 条**，803 行
`evidence.extra` 里一个 `crossref_verdict` / `claim_ids` 都没有——那条
`交叉0:单条个人吐槽` 是**评级章**（`audit.py`）直接写的。而整条重算路
（`_scored_payloads` 里 `freeze_others=False`）要 `extra` 里有血缘簇才给交叉维
打分，没有就判「缺断言血缘簇」写 NULL。旧代码把这批行挡在 targets 外，
反而保住了它们的交叉维；货 1 一放进来就抹掉了。引用池 `user_opinion` 的 B 级
行数 29 → 1，**比病还重**。

### 货 3 修法（commit `06c3645`，范围变更，已呈拍）

只为换第一维尺子而入选的行（`restale` 且不满足「没评全」），其余四维连分带理由
原样送回——口径与 `--rescore-only` 完全同一条（用户 09-05 对 §RATE-4 拍的甲）。
实现是把 `reusable` 按 `ruler_swap_only` 切两半，`freeze_others` 分别给 True / False；
`_needs_full_backfill()` 抽成具名函数，判据一个字没改，只是被引用了两处。
⛔ 没动评分口径，也没动 RATE-4 代表性算法本身。

副本读数：

```
[swap] attempted=755 rated=755 failed=0 engine_calls=0
BEFORE {代表性: 0, 权威: 803, B级: 33, B级_UGC: 29}
AFTER  {代表性: 755, 权威: 48, B级: 80, B级_UGC: 76}
grade  BEFORE {A:19, B:33, C:389, D:362} → AFTER {A:16, B:80, C:388, D:319}
被改的行 755；后四维分漂移 0/0/0/0；后四段理由逐字漂移 0
第一维 升 233 / 降 43 / 平 479
```

第 4 条用例锁住它，夹具照真实语料的形状造（`extra` 里没有 `crossref_verdict`）。
红侧（货 1+2 那两个 commit 上）：`ev-s000 交叉维被重算路抹成 None`。

## ⚠️ 提货单的库上判据是假绿尺子

提货单判据 2 写的是「在副本上跑 `--rescore-only`，代表性 0 → ≥700」。
**这把尺子量不出这个包**：`rescore_only` 那条分支的 targets 是
`_stored_labels(...) is not None`，**根本不看 `restale`**，D-073 的布尔结构在
这条路上一行都走不到。实测在 **base `80535d7`（没修）** 上跑：

```
[base-rescore] attempted=803 rated=755 failed=0
AFTER {代表性: 755, 权威: 48, B级: 80, B级_UGC: 76}
```

没修也是 0 → 755、B级_UGC 29 → 76，两条判据全过。

能分辨的尺子是**收尾回填那条路**（`rescore_only=False`），同一份副本：

| 代码 | attempted | 代表性 | B级_UGC | grade NULL |
|---|---|---|---|---|
| base `80535d7`（没修） | **0** | 0 | 29 | 0 |
| 货 1（只改布尔） | 755 | 755 | 1 | **755** |
| 货 1+3 | 755 | **755** | **76** | 0 |

记进「验收尺子自己也要验」「假绿：判据落在『存在』上」两条。

## pytest

```
2186 passed, 3 skipped in 32.23s
exit=0
```

基线 2183 + 本包 3 条（货 2）→ 2186；货 3 那条是第 4 条，在同一次全量里。
（落盘文件 `/tmp/d073_full_swap.txt`，`echo exit=$?` 单独一行，没走管道，
没用 `-q -q`。）

## 硬线自查

- 未 push、未合 main、未碰 `../Owli-wx1` 的库与 runs（只 `mode=ro` 打开 + backup API 取快照）
- 未写 8980 正式库；未重启或停 8969 / 8975 / 8976 / 8979 / 8980
- 未碰禁区：`app/store/`、`migrations`、`app/sources/`、`app/adapters/`、
  `app/reliability/crossref`、`app/reliability/ratelimit`、`app/replay/`、`app/config.py`
- 未碰 `app/report/polish/`（§RPT-5 并行在改）
- 未起整跑或补采：所有引擎调用数实测 `engine_calls=0`
- 改动只在 `app/reliability/backfill.py` + `tests/test_d073_*.py` + 本 worklog
