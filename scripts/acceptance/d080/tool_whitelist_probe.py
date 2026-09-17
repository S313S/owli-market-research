#!/usr/bin/env python3
"""§D-080 货 1 判据：Claude 路上的信息源调用到底过不过得了自家闸。

⚠️ **判据落在产物上，不落在 diff 上**。只改一行字符串然后看 diff，证明不了
「模型按 SDK 给的那个名字调用时，闸会放行、工具会真的跑起来」——中间还隔着
`_claude_capability` 翻译、`build_claude_options` 的 allowed_tools、
`make_permission_callback` 的判定、以及 `SourceToolAdapter` 那一层。本脚本把这一段
接上，形制照抄 `scripts/acceptance/d074/live_failover_probe.py`：**真适配器 + 真事件
协议，只换「服务端答什么」**。

真在哪、桩在哪：

- **真的** `app.adapters.claude.ClaudeAdapter.run()`，连同真的 `make_permission_callback`、
  真的 `build_claude_options`、真的 transcript 落盘与事件归一。
- **真的** `app.adapters.source_mcp.SourceToolAdapter.call()`——闸放行之后，工具是真的
  被调起来的，不是「假装调了一下」。
- **桩**：Claude 走进程内 SDK，没有可替换的可执行体，「换服务端答什么」只能换到 SDK 这一层
  （与 §D-074-fu 同一处取舍）。桩 SDK 干的事就是真 CLI 干的事——按 `mcp__<server>__<tool>`
  这个名字发起工具调用，问一次 `can_use_tool`，然后照答复行事。
- **桩**：信息源实现换成一个记账用的假源（⛔ 不联网、不起真引擎、不写留服库）。
  被验的是「闸放不放行」，不是「HN 今天有没有新帖」。

桩 SDK 用的工具名 `mcp__owli_sources__source_hacker_news` 不是自造的好认措辞，两处实证：
① 真机转录 `r-96e0257a86b4` goal-1/ch-13 里模型调的就是这个名字（也正是被拒的那个）；
② 2026-09-17 拿真 CLI + 真 stdio MCP server 量过一次 `system/init` 的 tools 清单，
   `source.hacker_news` 暴露出来就是它（实测表见 `app/adapters/source_mcp.py`）。

两侧都要跑（⛔ 只有绿的一侧不算数）：

    python scripts/acceptance/d080/tool_whitelist_probe.py --code head
    python scripts/acceptance/d080/tool_whitelist_probe.py --code base

`--code base` 把 base 的 `source_mcp.py` 原样 `git show` 出来当模块加载，只把
`app.adapters.claude` 里那一个 `exposed_tool_name` 换成 base 的版本（⛔ 不动工作树）。
别的一切完全相同——所以两侧读数之差只可能来自这一处拼法。

沙盒：每次跑都在临时目录里新建 runs 根与日志根，⛔ 不碰 `var/runs`、不写留服库。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

#: §D-080 的 base：那时候白名单项还带着点。
BASE_COMMIT = "6803857"

#: 真机 `r-96e0257a86b4` goal-1/ch-13 里模型调的那个名字，逐字。
REAL_EXPOSED_TOOL = "mcp__owli_sources__source_hacker_news"

#: 被拒时闸吐的那句话，逐字（`app/adapters/claude.py` 里的 f-string）。
DENY_MARKER = "工具不在 capability 白名单"

RESEARCH_ID = "r-96e0257a86b4"
GOAL_ID = "goal-1"
AGENT_ID = "data-collection"
SOURCE_ID = "hacker_news"


# --- 桩信息源：只记账，不联网 --------------------------------------------------


class StubSource:
    """假源：记下自己被调了几次、拿什么词调的，返回两行固定证据。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, query: str, window: str, on_event: Any = None) -> list:
        self.calls.append((query, window))
        return [
            {
                "permalink": f"https://news.ycombinator.com/item?id=d080-{index}",
                "title": f"{query} 桩证据 {index}",
            }
            for index in (1, 2)
        ]


# --- 桩 SDK：干真 CLI 干的事 ---------------------------------------------------


def build_stub_sdk(
    *,
    output_path: Path,
    source: StubSource,
    log: dict[str, Any],
) -> Any:
    """按真 CLI 的行为答话：拿 SDK 暴露名发起工具调用 → 问闸 → 照答复行事。

    ⛔ 桩里不做任何判定：放行还是拒，全由真的 `can_use_tool` 说了算；
    桩只负责把「模型真会用哪个名字」和「被放行之后工具真会跑」这两截接上。
    """

    class TextBlock:
        def __init__(self, text: str) -> None:
            self.text = text

    class ToolUseBlock:
        def __init__(self, name: str, input: dict) -> None:  # noqa: A002
            self.id = "toolu_d080"
            self.name = name
            self.input = input

    class AssistantMessage:
        def __init__(self, content: list) -> None:
            self.content = content
            self.model = "claude-opus-4-7"
            self.error = None
            self.uuid = "stub-assistant"

    class UserMessage:
        def __init__(self, content: list) -> None:
            self.content = content
            self.uuid = "stub-user"

    class SystemMessage:
        def __init__(self, subtype: str, data: dict) -> None:
            self.subtype = subtype
            self.data = data

    class ResultMessage:
        def __init__(self, result: str) -> None:
            self.subtype = "success"
            self.result = result
            self.is_error = False
            self.session_id = "stub-session-d080"
            self.usage = {"input_tokens": 1, "output_tokens": 1}
            self.total_cost_usd = 0.0
            self.structured_output = None

    class FakeOptions:
        def __init__(self, **values: Any) -> None:
            self.values = values
            self.__dict__.update(values)

    class Allow:
        def __init__(self, **values: Any) -> None:
            self.__dict__.update(values)

    class Deny:
        def __init__(self, **values: Any) -> None:
            self.message = values.get("message", "")

    class FakeHookMatcher:
        def __init__(self, matcher: Any = None, hooks: Any = None) -> None:
            self.matcher = matcher
            self.hooks = hooks or []

    class FakeClient:
        def __init__(self, options: Any) -> None:
            self.options = options

        async def connect(self, prompt: Any) -> None:
            """真 CLI 在这一步起会话、把工具清单给模型、模型发起调用。"""

            values = getattr(self.options, "values", {})
            log["allowed_tools"] = sorted(
                item
                for item in (values.get("allowed_tools") or [])
                if str(item).startswith("mcp__")
            )
            can_use_tool = values.get("can_use_tool")
            arguments = {"query": "hacker news 上的产品讨论", "window": "30d"}

            verdict = await can_use_tool(REAL_EXPOSED_TOOL, arguments, None)
            denied = type(verdict).__name__ == "Deny"
            log["permission_verdict"] = "deny" if denied else "allow"
            log["permission_message"] = str(getattr(verdict, "message", "") or "")

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if denied:
                # 真机病象逐字复刻：闸拒 → 写手不绕道 → 落盘 `[]`。
                output_path.write_text("[]", encoding="utf-8")
                log["source_invoked"] = False
                return

            # 放行之后，工具是真的被调起来的——走真的 SourceToolAdapter。
            from app.adapters.source_mcp import SourceToolAdapter, registered_tool_name

            adapter = SourceToolAdapter({registered_tool_name(SOURCE_ID): source})
            rows = await adapter.call(
                registered_tool_name(SOURCE_ID),
                str(arguments["query"]),
                str(arguments["window"]),
                research_id=RESEARCH_ID,
                goal_id=GOAL_ID,
                agent_id=AGENT_ID,
                capability=SimpleNamespace(
                    tools=(registered_tool_name(SOURCE_ID),),
                    sources=(SOURCE_ID,),
                    network="sources_only",
                ),
                on_event=None,
                with_comments="off",
            )
            log["source_invoked"] = True
            log["source_rows"] = len(rows or [])
            output_path.write_text(
                json.dumps(rows, ensure_ascii=False), encoding="utf-8"
            )

        async def receive_response(self):
            yield SystemMessage("init", {"type": "system", "subtype": "init"})
            yield AssistantMessage(
                [ToolUseBlock(REAL_EXPOSED_TOOL, {"query": "d080"})]
            )
            yield ResultMessage(_owli_result_block(output_path, log))

        async def disconnect(self) -> None:
            return None

        async def interrupt(self) -> None:
            return None

    class FakeSdk:
        ClaudeSDKClient = FakeClient
        ClaudeAgentOptions = FakeOptions
        AssistantMessage = None
        UserMessage = None
        SystemMessage = None
        ResultMessage = None
        TextBlock = None
        ToolUseBlock = None
        PermissionResultAllow = Allow
        PermissionResultDeny = Deny
        HookMatcher = FakeHookMatcher

    FakeSdk.AssistantMessage = AssistantMessage
    FakeSdk.UserMessage = UserMessage
    FakeSdk.SystemMessage = SystemMessage
    FakeSdk.ResultMessage = ResultMessage
    FakeSdk.TextBlock = TextBlock
    FakeSdk.ToolUseBlock = ToolUseBlock
    return FakeSdk


def _owli_result_block(output_path: Path, log: dict[str, Any]) -> str:
    denied = log.get("permission_verdict") == "deny"
    payload = {
        "status": "blocked" if denied else "done",
        "output_path": str(output_path),
        "summary": "桩写手：闸拒了，没取到数" if denied else "桩写手：取到了证据",
        "assumptions": [],
        "unmet": ["tool_unavailable"] if denied else [],
        "capability_denials": [REAL_EXPOSED_TOOL] if denied else [],
        "reason": "tool_unavailable" if denied else None,
    }
    return "```json owli-result\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


# --- 被验的那一处拼法：head（工作树）/ base（原样取出） -------------------------


def install_exposed_tool_name(which: str) -> str:
    """把 `app.adapters.claude` 用的 `exposed_tool_name` 换成要验的那一版。

    `base` 走 `git show`，把 base 的 `source_mcp.py` 原样写到临时文件当模块加载。
    ⛔ 不动工作树里的任何文件（本包这一步是验证，不是二次修）。
    """

    import app.adapters.claude as claude_module

    if which == "head":
        from app.adapters.source_mcp import exposed_tool_name

        claude_module.exposed_tool_name = exposed_tool_name
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, check=True,
        ).stdout.strip()
        return f"工作树（HEAD={head}，含未提交改动）"

    source = subprocess.run(
        ["git", "show", f"{BASE_COMMIT}:app/adapters/source_mcp.py"],
        cwd=str(ROOT), capture_output=True, text=True, check=True,
    ).stdout
    directory = Path(tempfile.mkdtemp(prefix="d080-base-source-mcp-"))
    path = directory / "base_source_mcp.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("d080_base_source_mcp", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    claude_module.exposed_tool_name = module.exposed_tool_name
    return f"{BASE_COMMIT}:app/adapters/source_mcp.py"


# --- 跑一次 -------------------------------------------------------------------


async def probe(which: str, sandbox: Path) -> dict[str, Any]:
    from app.adapters.capability import Capability, FileSystemScope
    from app.adapters.claude import ClaudeAdapter
    from app.adapters.contracts import EngineTask
    from app.adapters import validation as artifact_validation

    which_label = install_exposed_tool_name(which)

    runs_root = sandbox / "runs"
    artifact_validation.RUNS_ROOT = runs_root
    output = runs_root / RESEARCH_ID / "goals" / GOAL_ID / "evidence.json"

    task = EngineTask(
        body="必须调用 source.hacker_news 采集",
        output_path=output,
        output_format="json",
        research_id=RESEARCH_ID,
        goal_id=GOAL_ID,
        agent_id=AGENT_ID,
        agent_kind="data_collection",
        validators=["file_exists"],
        capability=Capability(
            tools=(f"source.{SOURCE_ID}", "fs.write"),
            sources=(SOURCE_ID,),
            fs=FileSystemScope(write=(f"goals/{GOAL_ID}/**",)),
            network="sources_only",
        ),
    )

    log: dict[str, Any] = {}
    source = StubSource()
    sdk = build_stub_sdk(output_path=output, source=source, log=log)
    adapter = ClaudeAdapter(sdk=sdk, log_root=sandbox / "logs")

    ctx = artifact_validation.Ctx(
        output_path=output,
        output_format="json",
        research_id=RESEARCH_ID,
        goal_id=GOAL_ID,
        agent_id=AGENT_ID,
        read_text=lambda: output.read_text(encoding="utf-8"),
        read_json=lambda: json.loads(output.read_text(encoding="utf-8")),
        store=None,
        source_domains=frozenset(),
        runs_root=runs_root,
    )
    result = await adapter.run(task, ctx)

    # ⚠️ 字段名是 `permission_denials`。这里一开始写的是 `getattr(result, "denials", [])`，
    # 取不到就**静默**回默认空列表——两侧都量出「没有拒绝」，等于把尺子自己量废了
    # （本项目「验收尺子自己也要验」的又一次现形）。⛔ 不许再用带默认值的 getattr。
    if not hasattr(result, "permission_denials"):
        raise AssertionError(
            "EngineRunResult 没有 permission_denials 字段——尺子和被测代码对不上，"
            "先核字段名再谈读数"
        )
    denials = list(result.permission_denials or [])
    written = output.read_text(encoding="utf-8") if output.is_file() else ""
    return {
        "被验代码": which_label,
        "白名单里的 mcp 工具": log.get("allowed_tools", []),
        "模型调用的工具名": REAL_EXPOSED_TOOL,
        "闸的判决": log.get("permission_verdict"),
        "闸的原话": log.get("permission_message", ""),
        f"出现「{DENY_MARKER}」": DENY_MARKER in log.get("permission_message", ""),
        "真适配器记下的 denials": denials,
        "信息源真被调用到": bool(log.get("source_invoked")),
        "桩源收到的调用": source.calls,
        "落盘产物": written[:120],
        "落盘是空数组": written.strip() == "[]",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", choices=("head", "base"), required=True)
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="d080-probe-") as raw:
        sandbox = Path(raw)
        os.environ["OWLI_LOG_ROOT"] = str(sandbox / "logs")
        readout = asyncio.run(probe(args.code, sandbox))

    print(f"=== §D-080 探子 · --code {args.code} ===")
    for key, value in readout.items():
        print(f"{key}: {value!r}")

    denied = readout["闸的判决"] == "deny"
    if args.code == "base":
        ok = (
            denied
            and readout[f"出现「{DENY_MARKER}」"]
            and REAL_EXPOSED_TOOL in readout["真适配器记下的 denials"]
            and not readout["信息源真被调用到"]
            and readout["落盘是空数组"]
        )
        print(f"\n判据（base 侧必须量出「有拒绝」）：{'符合' if ok else '不符合'}")
    else:
        ok = (
            not denied
            and not readout[f"出现「{DENY_MARKER}」"]
            and not readout["真适配器记下的 denials"]
            and readout["信息源真被调用到"]
            and readout["桩源收到的调用"]
            and not readout["落盘是空数组"]
        )
        print(f"\n判据（head 侧必须「无拒绝」且工具真被调用到）：{'符合' if ok else '不符合'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
