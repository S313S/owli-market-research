# §D-075 worklog · 交叉验证表恒空：全库主张 0 条

- worktree：`../Owli-d075`，分支 `d075-claims-chain`，base `9bbe8fa`
- python：`../Owli/.venv/bin/python`
- 提货单：`docs/handoff/d-075-claims-chain-empty.md`
- ⛔ 未 push、未合 main、未重出正式稿、未写任何留服库、未重启或停 8969/8975/8976/8979/8980、未起整跑。
- 真机底料全程**只读**：`../Owli-wx1/var/wx1-serve.db` 用 `sqlite3.Connection.backup()` 取快照到
  `var/snap/wx1.db`（⛔ 没用 `cp`，WAL 里 4.3 MB 未回写的内容会漏），
  `../Owli-wx1/var/runs/r-20271e8a5028/` 只读不写。

---

## 货 1 定因：抽取跑了、也没被投影覆盖，是**登记整批退回**

### 结论一句话

1380 条主张全都抽出来了，**其中 1 条**的 evidence 列表里把同一条小红书评论链接写了两遍，
`prepare_claim_registration` 判它违规就**抛错退回整批**，于是 `set_report_claims` 一次都没被调用，
`reports.extra` 里连 `claims` 这个键都不存在。
1 / 1380 的书写冗余，端掉了全部 1380 条。

### 库上读数

| 落点 | 读数 | 怎么量的 |
|---|---|---|
| `reports.extra`（`r-20271e8a5028`）的键 | `plan_generated_at` / `scale` / `llm_usage_offledger` / `exports` 四个，**没有 `claims` 键**，也没有 `claims_dropped` | 快照库 `select extra from reports` |
| `ext_key_registry` 里 `key like '%claim%'` | **0 行** | 快照库 |
| `evidence` 行数 / 其中 `extra.claim_ids` 非空的行数 | 803 / **0** | 快照库 |
| 正式稿 `…polished.consulting.tables.json` 的 `counts.claims` | **0** | 只读 `exports/` |
| 章产物里**实际抽得出**的 claims | **1380 条**，来自 11 份 JSON 章产物，**11/11 都有 `claims` 键** | 用生产函数 `claims_from_documents` 离线重跑 |

`set_report_claims`（`app/store/dao.py:756`）是**无条件** `extra["claims"] = normalized`。
所以「`extra` 里连键都没有」只可能有一个解释：它一次都没被调用。
不是「写了被投影覆盖」——投影要覆盖也得先有键。

### 事件上读数（不是看日志，是 `events` 表）

```
report_validation  verdict=fail
  failures=[{"validator":"claims_registration",
             "message":"断言登记失败，共 1 处",
             "offenders":["claims[732].evidence[2].permalink 在断言内重复"]}]
report_warning     reason=report_validation_failed（同一条 offenders）
claims_keys_stripped   —— 0 条（说明闭集外的键一个都没剥，§FIX-2 那条腿这轮没被走到）
```

`app/orchestrator/runtime.py:3245-3276`：`register_claims` 抛 `ClaimsRegistrationError`
→ 进 `except` 记成 `claims_error` → 只往 `failures` 里加一行，**库一个字没写**。

### 离线复现（生产函数原样调用，不自造尺子）

拿快照库里的 `plan_snapshot` 还原 `_claim_documents` 的选章口径
（`SECTIONED_CHAPTER_KINDS` × `format=json`），再喂生产的
`claims_from_documents` + `prepare_claim_registration`：

```
文档 11 份（cross-validation ×5、report-writing ×6），claims 依次 126/127/138/120/106/143/125/133/109/129/124
抽取出的 claims 条数: 1380   剥键记账条数: 0
evidence 行数: 803
登记抛错: 断言登记失败，共 1 处 | offenders = ['claims[732].evidence[2].permalink 在断言内重复']
```

`claims[732]`（`c-06050401`，goal-4 `cross-validation-3.json`）的三条 evidence 里，
第 0 条和第 2 条是**逐字节相同**的同一条小红书评论 permalink：

```
https://www.xiaohongshu.com/explore/6a499e1b00000000070217d7?xsec_token=…&owli_comment=6a4e62b3000000002203e624
```

### 反事实读数（把那一处重复机械去掉，别的一个字不改）

```
含「断言内重复 permalink」的 claim 数: 1 / 1380   重复链接处数: 1
去重后可登记 claims: 1380   evidence→claim 映射行: 89   丢弃账(dropped): 0
```

**0 → 1380。** 而且 `dropped=0`，说明 1380 条主张引的 permalink 全部能联上库里的 evidence 行，
没有一条悬空。修前修后就是这两个数。

### ⚠️ 相反的那一支：走过了，「章挂了」不成立

提货单要求别把「产出主张的章挂了」当唯一成因。走完相反支，结论是**它连成因都不是**：

1. **成稿的章全都产出了 claims。** 11 份 JSON 章产物，`'claims' in document` **11/11 为真**，
   合计 1380 条。不存在「章成稿了但 claims 为 0」。
2. **本轮挂掉的 7 章，一章都不在产主张的路上。**
   `chapter_progress` 里 `status != 'done'` 的是：

   | goal | chapter | agent kind | 产物 format | 在 `SECTIONED_CHAPTER_KINDS` 里？ |
   |---|---|---|---|---|
   | goal-1 | ch-11/13/15/16 | data_collection 等 | — | 否 |
   | goal-1 | ch-18 | `consistency_check` | **markdown** | **否** |
   | goal-2 | ch-4 | 同上 | — | 否 |
   | goal-3 | ch-4 | 同上 | — | 否 |

   `_claim_documents` 只收 `SECTIONED_CHAPTER_KINDS`（`cross_validation` / `summary` /
   `report` / `report_writing`）且 `format=json` 的产物。
   ch-18 是 `consistency_check` + markdown，**就算它跑成了也一条 claim 都不会贡献**。
3. 所以提货单二节那条线索（ch-18 timeout×6）与 `claims=0` **没有因果关系**。它是另一件事。

---

## 顺手核到的第二件事：货 2 的前提被实测推翻

提货单货 2 写「整读大文件撞 Read 上限 → 每轮重试从头卡读耗光墙钟」。
把 `goals/goal-1/consistency-check.transcript.jsonl`（165 行、6 个 session）逐事件量了一遍：

| 量 | 读数 |
|---|---|
| `File content (28672 tokens) exceeds maximum allowed tokens (25000)` 出现次数 | 6 次（每个 session 恰好 1 次） |
| **这 6 次报错一共吃掉的时间** | **4.7 秒**（1.7 + 0.6×5） |
| 章首尾总跨度 | 1678 秒 |
| 报错占墙钟比例 | **0.28%** |

而且**模型每次都当场自愈**：报错后的下一个工具调用就改成了带 `offset` 的 `Read`，
接着用 `Grep` 定位，从没重试整读。

真正的死因是另一根：

```
attempt 1: start=+0s    → 下次起跑 +325s
attempt 2: start=+325s  → +362s
attempt 3: start=+688s  → +293s
attempt 4: start=+981s  → +312s
attempt 5: start=+1293s → +305s
attempt 6: start=+1599s → 被章墙钟砍在 +1678s（79s 就没了）
```

每轮间隔都贴着 300 s —— `DEFAULT_CLAUDE_TIMEOUT_SECONDS = 300.0`（`app/adapters/claude.py:431`），
**单次 run 的硬墙钟**。session 1 的最后一条事件是模型说
「I now have enough context to compose the consistency check. I'll struct…」，
之后没有 `result` 事件，是在**动笔写 `consistency-check.md` 的途中被砍的**。
六轮全是这个形状：花 170~230 s 把 62 KB 的 `data-cleaning.md` 探完，刚要落笔就到点。
第 6 轮起跑时 `chapter_deadline_seconds=1800` 只剩 201 s，79 s 就被章墙钟收走 → 判 `missing`。

也就是说：**ch-18 不是被 Read 上限拖死的，是「探完就没时间写」**。
按提货单原文去改「按需切片/摘要读」，省下的是那 4.7 秒，救不了这一章。

⛔ 这一条**没有**动手改，等调度拍。

### 调度裁决（2026-09-17）：本包不修，另立 §D-076

调度批：货 2 与 `claims=0` 是两个毛病，它要的是工序重排不是小修，本包不动。
下面五行是给 §D-076 提货单用的读数（调度嘱「署明是你查的」）：

1. 章 `goal-1/ch-18`（`consistency-check`，`readonly-analyst`，产物 markdown），
   `attempts=6`、`reason=timeout`、`status=missing`。
2. 每轮起跑间隔 325 / 362 / 293 / 312 / 305 秒，**全都贴着 300 秒**——
   `DEFAULT_CLAUDE_TIMEOUT_SECONDS`（`app/adapters/claude.py:431`）单次 run 硬墙钟。
3. 六轮都是同一个形状：**花 170~230 秒把 62 KB 的 `data-cleaning.md` 探完，刚要落笔就到点**；
   session 最后一条事件是「我已有足够上下文，开始撰写」，之后没有 `result` 事件 = 写到一半被砍。
4. 第 6 轮起跑时章墙钟 `chapter_deadline_seconds=1800` 只剩 201 秒，79 秒就被收走。
5. `Read` 超限报错 6 次共耗 **4.7 秒 / 1678 秒（0.28%）**，且模型每次当场改 `offset` 分段读自愈——
   ⛔ 「整读大文件耗光墙钟」不成立，切片读省下的是这 4.7 秒。

---

## 货 1 修法（调度 2026-09-17 批准加进本包，范围变更待用户追认）

### 改了什么

只改一件事：**同一条主张内逐字节重复的 permalink**，从「整批退回」降级为
「机械去重保留第一条 + 逐条记账」。

- `app/reliability/claims.py`：`prepare_claim_registration` / `register_claims` 加
  `deduped` 出参；命中重复时不再 `offenders.append`，改为记账后 `continue`。
  那一行本来就 `continue` 跳过重复链接，联接结果一字不差——**「整批退回」是它唯一的后果**。
- `app/orchestrator/runtime.py`：收尾登记时把 `deduped` 落成 `claims_links_deduped`
  事件（形制照抄 §FIX-2 的 `claims_keys_stripped`：`count` + `entries[:50]`）。
  ⛔ 不静默去重——静默去重等于把证据质量问题藏起来。

⛔ 别的校验一个字没放宽：结构违规（`stance`/`firsthand`/`origin_url`/`id`/`text`/
重复 claim id）照旧整批退回，有用例锁着。
⛔ 没碰禁区：`app/store/`、`migrations`、`app/sources/`、`app/adapters/`、
`app/reliability/ratelimit`、`app/replay/`、`app/config.py` 一个字没动；
`app/reliability/crossref` 也**只读不改**（离线量表时调用了它，没改它）。

### 真机库上读数：修前 / 修后

在**自己 worktree 里的快照副本** `var/snap/wx1-fixed.db` 上跑（⛔ 没写留服库），
喂的是真机 `r-20271e8a5028` 的 11 份章产物原文：

| 落点 | 修前 | 修后 |
|---|---|---|
| `reports.extra` 有没有 `claims` 键 | **没有** | 有 |
| `reports.extra.claims` 条数 | — | **1380** |
| `reports.extra.claims_dropped` 条数 | — | 0 |
| `evidence.extra.claim_ids` 非空行数 | **0 / 803** | **89 / 803** |
| 去重记账条数 | —（整批退回，什么都没写） | **1**（见下） |

去重记账的那一条，与真机 `events.report_validation` 的 offender 逐字对得上：

```json
{"claim_id": "c-06050401",
 "location": "claims[732].evidence[2]",
 "permalink": "https://www.xiaohongshu.com/explore/6a499e1b00000000070217d7?xsec_token=…&owli_comment=6a4e62b3000000002203e624"}
```

### 用例红绿两侧读数

新用例 `tests/test_d075_claims_chain.py` 共 5 条，先在 base `9bbe8fa` 上真红过一次
（当时工作树只有货 1 的 worklog，生产代码一个字没改）。
**每条红的第一处断言都落在病象本身**，不是落在「新出参还不存在」上——
记账断言一律排在行为断言之后，就是为了不让 `TypeError: unexpected keyword argument`
冒充病象红（第一版写反了，读红的原文时发现并改掉）。

| 用例 | base（红） | 本包（绿） |
|---|---|---|
| `一条重复不再连坐整批_其余主张照常登记` | `ClaimsRegistrationError: 断言登记失败，共 1 处`（`app/reliability/claims.py:269`） | PASSED |
| `去重必须留痕_去了几条哪条主张哪个链接都查得到` | 同上（第一处行为断言就红） | PASSED |
| `真正不同的链接一条都不许被并掉` | PASSED（防「改过头」的哨兵，两侧都绿） | PASSED |
| `无重复时落库逐字节不变_且结构违规照旧整批退回` | PASSED（回归锁，两侧都绿） | PASSED |
| `runtime_章成稿后带重复链接的主张仍真写进库` | **`KeyError: 'claims'`** —— 与真机「`extra` 里连键都没有」逐字同形 | PASSED |

读红原文时另见一处与本卡无关的既有毛病：`ClaimsRegistrationError` 是
`@dataclass(frozen=True)`，异常经 `contextlib` 重抛时会叠一层
`FrozenInstanceError: cannot assign to field '__traceback__'`，
把真正的错因挤到 traceback 上一段。⛔ 本包没动它，只在此留档。

### 全量 pytest

```
2208 passed, 3 skipped in 33.57s
exit=0
```

落盘 `/tmp/d075_full.txt` 后 `echo exit=$?` 取的码，⛔ 没用管道、⛔ 没用 `-q -q`。
基线 2203 + 本包新增 5 条 = 2208，对得上。

---

## 顺带量的：1380 条登记进库后，交叉验证表会自己出来吗

**会。** 出表条件与读数如下（⛔ 没为了让表出来改任何出表条件）：

1. **出表条件**：`app/report/polish/tables.py:_crossref_mix` 按
   `reports.extra.claims[].verdict` 计数。`crossref_mix` 是**无条件**挂进 `tables` 的
   （`omitted_tables` 那道闸只管 UGC 编码那几张表），所以它一直在 tables.json 里，
   只是 claims 为空时 `rows=[]`、`n=0`——真机那份正是这样，写手看见一张空表就不写它。
2. **verdict 谁给**：`register_claims` 写的主张**不带 verdict**；verdict 由收尾期的
   评级回填 `app/reliability/backfill.py:_backfill_claim_clusters` 算完簇后回写。
   `runtime.py` 里的顺序是**先登记、后回填**（登记在 3247 行，
   `_backfill_ratings_on_finalize` 在其后），所以登记一通，verdict 就跟着有。
3. **实测**：在快照副本上登记 1380 条后跑 `_backfill_claim_clusters`——

```
带 verdict 的主张数: 1380 / 1380
verdict 分布: SINGLE 1312 / PASS 28 / WEAK 24 / CONFLICT 16
crossref_mix: n = 1380，4 行（修前 n=0、0 行）
coverage: {"主张总数": 1380, "带多源证据的主张": 423}
counts.claims: 0 → 1380
```

⚠️ 两句要说给读的人听：

- 表出来了，但它说的第一句话是「**95.07% 的结论是单源孤证**」。这是语料层面的事实，
  不是缺陷——而且正是客户该看到的东西。正式稿会照这个读数写，调度心里要有数。
- 1380 条主张只引到 **89 / 803** 条证据行，主张池挤在很窄的一撮证据上。
  这是另一张卡的事，本包只留读数不动手。
