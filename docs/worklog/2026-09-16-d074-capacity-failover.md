# §D-074 worklog · 引擎「容量上限」不触发让路，整节判失败

- worktree：`../Owli-d074`，分支 `d074-capacity-failover`，base `075c0f6`
- python：`../Owli/.venv/bin/python`
- 提货单：`docs/handoff/d-074-capacity-should-failover.md`
- ⛔ 未 push、未合 main、未重出正式稿、未写任何留服库、未重启或停 8969/8975/8976/8979/8980。
- ⛔ 未碰禁区；改动只落在 `app/adapters/routing.py` 一个文件（`app/adapters/` 下别的文件一个字没动）。
- 真机转录 `../Owli-wx1/var/runs/r-20271e8a5028/` 全程**只读**。

## 先把病象的范围核清楚

提货单写的是正式稿「关键发现」shard-1。实际查下来**不止那一处**：
`r-20271e8a5028` 全库 24 处命中「at capacity」，分布在

```
goals/polished/consulting-parts.transcript.jsonl   ← 提货单说的那处
goals/goal-1/doubao_cn_reputation_profile.transcript.jsonl
goals/goal-3/ugc-coding.transcript.jsonl
goals/goal-4/goal-4-report.transcript.jsonl
goals/goal-5/goal-5.transcript.jsonl               ← report-writing-5-sec-3-part-4
```

全部是 Codex。也就是说**这一轮的工作稿也被同一件事咬过**，不是正式稿一处的偶发。
（改动落在 `routing.py`，本来就对两边同时生效，范围没变，只是读数比提货单大。）

## 措辞取证：同族词一个都没收

提货单让「顺带核 `overloaded`、`503`、`server_overloaded` 等同族措辞在本项目真出现过哪些，
只收有证据的」。对 `Owli` / `Owli-wx1` / `Owli-serve` 三棵树的 `var/runs` 全量扫：

| 措辞 | 本项目转录里的出现次数 | 收不收 |
|---|---|---|
| `at capacity` | 24 | 收 |
| `Please try a different model` | 24（与上条同行） | 收 |
| `overloaded` / `server_overloaded` | 0 | ⛔ 不收 |
| `service unavailable` | 0 | ⛔ 不收 |
| `503` | 只匹配到 `503a`/`503d` 这类哈希串噪声，无一条是状态码 | ⛔ 不收 |

`service unavailable` 另有一层：它**已经**在 `app/adapters/codex.py:_INFRASTRUCTURE_MARKERS`
里，命中就判「引擎不可用」直接抛。收进容量类会和那条现成的路打架，而且 `codex.py`
按提货单是要报调度才能动的。没证据 + 会打架，两条都指向不收。

## 货 1 · 容量类错误归入可让路（commit `997c030`）

`app/adapters/routing.py`，四处：

1. `_CAPACITY_MARKERS = ("at capacity", "please try a different model")`。
2. `_is_capacity(event)`：只按**报文措辞**判、不按引擎名判（两家哪天都可能这么说），
   且要求 `is_error` —— 同一句话出现在正文里（写手复述报错）不算。
3. `_note_capacity(research_id, engine)`：写 `_route_overrides[research_id] = 另一家`。
   走的是**现成那条让路路**（限流让路用的也是它），⛔ 没新开失败路径。
4. `run()` 的 `routed_event` 里挂钩，**不 return**：这条错误照常往下走事件管道，
   只是顺手把后续尝试改派走。规划期（`_PLANNING_KINDS`）不记——规划固定走 claude、
   看不见这个覆盖，给它记一笔只会把别的任务无端赶去 codex。

三条⛔守住了：

- **不碰退避时钟**：容量类错误的 `route_state` 是 `None`，压根不进 `_start_backoff`。
  D-023 那条「退避借用了限流的时钟睡满五小时」的路一行都没走到。
- **不当永久不可用**：`_capacity_engines` 只是「这一串连着的失败里谁喊过满」，
  `run()` 的 `finally` 里只要这一轮**没人喊满**就整条清掉。跑通一轮 = 容量回来了 =
  让路额度还回来（用例 ④ 锁的就是这条）。
- **不无限循环**：两家都喊过满就**停在原地**，不在两家之间来回倒。来回倒只会把每一次
  重试都变成一次换家，跑满重试次数，最后还是原来那条失败路收场。

## 货 2 · 四条用例（commit `2645c23`（本条））

`tests/test_d074_capacity_failover.py`。夹具串**逐字**取自 `consulting-parts.transcript.jsonl`
seq 123/124：`Selected model is at capacity. Please try a different model.`，
连同转录里紧跟着的第二种形态（原话嵌在 `turn.failed` 的 `error.message` 里）一起过
**真归一路径** `normalize_codex_event`。⛔ 没自造更好认的措辞。
回归锁那条用的也是同一轮的真实报文
`Reconnecting... 2/5 (stream disconnected before completion: tls handshake eof)`。

起手先 `request_alternate(RESEARCH_ID)` 把任务推到 Codex 上——真机那一片
就是被让路机制交给 Codex 的（`report_writing` 默认 claude），方向与真机一致。

| 用例 | base `075c0f6` | 货 1 之后 |
|---|---|---|
| ① 原引擎报容量上限 → 下次尝试落在另一引擎 | 红：`assert 2 == 1`（`codex.calls`） | 绿 |
| ② 两家都报 → 按原有失败路径收场不来回倒 | 红：`assert 4 == 1`（`codex.calls`） | 绿 |
| ③ 非容量类错误行为不变（回归锁） | **绿**（它锁的是「不变」） | 绿 |
| ④ 容量上限不是永久不可用，跑通一轮后让路额度还回来 | 红：`assert None == 'claude'` | 绿 |

用例 ④ 是自补的（提货单只要三条）：它锁的是货 1 里「⛔ 不当永久不可用」那条我自己
的设计决定，不锁就是一段没人量的代码。仍在提货单范围内、禁区外，按规矩自己拍。

### 读过被判红的原文，红的是这件事

① 的红是 `assert codex.calls == 1` 打出 `assert 2 == 1`，`claude.calls` 全程 0 ——
**两次 attempt 全落在同一家满负荷的 Codex 上**，与 09-16 真机转录 seq 123/124/127/128
逐字同形（连报两轮同一句话、片没写出来）。不是夹具塌了：夹具塌会红在别的断言上，
而 ③ 在 base 上是绿的，说明这套假引擎/任务在 base 上跑得通、量得出「没让路」。
② 的红是 `assert 4 == 1`，四次 attempt 一次都没换过家。

## pytest 全量

⛔ 未用管道、⛔ 未用 `-q -q`；落盘 `/tmp/d074-full.txt` 后单独 `echo exit=$?`。

```
../Owli/.venv/bin/python -m pytest tests/ > /tmp/d074-full.txt 2>&1; echo "exit=$?"
exit=0
======================= 2203 passed, 3 skipped in 34.52s =======================
```

2203 = 判据线 2199 + 本包新增 4 条。既有用例零改动（一条都没动过尺子）。

## 没做的事 / 留给后面的

- **没有真机复验**：容量上限是外部状态，复现要等 Codex 再满一次；本包判据全在用例上。
  下一次真机撞到「at capacity」时，转录里应当看得见**同一片的第二次 attempt 换了
  `"engine"` 字段**（`Codex` → `Claude`）——那就是这条修复在生产里的读数，
  不用新加埋点。
- **没加新事件**：让路本身不另发事件。理由是转录里每条事件自带 `engine` 字段，
  换家当场就看得见（09-16 的病象正是这么诊出来的），多发一条只会多一处要维护的断言。
