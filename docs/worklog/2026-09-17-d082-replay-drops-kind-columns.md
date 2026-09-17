# §D-082 replay 复制丢了「评论/帖子」两栏 · worklog

worktree `../Owli-d082`，分支 `d082-replay-kind-columns`，base **fcf50f1**（main）。解释器 `../Owli/.venv/bin/python`。
提货单 `MarketingResearch/docs/handoff/d-082-replay-drops-kind-columns.md`。调度 09-17 深夜通知：用户已解禁 `app/replay/import_research.py` 一处供货 3，顺序不变（货 1 报完再等叫）。

## 货 1：定因与影响面（零引擎、只读；全部量数在本包 `var/` 副本上）

### 快照与源库只读

| 库 | 取法 | 读前 / 读后 mtime | 结论 |
|---|---|---|---|
| 源头 `../Owli-wx1/var/wx1-serve.db`（8980） | `snapshot.py` → `var/wx1-source.db`，`mode=ro` + backup API，23:48:57 | db 09-16 15:00:37 / wal 15:57:45 / shm 14:36:37，读后逐字相同（00:12 复核仍同） | 未写；未在 `../Owli-wx1` 做任何 git 操作 |
| 沙盒真库 `../Owli-src5/var/src5-backfill.db` | 同上 → `var/sandbox-live.db`，23:48:58 | db 22:42:34 / wal 23:38:02，读后相同 | 未写 |
| `../Owli-reissue1/var/post-reaudit.db` | `copy_db.py`（`mode=ro` backup）取两份副本 | db 21:51:46、wal 0B 不变；**`-shm` mtime 变成 00:02:52**（WAL 库只读打开会碰共享内存索引文件，库内容未变） | 如实记账 |

integrity 两份均 ok、user_version 10。

### 尺子自核（先怀疑尺子）

- **`post-reaudit.db` 不是「簇回填之后」**（提货单 §二写的是之后）：它 21:51:46 取、回填 finish 21:53:21 才跑。实测它与沙盒现值差在 147 行 `extra` 的簇回填键（origin_key / crossref_*）和 `reports.extra.claims` 的 verdict，events 1764 vs 1816。⇒ 基准一律用 `var/sandbox-live.db`（回填之后、kind 未修）；`post-reaudit` 只作「回填前」底料做交叉核（见下 v3/v4）。自拍，不改范围。
- `tables_probe.py`（沿用 `rpt1_polish.py` 的 `ReadOnlyStore` + `collect_inputs`，同一序列化）在 `sandbox-live.db` 上重算的 tables.json 与 21:55 出稿时落盘的 `exports/r-3b3482ca7f8b.polished.consulting.tables.json` **逐字节相同**（108,621 B）。
- `derive.py finish`（`backfill_report` 原函数，`RefuseAdapter` 拒绝一切引擎调用并计数）在 `sandbox-live` 副本上再跑一遍（v0）、在 `post-reaudit` 副本上跑一遍（v4），两者与沙盒现值 **evidence 全列 + claims 全字段 diff 0**；拒掉的引擎调用都是 3 次（未结算 25 对 × 3 次尝试，与 §REISSUE-1 finish 的 guard 3 次同）。⇒ 回填可离线复现、幂等。

### ① 定因：列差集

`PRAGMA table_info(evidence)` 32 列 − `_EVIDENCE_COLUMNS` 28 列 = `id`、`report_id`（有意重发）+ **`kind`、`parent_permalink`**，没有别的漏列。`chapter_progress` 13 列在 `_copy_chapters` 里全覆盖。
复制链核实：r-3b3482ca7f8b ← r-96e0257a86b4 ← r-f9bb30969cf2 ← r-20271e8a5028（`replay_source_database` = wx1-serve.db）。源头 803 行（comment 563：xhs 428 / douyin 57 / reddit 78）按 permalink **803/803 全对上**；沙盒多出的 17 行是补采 HN 7 + X 10（source_type=post）。源头 → 第一跳 f9bb 逐列比：除 kind/父链外只有 89 行 `extra.claim_ids` 新增，五维分、citation_no 等一字未变——沙盒里 803 行的分数就是源头（kind 正确时）打的分。

### ② 在副本上修对 kind 后逐项量

`restore_kind.py` 在副本 `c1-live-kindfix.db` 上：改 563 行；xhs 428 / douyin 57 / reddit 78；父链全非空；与源头同 permalink 行两列 **mismatch 0**；id、citation_no、五维分、rating_notes、reports.extra **diff 0**。

| 派生数据 | 修前（沙盒现值） | 副本修 kind 后 | 差 | 尺子 |
|---|---|---|---|---|
| 五维分 / 等级 / 代表性分位 | 820 行 | `--rescore-only`（r1）与现值 diff **0** | 0 | `diff_derived.py` |
| 同上，**不修 kind 就跑 rescore-only**（r0） | — | 563 行 rating_notes 丢掉「评论·」前缀，分不变 | 563 行理由被写坏 | 同上 |
| 一手性审计输入 | 不含 kind / 父链 | — | 0 | `_firsthand_pairs` 字段表；并从 §REISSUE-1 引擎会话日志取提示词原文核：键无 kind，`source_type=comment` 在，标题带「评论 · 」 |
| 态度编码 | 332 条评论已编码 | 编码全在源头 09-16 做（转录 mtime 09-16 14:14–15:57），沙盒 0 次编码，extra.coding 与源头逐字同 | kind 喂错 **0 条** | `diff_rows.py` + 转录 mtime |
| 引用池与角标 | citation_no 79 个 | 各变体 diff 0 | 0 | `diff_derived.py` |
| 断言交叉结论（剥掉上轮持久化簇键后重算，v2 = 回填前底料修 kind 再回填 v3，两者 diff 0） | SINGLE 1238 / WEAK 50 / PASS 49 / CONFLICT 21 | SINGLE 1254 / WEAK 34 / PASS 51 / CONFLICT 19 | **18 条断言**：WEAK→SINGLE 16（全是「同一帖下多条评论」本应同源）、CONFLICT→PASS 2（评论与它自己的父帖曾被当成独立两源） | `derive.py finish --strip-crossref` |
| 同上但**不剥**持久化簇键（v1） | — | 断言结论同 v3，但 6 行评论的 `extra.origin_key` / `crossref_secondary` 留着旧值 | 6 行脏数据 | v1 vs v3 |
| 147 行交叉分与簇结论对得上 | 100/147 | 重算簇后 98/147 | −2 | `diff_derived.py` |

正式稿确定性表（`tables_probe.py` + `diff_tables.py`；t0=现值、t1=修 kind、t3=修 kind+重算簇、t2=再收交叉分）：

| 表 | t0（停掉的新稿用的） | t1 修 kind | 旧稿 09-16（源头，kind 对） |
|---|---|---|---|
| platform_mix 其中评论 xhs / reddit / douyin | 0 / 0 / 0 | **428 / 78 / 57** | 428 / 78 / 57（判据 4 对上） |
| 独立帖子数 xhs / reddit / douyin | 587 / 98 / 76 | 159 / 20 / 19 | 159 / 20 / 19 |
| 被引来自帖子数 xhs / douyin | 53 / 5 | 36 / 4 | — |
| 态度三表只数主体的条数 n（scenario_counts / scenario_attitude / attitude_by_topic） | **141** | **90** | 90 |
| 未点名条数（contrast_attitude.coverage） | 79 | 130 | 130 |
| 主体态度合计 正/负/中/混合 | 36/39/57/9 | 27/17/38/8 | — |
| 写手池 sources：quote_prefix 非空 / same_thread 非空 | 0 / 0 | 23 / 26 个角标 | — |

成因：`tables._own_text` 对 `kind=post` 的行把标题拼进「自己的话」，评论标题是「评论 · 父帖标题」，父帖标题点名豆包 ⇒ 51 条评论被错算成「说豆包」。t1→t3 只动 crossref_mix（上表 18 条）与 3 个被引角标的 crossref（S53/S56/S57 CONFLICT→PASS）。

### ③ §REISSUE-1 挂账：147 行交叉分

- 收敛轮（`backfill.py` 「`if rated and clustered_ids`」段）**即使 rated>0 也写不下去**：`_stored_labels` 对 147 行整批判 None——其中 6 行（X 4 / HN 2，补采行）`content_kind` 为空，一行缺标签整批跳过。只记不修（代码行为，非本包范围）。
- 收法甲「只收交叉维」（`crossref_converge.py crossref-only`，零引擎）：在 v3 副本上改 **49 行** score_crossref（其余 98 行已对得上），rating_notes 只换交叉一段，**grade 变 35 行**；147/147 对得上。变后再剥键重跑回填（x1b）diff 0 ⇒ 一次即定（簇计算本就把交叉分与 grade 从输入里拿掉，D-013 已剪环）。
  - grade 分布 A 16→15 / B 86→85 / C 399→399 / D 319→321；被引行 A 16→15 / B 45→42 / C 18→22；被引角标 **31 个等级变**（A→B 9、B→A 8、B→C 9、C→B 5）；原声闸（A/B/C）被引行进出 0；落到 D 的 2 行都没被引。
  - 表：只动 grade_mix 与 sources.grade，态度三表不变。
- 收法乙「整轮收敛（五维全按本地规则重算）」：如上，现码整段不写，量不出；且会替另外四维重下判断（§RATE-4/D-073 记过的两条打分路不一致），不建议。

### 工作稿与交付面

- 工作稿 `goal-6/cross-comparison-report.json` 是沙盒里 05:18–06:30 UTC 重写的（写手池里评论全是 kind=post、无父链；「评论要点明、与父帖相反写 stance=contradicts」那条提示词没法生效）。粗尺子：23 个被引评论角标里 21 个至少有一句点明「评论/网友/留言」，S62/S63 只出现在「5 条 DeepSeek 相关小红书 UGC…短评式吐槽」合并句里；未逐句人工核。重写要付：本段转录窗口 19 次结果 / **$11.69** / 72 min，且会重登记断言 ⇒ 一手性审计 1,973 对要重审（§REISSUE-1 实付 ≈4 h 40 m / $37.9）。
- Excel `exports/r-3b3482ca7f8b.xlsx`（09-17 14:30）「04_信息源」79 行「类型」全是「帖」，应为评论 23 / 帖 56（旧稿 xlsx 评论 61 / 帖 19）。`export_excel` 零引擎可重出。
- `app/api/delivery.py:45` by_kind 实时读库，库修好自动对；`source_mcp.py:836`（二跳只对 post 拉评论）与 `runtime.py:2287` 投影名单只在采集期生效，本研究不再采集 ⇒ 不用修。
- 沙盒另两份 r-f9bb30969cf2 / r-96e0257a86b4 同病（各 820 行全 post），非交付物。

### 货 3 改法建议（解禁后才动）

- 列清单与表结构同源：复制时取 `PRAGMA table_info(evidence)`（目标库）与源行键的交集，减去 `id`、`report_id`；JSON 列沿用 `_JSON_EVIDENCE_COLUMNS`（`author_meta/raw_metrics/norm_context/extra`，kind/父链不是 JSON 列）。旧 schema 的源库缺列时交集自然跳过、目标取默认值。
- 守卫用例造红：真 `Store` 建源库，写一条帖子 + 一条 `kind=comment` 且带 `parent_permalink` 的评论（其余列都给非默认值），`import_research` 导到新 id，逐列比源行与新行（除 id/report_id）；base 上必红在 kind（comment→post）与 parent_permalink（有→None），读被判红原文确认后再改。

### ④ 修复清单（待调度批）

| # | 项 | 受影响读数：修前 → 副本修后（差） | 客户稿哪一节 | 处置 | 依据 |
|---|---|---|---|---|---|
| 1 | evidence.kind / parent_permalink（r-3b3482ca7f8b） | comment 0 → 563（xhs 428 / douyin 57 / reddit 78）；父链 0 → 563；与源头 mismatch 563 → 0 | 全部表的底 | **零引擎，必修** | `restore_kind.py`，副本实测 id/角标/分 diff 0 |
| 2 | 平台表 platform_mix | 其中评论 0 → 428/78/57；独立帖子数 587/98/76 → 159/20/19；被引来自帖子数 xhs 53→36、douyin 5→4 | 附录平台表、正文「声音集中在少数帖子」 | 零引擎，随 #1 自动对（出稿时重算） | t0/t1 对照，与 09-16 旧稿一致 |
| 3 | 态度三表 + 原声表 coverage、对照表 | 主体条数 141 → 90（−51）；未点名 79 → 130；态度合计 36/39/57/9 → 27/17/38/8 | 正文态度表、摘要「已编码评论 N 条」、附录对照表 | 零引擎，随 #1 自动对 | `_own_text` 按 kind 取标题 |
| 4 | 写手池 quote_prefix / same_thread | 0/0 → 23/26 个角标 | 原声引用、同帖提示 | 零引擎，随 #1 自动对 | 同上 |
| 5 | 断言交叉结论（簇回填） | SINGLE/WEAK/PASS/CONFLICT 1238/50/49/21 → 1254/34/51/19（18 条断言） | 交叉验证表、建议段门禁（S53/S56/S57 CONFLICT→PASS） | **零引擎，必修**：先剥 147 行持久化簇键，再跑 `backfill_report` 回填（拒引擎） | v2 = v3，不剥留 6 行旧 origin_key |
| 6 | §REISSUE-1 挂账：147 行交叉分 | 对得上 100/147（修 kind 后 98）→ 甲 147/147；49 行分、35 行 grade、31 个被引角标等级变 | 等级表、信息源清单等级、「C 级只作旁证」规则 | **待拍**：甲 零引擎只收交叉维（`crossref_converge.py`）/ 乙 不收，照旧挂账 | 收敛轮现码写不下去（6 行缺标签整批跳过） |
| 7 | Excel xlsx「类型」列 | 帖 79 → 评论 23 / 帖 56（若批甲，等级列同步变） | 交付 Excel | 零引擎重出（`export_excel`），建议并入 §REISSUE-1 出稿时一起出 | `excel.py:97` |
| 8 | 五维分 / 代表性 | 0 差 | — | **不用修**；⛔ #1 之前不许跑 `--rescore-only`（会写坏 563 行理由） | r0/r1 |
| 9 | 一手性审计 | 输入不含 kind | — | 不用修 | 提示词原文核过 |
| 10 | 态度编码 | kind 喂错 0 条 | — | 不用修（不重编） | 编码在源头 09-16 做完 |
| 11 | 引用池与角标 | 0 差 | — | 不用修 | 各变体 diff 0 |
| 12 | 工作稿 goal-6 交叉对比报告正文 | 写手看到的评论全是 post；23 个被引评论 21 个正文点明了 | 正式稿底稿 | **建议不修、挂账**；若修付引擎：重写 ≈72 min / ≈$11.7 / 19 次，连带断言重登记 + 一手性审计重审 ≈4 h 40 m / ≈$38 | 转录时间窗读数 |
| 13 | 沙盒 r-f9bb30969cf2 / r-96e0257a86b4 | 各 563 行错标 | 非交付 | 不修（要修零引擎同 #1） | — |
| 14 | 正式稿 | 停掉的半份稿 4 片基于错表 | 全稿 | 归 §REISSUE-1 重出一次（付引擎，本包不估） | 出稿开头清旧片 |

**货 2 执行顺序建议**（全部零引擎、一次写完）：① backup API 写前快照（确认 8981 无在跑任务）→ ② #1 恢复两列并判据 1 → ③ 剥 147 行持久化簇键 + 回填（#5，拒引擎，预期拒 3 次）→ ④ 若批甲再做 #6，随后剥键重跑回填确认 diff 0 → ⑤ `tables_probe.py` 复核判据 4 与本表读数 → ⑥ 交 §REISSUE-1 出稿（含 #7 Excel）。⛔ ②之前不跑 rescore-only；③④不可调换（先定簇结论再定交叉分）。

货 1 新增尺子与脚本：`scripts/acceptance/d082/{snapshot,copy_db,restore_kind,diff_rows,tables_probe,diff_tables,derive,diff_derived,crossref_converge}.py`；读数落 `var/`（tables/、derive/、diffs/，不入库）。`app/` 零改动。
