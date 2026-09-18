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
