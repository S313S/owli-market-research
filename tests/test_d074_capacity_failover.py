"""§D-074：引擎报「容量上限」要换一家重试，不在满负荷那家原地重试到片失败。

真机 09-16 16:2x（r-20271e8a5028 咨询体正式稿「关键发现」shard-1），
``goals/polished/consulting-parts.transcript.jsonl`` seq 123/124/127/128 连着两轮：

    {"engine": "Codex", "event": {"type": "error",
     "message": "Selected model is at capacity. Please try a different model."}}
    {"engine": "Codex", "event": {"type": "turn.failed", "error": {"message": 同上}}}

两次 attempt 全落在同一家满负荷的 Codex 上，片没写出来 ⇒ 按 §D-051「片失败节不判
done」⇒ 整轮中止，只写出 01-执行摘要.md。同一句话在这一轮的 goal-1/3/4/5 也各撞到，
不是正式稿一处的事。

夹具串**逐字**取自转录原文（连同 ``turn.failed`` 那种把原话嵌在 error.message 里的
形态），⛔ 不自造一个更好认的措辞来迁就代码。回归锁那条用的也是同一轮的真实报文
「Reconnecting... (stream disconnected before completion: tls handshake eof)」——
传输抖动自己会回来，它不该把任务从这一家赶走。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.adapters.events import ItemKind, NormalizedEvent, normalize_codex_event
from app.adapters.routing import RoutedAdapter

#: 转录原文，逐字。
CAPACITY = "Selected model is at capacity. Please try a different model."
#: 同一轮里真实出现过的非容量类错误（传输抖动，Codex 自己 Reconnecting）。
TRANSPORT = (
    "Reconnecting... 2/5 (stream disconnected before completion: tls handshake eof)"
)

RESEARCH_ID = "r-20271e8a5028"


def _codex_error(message: str) -> NormalizedEvent:
    """走真归一路径：`{"type": "error", "message": ...}` 就是转录里那一行。"""

    return normalize_codex_event({"type": "error", "message": message})[0]


def _codex_turn_failed(message: str) -> NormalizedEvent:
    """转录里紧跟着的第二种形态：原话嵌在 `error.message` 里。"""

    return normalize_codex_event(
        {"type": "turn.failed", "error": {"message": message}}
    )[0]


def _claude_error(message: str) -> NormalizedEvent:
    """Claude 侧同款错误：`_assistant_events` 对 message.error 就是这样归一的。"""

    return NormalizedEvent(
        engine="Claude", thread_id=RESEARCH_ID, turn_id=None,
        item_kind=ItemKind.ERROR, text=message, is_error=True,
        raw={"error": message},
    )


class _Engine:
    """按剧本吐事件的假引擎，只记自己被叫到几次。"""

    def __init__(self, name: str, script: list[list[NormalizedEvent]]) -> None:
        self.name = name
        self._script = script
        self.calls = 0

    async def run(self, task: Any, ctx: Any, *, on_event: Any = None) -> Any:
        self.calls += 1
        index = min(self.calls - 1, len(self._script) - 1) if self._script else None
        events = list(self._script[index]) if index is not None else []
        for event in events:
            if on_event is not None:
                await on_event(event)
        # 判据落在产物上：报了错就当这一轮没写出来，与 polish 的 `_write_target` 同口径。
        return SimpleNamespace(succeeded=not events, events=events)


def _task(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        research_id=RESEARCH_ID, goal_id="polished", agent_id="report-polisher",
        agent_kind="report_writing", user_override=None, capability=None,
        output_path=tmp_path / "02-关键发现.shard-1.md",
    )


def _adapter(claude: _Engine, codex: _Engine) -> RoutedAdapter:
    return RoutedAdapter(adapters={"claude": claude, "codex": codex})


async def _attempts(adapter: RoutedAdapter, task: Any, count: int) -> list[Any]:
    """照 polish 的重试路连着起 N 次——一次 attempt 一次 `adapter.run`。"""

    return [await adapter.run(task, SimpleNamespace()) for _ in range(count)]


def test_容量上限命中即换引擎_下一次尝试不落在满负荷那家(tmp_path):
    # 真机方向：report_writing 默认 claude，本片是被让路机制交给 Codex 的。
    claude = _Engine("claude", [[]])
    codex = _Engine("codex", [[_codex_error(CAPACITY), _codex_turn_failed(CAPACITY)]])
    adapter = _adapter(claude, codex)
    adapter.request_alternate(RESEARCH_ID)
    task = _task(tmp_path)

    results = asyncio.run(_attempts(adapter, task, 2))

    # 第 1 次落在满负荷的 Codex 上并报容量上限——这一次和修前一样。
    assert codex.calls == 1
    assert results[0].succeeded is False
    # 修前：第 2 次 attempt 还在 Codex 上（codex.calls == 2 / claude.calls == 0），
    # 于是两次 attempt 同样报错、片没写出来。修后：换到另一家，一次就写出来了。
    assert claude.calls == 1
    assert codex.calls == 1
    assert results[1].succeeded is True
    assert adapter.route_override_for(RESEARCH_ID) == "claude"


def test_两家都满不再让路_按原有失败路径收场不来回倒(tmp_path):
    claude = _Engine("claude", [[_claude_error(CAPACITY)]])
    codex = _Engine("codex", [[_codex_error(CAPACITY)]])
    adapter = _adapter(claude, codex)
    adapter.request_alternate(RESEARCH_ID)
    task = _task(tmp_path)

    results = asyncio.run(_attempts(adapter, task, 4))

    # 一次 run 只付一次引擎：让路不在适配层里自己再跑一轮，失败照样交回调用方。
    assert codex.calls + claude.calls == 4
    assert all(result.succeeded is False for result in results)
    # 让路只发生一次：Codex 满了换到 Claude，Claude 也满了就**停在那儿**，
    # ⛔ 不在两家之间来回倒（那会把每一次重试都变成一次换家）。
    assert codex.calls == 1
    assert claude.calls == 3
    assert adapter.route_override_for(RESEARCH_ID) == "claude"


def test_非容量类错误不触发让路_路由逐字不变(tmp_path):
    claude = _Engine("claude", [[]])
    codex = _Engine("codex", [[_codex_error(TRANSPORT), _codex_turn_failed(TRANSPORT)]])
    adapter = _adapter(claude, codex)
    adapter.request_alternate(RESEARCH_ID)
    task = _task(tmp_path)

    asyncio.run(_attempts(adapter, task, 3))

    # 传输抖动自己会 Reconnecting 回来，不是「这一家满了」——三次都留在 Codex。
    assert codex.calls == 3
    assert claude.calls == 0
    assert adapter.route_override_for(RESEARCH_ID) is None


def test_容量上限不是永久不可用_跑通一轮后让路额度还回来(tmp_path):
    # 「两家都满」的记性只管这一串连着的失败：中间有一轮跑通，说明容量回来了，
    # ⛔ 不能因为半小时前两家都满过，就再也不给这个研究让路了。
    claude = _Engine("claude", [[_claude_error(CAPACITY)], [], [_claude_error(CAPACITY)]])
    codex = _Engine("codex", [[_codex_error(CAPACITY)], []])
    adapter = _adapter(claude, codex)
    adapter.request_alternate(RESEARCH_ID)
    task = _task(tmp_path)

    asyncio.run(_attempts(adapter, task, 2))       # codex 满 → claude 满
    assert adapter.route_override_for(RESEARCH_ID) == "claude"

    asyncio.run(_attempts(adapter, task, 1))       # 第 3 次：claude 跑通，记性清掉
    assert claude.calls == 2

    asyncio.run(_attempts(adapter, task, 1))       # 第 4 次：claude 又满 → 该换回 codex
    assert adapter.route_override_for(RESEARCH_ID) == "codex"
    asyncio.run(_attempts(adapter, task, 1))
    assert codex.calls == 2
