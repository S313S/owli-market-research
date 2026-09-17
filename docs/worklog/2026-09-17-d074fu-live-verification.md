# §D-074-fu worklog · 容量让路的真机复验（验尺子，不修代码）

- worktree：`../Owli-d074fu`，分支 `d074fu-live-verification`，base `9bbe8fa`
- python：`../Owli/.venv/bin/python`
- 提货单：`MarketingResearch/docs/handoff/d-074-fu-live-verification.md`
- ⛔ 未 push、未合 main、未重出正式稿、未写任何留服库、未重启或停 8969/8975/8976/8979/8980、未起整跑。
- ⛔ 未碰禁区：`app/` 下**一个字节都没动**（`git diff 9bbe8fa --stat` 只有
  `scripts/acceptance/d074/`、`tests/`、`docs/worklog/` 三处新增）。
- 被扫的三棵树与 `../Owli-wx1/var/runs/r-20271e8a5028/` 全程**只读**。

本包的角色是**验尺子的人**。§D-074 已合入 main，但它的四条用例用的是假适配器
（`tests/test_d074_capacity_failover.py::_Engine`），证明的是「`RoutedAdapter` 的分支
写对了」，证明不了「真的 `CodexAdapter` 吐出真的 CLI 事件时这条分支会被走到」——
中间还隔着子进程、JSONL 解析、`ratelimit.route`、`normalize_codex_event`、transcript
落盘一整条管道。本包把那一段接上，并留下一把以后能随手重跑的尺子。

---

## 货 1 · 桩引擎真机联通验：两侧读数都在，红侧真红过

`scripts/acceptance/d074/live_failover_probe.py`。

**换掉的只有「服务端答什么」**：

- 真的 `app.adapters.codex.CodexAdapter`，只把 `executable` 指到一个桩可执行体。
  桩逐字吐 09-16 真机 `consulting-parts.transcript.jsonl` seq 118–124 那几行：
  两行非 JSON 的 stderr 噪声、`thread.started`、`turn.started`、一条无关的
  `item.completed` 告警，然后才是 `{"type":"error"}` 与 `{"type":"turn.failed"}`
  两种形态的 `Selected model is at capacity. Please try a different model.`。
  ⛔ 没自造一个更好认的措辞，⛔ 桩不写产物（真机那两轮也没写出来，片失败正是病象本身）。
- 真的 `ClaudeAdapter`，只把 `sdk` 换成按剧本答话的替身（Claude 侧走进程内 SDK，
  没有可替换的可执行体，「换服务端答什么」只能换到这一层）。
- 真的 `RoutedAdapter`；两次 attempt = 两次 `adapter.run`，与 polish 的重试路同口径。
- 起手 `request_alternate(RESEARCH_ID)` 把任务推到 Codex 上——真机那一片
  （`report_writing` 默认 claude）就是被让路机制交给 Codex 的，方向与真机一致。

**判据读的是 transcript 落盘的 `engine` 字段**，⛔ 不读 `_Engine.calls`、不读日志文字——
那两样在真机上都没有。09-16 诊出病象用的就是这把尺子、这个文件形态。

**造红一侧怎么做到「只差路由代码」**：`--routing base` 用 `git show
075c0f6:app/adapters/routing.py` 把 base 的路由原样取出来写进临时文件、当模块加载，
其余一切完全相同。⛔ 没动工作树里的 `app/adapters/routing.py`（本包是验证，不是二次修）。
`git diff 075c0f6 9bbe8fa --stat` 也印证了 §D-074 的 app 改动只有 `routing.py` 一个文件，
所以两侧读数之差**只可能**来自路由代码。

### 两侧读数

| | attempt 1 的 `engine` | attempt 1 容量报文 | attempt 2 的 `engine` | attempt 2 容量报文 | `succeeded` | `route_override` | 转录行数 | 判定 |
|---|---|---|---|---|---|---|---|---|
| **base `075c0f6`（造红）** | `Codex` | 2 行 | **`Codex`** | **2 行** | False / False | `None` | 14 | `no-failover` |
| **head `9bbe8fa`（被验）** | `Codex` | 2 行 | **`Claude`** | 0 行 | False / **True** | `claude` | 10 | `failover-ok` |

base 侧那 14 行与真机 seq 118–128 **逐字同形**：连着两次 attempt 都写着
`"engine": "Codex"`，两次各两行容量报文，片一次都没写出来。这不是夹具塌了——
夹具塌会两侧一起塌，而 head 侧同一套桩、同一套任务跑出了让路。

复跑命令（沙盒，不联网、不起真引擎、不写留服库、不花钱）：

```bash
../Owli/.venv/bin/python scripts/acceptance/d074/live_failover_probe.py --routing head
../Owli/.venv/bin/python scripts/acceptance/d074/live_failover_probe.py --routing base
```

---

## 货 2 · 真机探子：对历史底料通电，量出红来了

`scripts/acceptance/d074/scan_capacity_failover.py`，只读扫描。

**三档判定**（对每一处 `at capacity` 命中，看同一个 `output` 的下一段）：
下一段换了家 = `failover-ok`；下一段还是同一家 = `no-failover`（红）；
没有下一段 = `unknown`。

**切段规则按真机实测的形态定**：转录是**按章**落盘的，同章并发的多个片交替写同一份
文件，所以先按 `output` 分流，再在单个 output 的行序列里切段；段的起点是
「该 output 第一行 / `engine` 换了 / `thread.started` / `subtype=init`」四者之一。

### 历史底料读数（全部在修复前）

扫的是提货单点名的三棵树。**只有 `Owli-wx1` 有 `var/runs`**：

| 树 | `var/runs` | transcript 份数 | 命中 attempt 数 |
|---|---|---|---|
| `Owli` | ⛔ 不存在 | 0 | 0 |
| `Owli-wx1` | 有 | 106 | 12 |
| `Owli-serve` | ⛔ 不存在 | 0 | 0 |

为防漏，另把本机 `InformationCollection/` 下**全部 129 棵树**扫了一遍
（`for d in */; do grep -r "at capacity" "$d/var/runs"; done`）：
`at capacity` 只在 `Owli-wx1` 出现，24 行。所以 24 就是全量，没有别处的底料被落下。

```
命中行数 24，落在 12 次 attempt 上
  failover-ok=0   no-failover=6   unknown=6
```

**`failover-ok = 0` 是这把尺子的通电证明**：底料全在修复前，一处绿都不该有，
也确实一处都没有；同时它对有后续尝试的 6 处**判出了红**——量得出红，以后量出绿才算数。

### 一处小修正：提货单说的「24 处」是 24 **行**，不是 24 次

一次命中固定占两行：引擎先发 `{"type":"error","message":"…at capacity…"}`，
紧跟着 `{"type":"turn.failed","error":{"message":…}}`。24 ÷ 2 = **12 次**。
提货单预期「24 处全部 `no-failover`」，实际是 12 次里 6 次 `no-failover` + 6 次 `unknown`。

**`unknown` 不是「大概没事」**：它的意思是那一片报完容量就再没有下一次尝试了
（例：`goal-1` 的 `sec-2.part.1.md`，seq 83/84 是它在这一章里的最后两行）。
这是病象更狠的一种形态，不是好消息——只是这把尺子量的是「下一次换没换家」，
没有下一次它就诚实地说判不出来，⛔ 不替它猜。

### 人工抽查 3 处，逐条读原文（`sed -n '<seq>p'`，不经过被测脚本）

1. **`polished/consulting-parts.transcript.jsonl` / `02-关键发现.shard-1.md`，尺子判 `no-failover`**
   原文 seq 123 `{"engine": "Codex", … "type": "error", "message": "Selected model is at capacity…"}`、
   seq 124 `turn.failed` 同一句话、seq 125 `{"engine": "Codex", … "type": "thread.started"}`
   同一个 `output`。下一次尝试确实还在 Codex。**与尺子一致**。

2. **`goal-3/ugc-coding.transcript.jsonl` / `batch-019.json`，尺子判 `no-failover`**
   原文 seq 234 `error` + seq 235 `turn.failed` 都是 `"engine": "Codex"`，
   seq 236 `{"engine": "Codex", … "thread.started"}`、`output` 仍是 `batch-019.json`。
   **与尺子一致**。

3. **`goal-1/doubao_cn_reputation_profile.transcript.jsonl` / `sec-2.part.1.md`，尺子判 `unknown`**
   `grep '"output": "sec-2.part.1.md"'` 全文只有 seq 70–84 十五行，最后两行正是
   seq 83 `error` / seq 84 `turn.failed`。该片此后再没出现过，**确无下一次尝试**，
   **与尺子一致**。

附加核对（并发交错这一坑）：`shard-1` 第 4 段判 `no-failover`、下一段 `first_seq=142`。
原文 seq 129–141 是 `01-执行摘要.md` 的 **Claude** 事件（隔壁片），seq 142 才是
`shard-1` 自己的 `{"engine": "Codex", "thread.started"}`。尺子按 `output` 分流，
没把隔壁片的 Claude 读成「换家了」——这条假绿的口子堵住了。

复跑命令：

```bash
../Owli/.venv/bin/python scripts/acceptance/d074/scan_capacity_failover.py
```

---

## 货 3 · RUNBOOK

`scripts/acceptance/d074/RUNBOOK.md`：下次真撞容量时看哪个文件哪个字段、
三档读数各是什么意思该怎么办、两个脚本怎么跑、六条已知的坑
（`grep -c` 数的是行不是次 / 同章并发会读出假绿 / `unknown` 的真实含义 /
正文复述报错不算 / 别拿没证据的措辞试 / `service unavailable` 另有归属）。
⛔ 没写成只有作者看得懂的备忘：每一条都写清楚"看哪里、什么读数、然后做什么"。

---

## 尺子自己的锁

`tests/test_d074fu_live_failover.py` 三条（项目坑：自造脚本造过七次假数据，尺子自己也要验）：

| 用例 | 锁的是什么 | base `075c0f6` | head `9bbe8fa` |
|---|---|---|---|
| 桩引擎走真适配器时容量上限让路，转录里下一次尝试写着 Claude | 真链路 + 读 `engine` 字段 | 红（实测 attempt 2 = `Codex`） | 绿 |
| 探子把「修复前 / 换了家 / 没有下一段」三种形态分别判红绿与 unknown | 三档判定各自出得来 | 绿（它锁的是尺子，与路由无关） | 绿 |
| 探子按 `output` 分流，不被同章并发的别的片带偏 | 堵住那条假绿 | 绿（同上） | 绿 |

第 1 条的红是**实跑出来的**：把同一个场景跑在 base 的路由模块上，
attempt 2 的 `transcript_engines` 量出 `['Codex']`、`succeeded=False`、
`route_override=None`，四条断言全不成立。⛔ 不是推断。

## pytest 全量

⛔ 未用管道、⛔ 未用 `-q -q`；落盘 `/tmp/d074fu-full.txt` 后单独 `echo exit=$?`。

```
../Owli/.venv/bin/python -m pytest tests/ > /tmp/d074fu-full.txt 2>&1; echo "exit=$?"
exit=0
======================= 2206 passed, 3 skipped in 31.11s =======================
```

2206 = 判据线 2203 + 本包新增 3 条。既有用例零改动（一条都没动过尺子）。

## 复验结论与挂账

- **§D-074 没修错**：真适配器 + 真 CLI 事件协议下，容量上限确实触发换引擎，
  下一次尝试的 `engine` 字段从 `Codex` 变成 `Claude`，且让路后那一次真写出了产物。
  ⛔ 未发现需要二次修的地方，`app/adapters/routing.py` 一个字节没动。
- **仍然没有「生产里真撞一次」的读数**：本包用桩把联通性验到了，但外部状态没法造。
  探子留在树上，下次真撞时直接跑就有读数——这是本包能给的最接近真机的东西。
- **挂账（`unknown` 那 6 次背后的问题，不属本包范围）**：修复前有一半的容量命中
  是「报完就此收场、连第二次尝试都没有」。让路只在**有下一次尝试**时起作用；
  那 6 处如果换成修复后的代码，让路能不能救得回来，取决于那一片当时为什么没有重试。
  这条留给调度判要不要另立包，⛔ 本包不猜、不动。
