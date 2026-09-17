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

---
