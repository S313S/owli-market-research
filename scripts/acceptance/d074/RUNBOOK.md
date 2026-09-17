# §D-074 容量让路 · 复验手册

**这份手册回答一件事**：引擎说「我现在满了」的时候，Owli 有没有把下一次尝试交给另一家？

背景一句话：2026-09-16 那轮（`r-20271e8a5028`），Codex 连着报
`Selected model is at capacity. Please try a different model.`，
而当时的代码谁都不认这句话，于是同一片的两次尝试全落在同一家满负荷的 Codex 上，
片没写出来 → 片失败节不判 done → 整轮中止。§D-074 把这类错误归入「可让路」，
§D-074-fu 补上真机读数。

---

## 一、看哪个文件、看哪个字段

**文件**：`var/runs/<research_id>/goals/<goal>/<章>.transcript.jsonl`
一章一份，**同章并发的多个片交替写同一份**（这一点很要紧，见下）。

**字段**：每一行都是一条 JSON，四个字段就够判：

| 字段 | 含义 | 判定里的用处 |
|---|---|---|
| `seq` | 行号，章内单调递增 | 定位、排序 |
| `engine` | `"Codex"` / `"Claude"` | **判据本身**：让路 = 这个字段换了家 |
| `output` | 这一行是哪个片/节写的 | **分流键**：同章并发，不按它分会读错 |
| `event` | 引擎原始事件（dict；CLI 的裸 stderr 是字符串） | 找 `at capacity` |

**一次「命中」占两行**：引擎先发 `{"type":"error","message":"…at capacity…"}`，
紧跟着 `{"type":"turn.failed","error":{"message":"…at capacity…"}}`。
所以 `grep -c "at capacity"` 数出来的是行数，**除以 2 才是真正撞了几次**。

**怎么切「一次尝试」**（按真机转录实测的形态，不是猜的）：先按 `output` 分流，
再在单个 output 的行序列里切段，段的起点是这四种之一——

1. 该 output 的第一行；
2. `engine` 与上一行不同（换家本身就是新的一次调用）；
3. `{"type": "thread.started"}`——一次 `codex exec` 正好发一条；
4. `{"subtype": "init"}`——Claude SDK 一次会话的起手。

---

## 二、什么读数算通过

对每一处命中，看**同一个 `output` 的下一段**：

| 读数 | 意思 | 该怎么办 |
|---|---|---|
| `failover-ok` | 下一段的 `engine` 换了家 | ✅ 让路生效，这就是 §D-074 要的读数 |
| `no-failover` | 下一段还是同一家 | ❌ 没让路。**别自己改 `routing.py`**，报调度另立修复包 |
| `unknown` | 同一个 output 没有下一段 | ⚠️ 那一片就此收场，这一处判不出来——见下面的坑 3 |

⛔ **不看日志文字、不看代码分支、不看「有没有报错」**。
让路本身不另发事件（§D-074 有意不加埋点：每条事件自带 `engine`，换家当场就看得见）。
"安静" 有两种意思——没让路也安静，让路了也安静，只有 `engine` 字段分得清。

---

## 三、两个脚本

### 1. 真撞容量之后：跑探子，它自己会找

```bash
cd ../Owli-d074fu     # 或任何带这两个脚本的树
../Owli/.venv/bin/python scripts/acceptance/d074/scan_capacity_failover.py
```

只读，不写不改任何被扫的树。默认扫 `Owli` / `Owli-wx1` / `Owli-serve` 三棵树的
`var/runs/**/*.transcript.jsonl`；跑在别处就 `--root <树>`（可给多次），
`--json` 出机读格式。

输出先是每棵树的文件数与命中数，然后是三档计数，最后逐条列出命中位置
（文件、`output`、attempt 序号与 `seq` 区间、命中的 `seq`、下一段的引擎与起始 `seq`）。
**拿到读数别只看计数**：挑两三条，按它给的 `seq` 用 `sed -n '<seq>p' <文件>` 把原文
读出来核一遍（尺子说什么都要读原文）。

### 2. 不想等外部状态：桩引擎联通验，随时能跑

```bash
../Owli/.venv/bin/python scripts/acceptance/d074/live_failover_probe.py --routing head
../Owli/.venv/bin/python scripts/acceptance/d074/live_failover_probe.py --routing base
```

真的 `CodexAdapter` 起真的子进程、走真的 CLI 事件协议，只把「服务端答什么」换成桩
（逐字吐真机那几行）；Claude 侧同理换 SDK 替身。跑在临时沙盒里，不联网、不起真引擎、
不写任何留服库、不花钱。

`--routing base` 把 §D-074 的 base `075c0f6` 的 `routing.py` 原样取出来当模块加载
（⛔ 不动工作树里的文件），别的一切完全相同——**两侧读数之差只可能来自路由代码**。
`--routing head` 应当 `failover-ok`，`--routing base` 应当 `no-failover`；
**只有一侧绿不算数**，base 侧红不出来说明这把尺子坏了，先修尺子。

### 3. 两把尺子自己的锁

`tests/test_d074fu_live_failover.py` 三条：桩引擎真链路读转录、探子的三档判定、
探子按 `output` 分流不被隔壁片带偏。

```bash
../Owli/.venv/bin/python -m pytest tests/test_d074fu_live_failover.py
```

---

## 四、已知的坑

1. **`grep -c` 数出来的是行数不是次数**：一次命中固定两行（`error` + `turn.failed`）。
   2026-09-16 那轮「24 处」其实是 24 行 = **12 次**。

2. **同章并发会把隔壁片读成「换家了」**：转录按章落盘，`consulting-parts` 里
   shard-1 报完容量之后插进来的是 `01-执行摘要.md` 的十几行 Claude 事件
   （seq 129–141），shard-1 自己的下一次尝试在 seq 142、还是 Codex。
   不按 `output` 分流就会把那十几行读成让路——**假绿**。探子按 `output` 分流，
   `tests/test_d074fu_live_failover.py` 里有一条专门锁这件事；手工核的时候也要盯住
   `output` 一栏，别只顺着 `seq` 往下看。

3. **`unknown` 不是「大概没事」**：它的意思是这一片报完容量就再没有下一次尝试了。
   09-16 那 12 次里有 6 次是这样（例：`goal-1` 的 `sec-2.part.1.md`，seq 83/84 是它
   这一章里的最后两行）。**这是病象更狠的一种形态，不是好消息**——只是这把尺子
   量的是「下一次换没换家」，没有下一次它就诚实地说判不出来。
   真验让路生效，要挑有下一次尝试的那些位置看。

4. **`at capacity` 出现在正文里不算**：写手复述报错时也会写出这句话。
   `routing.py::_is_capacity` 要求 `is_error`；探子扫的是转录原始事件行，
   正文是 `item.completed` 里的 `text`，措辞相同但不是引擎在报自己的状态——
   真撞上这种噪声，回到原文看这一行的 `type` 是不是 `error` / `turn.failed`。

5. **别拿别的措辞试**：`overloaded` / `server_overloaded` / `service unavailable` /
   `503` 在本项目转录里一次都没出现过，`_CAPACITY_MARKERS` 只收有证据的两条。
   真出现了新措辞，是加措辞的活（另立包），不是这份手册判红判绿的事。

6. **`service unavailable` 另有归属**：它已经在 `app/adapters/codex.py::_INFRASTRUCTURE_MARKERS`
   里，命中判「引擎不可用」直接抛，与容量让路是两条路，别混着读。
