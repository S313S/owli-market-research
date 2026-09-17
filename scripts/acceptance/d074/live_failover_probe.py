#!/usr/bin/env python3
"""§D-074-fu 货 1：桩引擎真机联通验——真适配器 + 真 CLI 事件协议，只换「服务端答什么」。

§D-074 的判据全落在单测的假适配器上（`tests/test_d074_capacity_failover.py` 里
那个 `_Engine` 类）。假适配器证明的是「`RoutedAdapter` 的分支写对了」，证明不了
「真的 `CodexAdapter` 吐出真的 CLI 事件时，这条分支会被走到」——中间还隔着
子进程、JSONL 解析、`ratelimit.route`、`normalize_codex_event`、transcript 落盘
一整条管道。本脚本把那一段接上：

- **真的** `app.adapters.codex.CodexAdapter`，只把 `executable` 指到一个桩可执行体；
  桩逐字吐 2026-09-16 真机转录 `r-20271e8a5028` seq 118–124 那几行（含 `at capacity`
  的 `error` 与 `turn.failed` 两种形态），⛔ 没自造更好认的措辞。
- **真的** `app.adapters.claude.ClaudeAdapter`，只把 `sdk` 换成按剧本答话的替身
  （Claude 侧走的是进程内 SDK，没有可替换的可执行体，「换服务端答什么」只能换到这一层）。
- **真的** `RoutedAdapter`，两次 attempt = 两次 `adapter.run`（与 polish 的重试路同口径）。
- 判据不读日志文字、不读 `_Engine.calls`，**读 transcript 落盘的 `engine` 字段**——
  跟 09-16 那次诊断病象用的是同一把尺子、同一个文件形态。

两侧都要跑（⛔ 只有绿的一侧不算数）：

    python scripts/acceptance/d074/live_failover_probe.py --routing head
    python scripts/acceptance/d074/live_failover_probe.py --routing base

`--routing base` 把 base 075c0f6 的 `routing.py` 原样取出来当模块加载（⛔ 不动工作树
里的 `app/adapters/routing.py`），别的一切完全相同——所以两侧读数之差只可能来自路由代码。

沙盒：每次跑都在临时目录里新建 runs 根、CODEX_HOME 与日志根，⛔ 不写任何留服库、
不碰 `var/runs`、不联网、不起真引擎。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

#: §D-074 本体的 base：那时候「容量上限」还没人认。
BASE_COMMIT = "075c0f6"

#: 真机转录原文，逐字。`../Owli-wx1/var/runs/r-20271e8a5028/goals/polished/
#: consulting-parts.transcript.jsonl` seq 123/124 的 message。
CAPACITY = "Selected model is at capacity. Please try a different model."

#: 桩 codex 每次被调起时吐的整串，逐字对应真机 seq 118–124：
#: 两行非 JSON 的 stderr 噪声（真机里 stderr 并进了 stdout）、thread.started、
#: turn.started、一条无关的 item.completed 告警，然后才是容量上限的两种形态。
STUB_CODEX_LINES = [
    "2026-09-16T08:24:33.160181Z ERROR codex_models_manager::manager: "
    "failed to refresh available models: timeout waiting for child process to exit",
    "2026-09-16T08:24:33.183270Z ERROR codex_models_manager::manager: "
    "failed to refresh available models: timeout waiting for child process to exit",
    json.dumps({
        "type": "thread.started",
        "thread_id": "01a0a951-5d7d-7600-8d8d-4fcd636b4093",
    }),
    json.dumps({"type": "turn.started"}),
    json.dumps({
        "type": "item.completed",
        "item": {
            "id": "item_0",
            "type": "error",
            "message": (
                "Skill descriptions were shortened to fit the skills context budget. "
                "Codex can still see every skill, but some descriptions are shorter. "
                "Disable unused skills or plugins to leave more room for the rest."
            ),
        },
    }),
    json.dumps({"type": "error", "message": CAPACITY}),
    json.dumps({"type": "turn.failed", "error": {"message": CAPACITY}}),
]

RESEARCH_ID = "r-20271e8a5028"
GOAL_ID = "polished"
AGENT_ID = "report-polisher"
OUTPUT_NAME = "02-关键发现.shard-1.md"


# --- 桩 codex 可执行体 --------------------------------------------------------


def write_stub_codex(path: Path) -> None:
    """桩 codex：不看任何参数，按剧本逐行吐真机原文，然后 0 退出。

    ⛔ 不写产物——真机那两轮也没写出来（片失败正是病象本身）。
    """

    payload = json.dumps(STUB_CODEX_LINES, ensure_ascii=False)
    source = (
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"LINES = json.loads({payload!r})\n"
        "for line in LINES:\n"
        "    print(line, flush=True)\n"
        "sys.exit(0)\n"
    )
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


# --- 桩 claude SDK ------------------------------------------------------------


def _owli_result_block(output_path: Path) -> str:
    payload = {
        "status": "done",
        "output_path": str(output_path),
        "summary": "桩引擎：让路后的这一次尝试写出了片",
        "assumptions": [],
        "unmet": [],
        "capability_denials": [],
        "reason": None,
    }
    return "```json owli-result\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def build_stub_sdk(output_path: Path) -> Any:
    """按剧本答话的 Claude SDK 替身：写出产物并给一份合法 owli-result。

    只替换「服务端答什么」：`ClaudeAdapter` 的 options 组装、permission 回调、
    transcript 落盘、事件归一、双腿判定全部还是真代码。
    """

    class TextBlock:
        def __init__(self, text: str) -> None:
            self.text = text

    class ToolUseBlock:
        def __init__(self, name: str, input: dict) -> None:  # noqa: A002
            self.id = "toolu_stub"
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
            self.session_id = "stub-session"
            self.usage = {"input_tokens": 1, "output_tokens": 1}
            self.total_cost_usd = 0.0
            self.structured_output = None

    class FakeOptions:
        def __init__(self, **values: Any) -> None:
            self.values = values

    class FakeClient:
        def __init__(self, options: Any) -> None:
            self.options = options

        async def connect(self, prompt: Any) -> None:
            # 真机这一步是 CLI 起会话；桩直接把「写手写出了片」这件事做掉。
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                "## 关键发现（桩引擎写出的占位正文）\n", encoding="utf-8"
            )

        async def receive_response(self):
            yield SystemMessage("init", {"type": "system", "subtype": "init"})
            yield AssistantMessage([TextBlock(_owli_result_block(output_path))])
            yield ResultMessage(_owli_result_block(output_path))

        async def disconnect(self) -> None:
            return None

    class Allow:
        pass

    class Deny:
        def __init__(self, **values: Any) -> None:
            self.message = values.get("message", "")

    class FakeHookMatcher:
        def __init__(self, matcher: Any = None, hooks: Any = None) -> None:
            self.matcher = matcher
            self.hooks = hooks or []

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


# --- 路由代码：head（工作树）/ base（075c0f6 原样取出） -------------------------


def load_routed_adapter(which: str):
    """返回要被验的 `RoutedAdapter` 类。

    `base` 走 `git show`，把 075c0f6 的 `routing.py` 原样写到临时文件当模块加载。
    ⛔ 不动工作树里的 `app/adapters/routing.py`（本包是验证，不是二次修）。
    """

    if which == "head":
        from app.adapters.routing import RoutedAdapter

        return RoutedAdapter, _describe_head()
    source = subprocess.run(
        ["git", "show", f"{BASE_COMMIT}:app/adapters/routing.py"],
        cwd=str(ROOT), capture_output=True, text=True, check=True,
    ).stdout
    directory = Path(tempfile.mkdtemp(prefix="d074fu-base-routing-"))
    path = directory / "base_routing.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("d074fu_base_routing", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    marker = "有" if "_CAPACITY_MARKERS" in source else "无"
    return module.RoutedAdapter, f"{BASE_COMMIT}:app/adapters/routing.py（容量标记：{marker}）"


def _describe_head() -> str:
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(ROOT), capture_output=True, text=True, check=True,
    ).stdout.strip()
    source = (ROOT / "app" / "adapters" / "routing.py").read_text(encoding="utf-8")
    marker = "有" if "_CAPACITY_MARKERS" in source else "无"
    return f"{head}:app/adapters/routing.py（工作树，容量标记：{marker}）"


# --- 场景 --------------------------------------------------------------------


def _build_task(runs_root: Path):
    from app.adapters.capability import Capability, FileSystemScope
    from app.adapters.contracts import EngineTask

    goal_root = runs_root / RESEARCH_ID / "goals" / GOAL_ID
    return EngineTask(
        body="写「关键发现」shard-1。",
        output_path=goal_root / OUTPUT_NAME,
        output_format="markdown",
        research_id=RESEARCH_ID,
        goal_id=GOAL_ID,
        agent_id=AGENT_ID,
        # 真机方向：report_writing 默认 claude，本片是被让路机制交给 Codex 的。
        agent_kind="report_writing",
        validators=["file_exists"],
        capability=Capability(
            tools=("fs.write",),
            fs=FileSystemScope(write=(f"goals/{GOAL_ID}/**",)),
        ),
        runs_root=runs_root,
    )


def _build_ctx(task, runs_root: Path):
    from app.adapters import validation

    output_path = task.output_path
    return validation.Ctx(
        research_id=RESEARCH_ID,
        goal_id=GOAL_ID,
        agent_id=AGENT_ID,
        output_path=output_path,
        output_format="markdown",
        read_text=lambda: output_path.read_text(encoding="utf-8"),
        read_json=lambda: json.loads(output_path.read_text(encoding="utf-8")),
        store=None,
        source_domains=frozenset(),
        runs_root=runs_root,
    )


def _transcript_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def run_scenario(routing: str, workspace: Path, attempts: int = 2) -> dict:
    from app.adapters import validation
    from app.adapters.claude import ClaudeAdapter
    from app.adapters.codex import CodexAdapter
    from app.adapters.transcript import transcript_path

    routed_class, routing_desc = load_routed_adapter(routing)

    runs_root = workspace / "runs"
    logs_root = workspace / "logs"
    codex_home = workspace / "codex-home"
    stub = workspace / "stub-codex"
    write_stub_codex(stub)

    task = _build_task(runs_root)
    ctx = _build_ctx(task, runs_root)
    path = transcript_path(task)

    codex = CodexAdapter(
        executable=str(stub),
        codex_home=codex_home,
        log_root=logs_root,
        timeout_seconds=60.0,
    )
    claude = ClaudeAdapter(
        sdk=build_stub_sdk(task.output_path),
        log_root=logs_root,
        timeout_seconds=60.0,
    )
    adapter = routed_class(adapters={"claude": claude, "codex": codex})
    adapter.request_alternate(RESEARCH_ID)

    per_attempt: list[dict] = []

    async def scenario() -> None:
        for index in range(attempts):
            before = len(_transcript_rows(path))
            result = await adapter.run(task, ctx)
            rows = _transcript_rows(path)
            fresh = rows[before:]
            engines = sorted({str(row.get("engine")) for row in fresh})
            per_attempt.append({
                "attempt": index + 1,
                "transcript_engines": engines,
                "transcript_seq": [row.get("seq") for row in fresh],
                "capacity_lines": sum(
                    1 for row in fresh if CAPACITY in json.dumps(
                        row.get("event"), ensure_ascii=False
                    )
                ),
                "succeeded": bool(getattr(result, "succeeded", False)),
            })
            # 每次 attempt 前清掉上一次的产物，两次 attempt 站同一条起跑线。
            if index + 1 < attempts and task.output_path.is_file():
                task.output_path.unlink()

    asyncio.run(scenario())

    rows = _transcript_rows(path)
    return {
        "routing": routing,
        "routing_source": routing_desc,
        "transcript": str(path),
        "attempts": per_attempt,
        "route_override": adapter.route_override_for(RESEARCH_ID),
        "transcript_rows": len(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="§D-074-fu 货 1 桩引擎真机联通验")
    parser.add_argument(
        "--routing", choices=("head", "base"), default="head",
        help="head=工作树的 routing.py；base=075c0f6 原样取出（造红一侧）",
    )
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument(
        "--keep", action="store_true", help="保留沙盒目录（默认跑完就删）"
    )
    parser.add_argument("--json", action="store_true", help="只打 JSON")
    args = parser.parse_args()

    workspace = Path(tempfile.mkdtemp(prefix=f"d074fu-{args.routing}-"))
    try:
        report = run_scenario(args.routing, workspace, attempts=args.attempts)
    finally:
        if not args.keep:
            shutil.rmtree(workspace, ignore_errors=True)

    engines = [
        attempt["transcript_engines"] for attempt in report["attempts"]
    ]
    flat = [item[0] if len(item) == 1 else "/".join(item) for item in engines]
    report["verdict"] = (
        "failover-ok"
        if len(flat) >= 2 and flat[0] == "Codex" and flat[1] == "Claude"
        else "no-failover"
        if len(flat) >= 2 and flat[0] == "Codex" and flat[1] == "Codex"
        else "unknown"
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"路由代码：{report['routing_source']}")
    print(f"转录：{report['transcript']}（{report['transcript_rows']} 行）")
    for attempt in report["attempts"]:
        print(
            f"  attempt {attempt['attempt']}："
            f"engine={'/'.join(attempt['transcript_engines']) or '(无事件)'}"
            f" seq={attempt['transcript_seq']}"
            f" at-capacity×{attempt['capacity_lines']}"
            f" succeeded={attempt['succeeded']}"
        )
    print(f"route_override_for({RESEARCH_ID})={report['route_override']}")
    print(f"判定：{report['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
