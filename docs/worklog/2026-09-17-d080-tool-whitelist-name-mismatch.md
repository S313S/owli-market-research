# §D-080 worklog · 采集工具在 Claude 路上全线被拒（白名单拼法不一致）

- worktree：`../Owli-d080`，分支 `d080-tool-name-mismatch`
- base：调度令 `git rebase 6803857`（本地 main，含 §D-075 / §D-074-fu / §RPT-6）。
  提货单上写的 `3c213e7` 是 rebase 前的底，本包一切读数以 **6803857** 为 base。
- python：`../Owli/.venv/bin/python`
- 提货单：`MarketingResearch/docs/handoff/d-080-tool-whitelist-name-mismatch.md`
- ⛔ 未 push、未合 main、未重出正式稿、未写任何留服库、未重启或停 8969/8975/8976/8979/8980/8981、未起整跑与真小跑。
- ⛔ 未碰 `../Owli-src5` 与 8981 那棵树。
- ⛔ 未碰禁区。改动只落在 `app/adapters/source_mcp.py` 一个文件——**比用户批准的范围还窄**：
  用户点名批准的例外是 `source_mcp.py` + `claude.py` 这一处命名一致性，实际 `claude.py`
  一个字没动（它本来就只是 `exposed_tool_name` 的消费方，拼法修在产名字的那一头就够）。

## 一、SDK 的实际改写规则：实测来的，不是按单一样例硬编

提货单提醒「若 SDK 的命名规则不止『点变下划线』这一条，⛔ 不许按单一样例硬编」。
先量后写：拿**真 CLI**（`claude_agent_sdk` 2.1.274 内置那个 Mach-O）+ **真 stdio MCP
server**，注册一批故意做花的工具名，连上去读 `system/init` 消息里的 `tools` 清单。

> 走的是 `ClaudeSDKClient.connect()` → 读第一条 `system/init` → 立刻 `interrupt()`。
> 这是一次握手，不是一次调研：没有整跑、没有小跑、没写任何库。
> （先试过 `get_server_info()` 与 `get_mcp_status()`：前者这一版根本没有 `tools` 键，
> 后者给的是**原始**工具名 `source.hacker_news`，两个都量不到「暴露成什么」。）

实测读数，逐条：

| 注册名 | SDK 暴露的后半段 | 说明 |
|---|---|---|
| `source.hacker_news` | `source_hacker_news` | 点换下划线 |
| `a.b.c` | `a_b_c` | 逐个换 |
| `double..dot` | `double__dot` | ⛔ 连续下划线**不**折叠 |
| `.leading` | `_leading` | ⛔ 首尾下划线**不**去掉 |
| `trailing.` | `trailing_` | 同上 |
| `Upper.Case` | `Upper_Case` | 大小写原样保留 |
| `dash-keep.dot` | `dash-keep_dot` | 连字符原样保留 |
| `under__score` | `under__score` | 安全字符一个不动 |
| `sp ace` / `plus+sign` / `slash/x` / `colon:x` | `sp_ace` / `plus_sign` / `slash_x` / `colon_x` | 一律换 |
| `中文.源` | `____` | 非 ASCII 也逐字符换（4 字符 → 4 下划线） |

服务端名那一段同规则：把服务端注册成 `owli.probe-X`，暴露出来是 `mcp__owli_probe-X__…`。

**结论：逐字符把 `[^A-Za-z0-9_-]` 替换成 `_`**，不折叠、不去首尾、不改大小写。

⚠️ 这里正是「不许按单一样例硬编」救下来的地方：只看 `source.hacker_news` 这一个样例，
最自然的写法是 slugify（换 → 折叠 `_+` → 去首尾 `_`）。CLI 二进制里确实也躺着
`[^a-zA-Z0-9_-]` / `_` / `_+` / `^_|_$` 这么一组常量，看着就像 slugify，差点照抄。
实测把后两步否了：`double..dot` 出来是 `double__dot` 不是 `double_dot`，
`.leading` 出来是 `_leading` 不是 `leading`。
唯一与 Python 不同口径的角落是 BMP 外字符（JS 按 UTF-16 码元算两个下划线，
Python 按码点一个）——信息源 id 都是 ASCII 标识符，够不着这个角落，已写进代码注释。

## 二、货 1：修拼法

`app/adapters/source_mcp.py`：

- 新增 `sdk_name_segment()`：上面那条实测规则，实测表逐条写在常量上方当依据。
- 新增 `registered_tool_name(source_id)` → `source.<id>`：**注册名的唯一出处**。
- `exposed_tool_name()` 改为「注册名过一遍 SDK 改写」，⛔ 不再自己拼字面量。
- `_tool_definition()`（MCP 服务端建工具清单的那个函数）的 `name=` 改用
  `registered_tool_name()`——这一步是关键：不这么改的话，两头仍然是两份字面量，
  守卫用例也只能守个寂寞。

读数：`source.hacker_news` → `mcp__owli_sources__source_hacker_news`（与实测逐字一致）。
逻辑名仍是 `source.hacker_news`，`capability.tools` / plan / `call_tool` 全线不受影响。

## 三、货 1 的判据：桩真机两侧读数（⛔ 不看 diff）

新探子 `scripts/acceptance/d080/tool_whitelist_probe.py`，形制照抄
`scripts/acceptance/d074/live_failover_probe.py`：**真适配器 + 真事件协议，只换「服务端答什么」**。

- **真的** `ClaudeAdapter.run()`、真的 `make_permission_callback`、真的 `build_claude_options`、
  真的 transcript 落盘与事件归一。
- **真的** `SourceToolAdapter.call()`——闸放行之后工具是真被调起来的。
- **桩** SDK：Claude 走进程内 SDK，没有可替换的可执行体，只能换到这一层（与 §D-074-fu 同一处取舍）。
  桩干的就是真 CLI 干的事：按 `mcp__<server>__<tool>` 发起调用、问一次 `can_use_tool`、照答复行事。
  ⛔ 桩里不做任何判定，放行还是拒全由真回调说了算。
- **桩** 信息源：只记账，⛔ 不联网。被验的是闸放不放行，不是 HN 今天有没有新帖。
- 桩用的工具名 `mcp__owli_sources__source_hacker_news` ⛔ 不是自造的好认措辞：
  ① 真机转录 `r-96e0257a86b4` goal-1/ch-13 里模型调的就是它；② 上面那次实测也是它。
- `--code base` 用 `git show 6803857:app/adapters/source_mcp.py` 原样加载当模块，
  只把 `app.adapters.claude` 用的 `exposed_tool_name` 换成 base 那版，⛔ 不动工作树。
  别的一切完全相同，所以两侧读数之差只可能来自这一处拼法。

两侧读数（⛔ 只有绿的一侧不算数）：

| 读数 | `--code base`（6803857） | `--code head` |
|---|---|---|
| 白名单里的 mcp 工具 | `mcp__owli_sources__source.hacker_news` | `mcp__owli_sources__source_hacker_news` |
| 模型调用的工具名 | `mcp__owli_sources__source_hacker_news` | 同左 |
| 闸的判决 | **deny** | **allow** |
| 闸的原话 | `工具不在 capability 白名单：mcp__owli_sources__source_hacker_news` | （空） |
| 出现「工具不在 capability 白名单」 | **True** | **False** |
| 真适配器 `permission_denials` | `['mcp__owli_sources__source_hacker_news']` | `[]` |
| 信息源真被调用到 | **False** | **True** |
| 桩源收到的调用 | `[]` | `[('hacker news 上的产品讨论', '30d')]` |
| 落盘产物 | `[]` | 两行证据 JSON |

两侧 exit=0（各自按自己那一侧的判据判）。base 侧把真机病象逐字复刻出来了：
闸拒 → 写手不绕道 → 落盘 `[]`（真机里接着就是章判 `tool_unavailable`）。

### 探子自己的尺子先量废过一次

第一版读的是 `getattr(result, "denials", [])`——字段真名是 `permission_denials`，
取不到就**静默**回默认空列表，于是**两侧都**量出「没有拒绝」，base 侧那条关键读数
被抹平了。发现后改成先 `hasattr` 断言字段在、再直读，并把这条写进探子注释：
⛔ 不许再用带默认值的 `getattr` 读判据。
（本项目「验收尺子自己也要验」「假绿：判据落在『存在』上」的又一次现形。）

## 四、货 2：改尺子并说明白 + 守卫用例

### 改的那条是「语义变更打红既有用例」，不是改尺子作弊

`tests/test_m3_wiring.py:784` 原文断言 `mcp__owli_sources__source.hacker_news`（带点）。

两者的区别，按本项目一贯的分法：

- **改尺子作弊**＝实现错了，把尺子调到迁就实现，于是错的地方再也红不起来。
- **语义变更打红既有用例**＝尺子锁的正是**被替换掉的那个旧语义**，真相另有出处，
  实现和尺子一起跟着真相走。

这里是后者，判据有三：

1. 真相不在实现里，在真机与实测里——真机转录里模型调的是带下划线那个名字，
   2026-09-17 实测 SDK 暴露的也是它。尺子是照着真机改的，不是照着我的实现改的。
2. 旧断言锁的恰恰是**病根本身**。它绿着的这段时间里，「Claude 路上每一次信息源调用
   都被自家闸拒」这件事从没被打红过一次——尺子锁着错拼法，正是它把这个洞焊死的。
3. 改完之后错误**更容易**被抓到，不是更难：新加的守卫用例锁的是推导关系（见下），
   往后谁再让两头分叉都会红。

改法是替换断言值 + 在用例里写清上面这件事，⛔ 没删断言、⛔ 没放宽断言。

### 新增 `tests/test_d080_tool_name_whitelist.py`（6 条）

- `白名单项用下划线不用点`：对得上真机的那个名字。
- `逻辑工具名仍然带点`：`source.<id>` 全线不许跟着改。
- `sdk_改写规则按实测逐字符替换`：上面 14 条实测读数逐条回放。
  ⚠️ 这条就是「⛔ 不许按单一样例硬编」的守卫——按 slugify 写会在这里红三条。
- `白名单项与注册名同源`：白名单项必须 ==「注册名过一遍 SDK 改写」。
- `注册名与白名单项确实来自同一个函数`：直接去问 `_tool_definition`（服务端建工具清单
  用的那个函数），确认它注册的名字就是 `registered_tool_name()` 的返回值。
  ⚠️ 上一条只证明「白名单由某个 `source.<id>` 推导」，证明不了**服务端真按这个名字注册**；
  少了这一条，守卫守的还是两份各自为政的字面量——§D-080 分叉的正是这个接缝。
- `白名单项落在 sdk 允许的字符集里`：拼出集外字符等于必被拒。

## 五、红绿两侧

新/改用例先在 base（6803857，把 `app/adapters/source_mcp.py` stash 掉）上真红过一次，
并读了被判红的原文确认红的是这件事：

```
>       assert "mcp__owli_sources__source_hacker_news" in options.allowed_tools
E       AssertionError: assert 'mcp__owli_sources__source_hacker_news' in
        ['Edit', 'MultiEdit', 'NotebookEdit', 'Write', 'mcp__owli_sources__source.hacker_news']
```

红得正是这件事：base 的 `allowed_tools` 里躺着的是**带点**那个，模型要用的**带下划线**那个不在里面。

`tests/test_d080_tool_name_whitelist.py` 在 base 上是收集期就红（红的也是这件事）：

```
E   ImportError: cannot import name 'registered_tool_name' from 'app.adapters.source_mcp'
```

base 上根本没有「同源推导」这个东西——两头各写各的字面量，正是病根。

| | base 6803857 | head |
|---|---|---|
| `tests/test_m3_wiring.py` | **1 failed**, 16 passed（exit=1） | 全绿 |
| `tests/test_d080_tool_name_whitelist.py` | **collection ERROR**（exit=2） | 6 passed |

## 六、pytest 全量

⛔ 未用管道、⛔ 未用 `-q -q`，落盘后读 exit：

```
2240 passed, 3 skipped in 33.22s
exit=0
```

base 基线是 `2234 passed / 3 skipped`（rebase 后本包开工前实测，exit=0）。
+6 = 本包新增的 6 条，⛔ 无用例被删、无用例被跳过。

## 七、挂账与提醒

1. **Codex 路没被这件事咬过，也没被这次改动碰到**：Codex 侧走 `codex_mcp_args` /
   `mcp_servers.owli_sources.*` 配置，用的是逻辑名 `source.<id>`，本包一个字没动。
   真机里「采集章只有跑在 Codex 上才取得到数」与这个吻合。
2. **`app/adapters/claude.py` 没改**，所以 §D-074 的让路逻辑一行没动；这次修的是让路
   落地那一头的死路。让路 + 修好的白名单要合起来才算两条腿，⚠️ 但**本包没有整跑证据**——
   「Claude 路真能采到数」目前只到桩真机这一层，真机复验建议挂到下一次整跑里顺带看。
3. 加源时的提醒：源 id 里只要出现 `[A-Za-z0-9_-]` 之外的字符（比如点、空格、中文），
   暴露名会被逐字符改写，逻辑名和暴露名的字形差距会更大。现在两头同源了不会再分叉，
   但 `tests/test_d080_tool_name_whitelist.py` 那条字符集断言值得在加源 checklist 里留一眼。
