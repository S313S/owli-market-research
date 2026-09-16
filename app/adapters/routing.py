"""R2 默认路由与适配器选择；编排层不接触引擎分支。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping

from app.adapters.contracts import PlanningSegmentRequest, PlanningSegmentResult
from app.adapters.events import ItemKind, NormalizedEvent
from app.adapters.source_mcp import (
    SourceToolAdapter,
    prepare_source_events,
    replay_source_events,
)
from app.config import ResilienceConfig, load_resilience_config


_DEFAULT_ENGINES = {
    "planning": "claude",
    # M0 固定链路兼容项：只证明路由生效，不在 M1 改写既有引擎分配。
    "m0_hn_collection": "claude",
    "goal_planning": "claude",
    "plan_arbitration": "claude",
    "audit": "claude",
    "reliability_audit": "claude",
    "cross_validation": "claude",
    "consistency_check": "claude",
    "report": "claude",
    "report_writing": "claude",
    "summary": "claude",
    "tagging": "claude",
    "code_execution": "codex",
    "excel_generation": "codex",
    "data_cleaning": "codex",
    "data_collection": "codex",
    "browser_automation": "codex",
}
_ENGINES = frozenset({"claude", "codex"})
_PLANNING_KINDS = frozenset({"planning", "goal_planning", "plan_arbitration"})
#: D-074：引擎侧「这一家现在满了」。**换一家马上能跑**，所以它既不是「这家坏了」
#: （⛔ 不进 codex.py 的 `_INFRASTRUCTURE_MARKERS`——那条路判引擎不可用、直接抛），
#: 也不是限流（⛔ 不起退避、不碰退避时钟：D-023 踩过借限流的时钟睡满五小时）。
#: 只收本项目真出现过的措辞：2026-09-16 r-20271e8a5028 全库 24 处命中，全是 Codex 的
#: 「Selected model is at capacity. Please try a different model.」。同族的
#: `overloaded` / `server_overloaded` / `service unavailable` 在本项目转录里**一次都没出现过**，
#: 没证据的不收——拿猜来的措辞去改真实路由，改错了没人量得出来。
_CAPACITY_MARKERS = ("at capacity", "please try a different model")


@dataclass(frozen=True)
class EngineSelection:
    engine: str
    origin: str


def pick_engine(agent_kind: str, user_override: str | None) -> EngineSelection:
    """按 R2 选默认引擎；显式覆盖保留 origin=user。"""

    if user_override is not None:
        selected = user_override.strip().casefold()
        if selected not in _ENGINES:
            raise ValueError(f"不支持的用户引擎覆盖：{user_override}")
        return EngineSelection(selected, "user")
    try:
        return EngineSelection(_DEFAULT_ENGINES[agent_kind], "system")
    except KeyError as exc:
        raise ValueError(f"未知 agent_kind：{agent_kind}") from exc


class RoutedAdapter:
    """在适配层内完成路由并把统一结果交回编排层。"""

    def __init__(
        self,
        *,
        utc_clock: Callable[[], datetime] | None = None,
        adapters: Mapping[str, Any] | None = None,
        source_tools: Mapping[str, Any] | None = None,
        source_store: Any = None,
        resilience_config: ResilienceConfig | None = None,
        backoff_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if adapters is None:
            from app.adapters.claude import ClaudeAdapter
            from app.adapters.codex import CodexAdapter

            adapters = {"claude": ClaudeAdapter(), "codex": CodexAdapter()}
        missing = _ENGINES - set(adapters)
        if missing:
            raise ValueError(f"缺少引擎适配器：{','.join(sorted(missing))}")
        self._adapters = dict(adapters)
        self._utc_clock = utc_clock
        self._active: Any = None
        self._route_overrides: dict[str, str] = {}
        self._last_research_id: str | None = None
        self._resilience_config = resilience_config or load_resilience_config()
        self._backoff_sleep = backoff_sleep
        self._backoff_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._backoff_counts: dict[tuple[str, str], int] = {}
        self._backoff_causes: dict[tuple[str, str], str] = {}
        self._quota_gates: dict[str, asyncio.Event] = {}
        # D-074：这一串连着的失败里，哪几家已经报过「满了」。⛔ 不是黑名单：
        # 一旦有一轮没报容量就整条清掉（见 `run` 末尾），所以它不会把引擎永久下线。
        self._capacity_engines: dict[str, set[str]] = {}
        self._manual_research_alternates: set[str] = set()
        self._manual_agent_alternates: dict[tuple[str, str], int] = {}
        self._agent_runs: dict[tuple[str, str], int] = {}
        self._source_adapter = SourceToolAdapter(source_tools, store=source_store)

    @property
    def timeout_seconds(self) -> float | None:
        """本路由下「一次引擎超时」的口径：取各适配器超时的最大值（与引擎无关）。"""

        values = [
            float(value)
            for adapter in self._adapters.values()
            if (value := getattr(adapter, "timeout_seconds", None)) is not None
        ]
        return max(values) if values else None

    @property
    def future_engine(self) -> str | None:
        """限流事件要求后续新任务让路时的适配层覆盖。"""

        return self.route_override

    @property
    def route_override(self) -> str | None:
        """返回最近一次 research 的适配层路由覆盖，仅用于观测。"""

        if self._last_research_id is None:
            return None
        return self._route_overrides.get(self._last_research_id)

    def route_override_for(self, research_id: str) -> str | None:
        """按 research 查询覆盖，避免跨 research 共享断路状态。"""

        return self._route_overrides.get(research_id)

    @staticmethod
    def _alternate(engine: str) -> str:
        return next(item for item in _ENGINES if item != engine)

    def request_alternate(
        self,
        research_id: str,
        *,
        agent_id: str | None = None,
        after_attempt: int = 0,
    ) -> None:
        """记录人工让路意图；具体目标仍只由适配层根据当前默认路由推导。"""

        if agent_id is None:
            self._manual_research_alternates.add(research_id)
            return
        self._manual_agent_alternates[(research_id, agent_id)] = max(
            0, int(after_attempt)
        )

    def release_route_gate(self, research_id: str) -> None:
        gate = self._quota_gates.pop(research_id, None)
        if gate is not None:
            gate.set()

    async def _await_route_gates(
        self, research_id: str, engine: str
    ) -> str | None:
        released_cause = None
        quota_gate = self._quota_gates.get(research_id)
        if quota_gate is not None:
            await quota_gate.wait()
        key = (research_id, engine)
        backoff = self._backoff_tasks.get(key)
        if backoff is not None:
            # D-023：用 asyncio.wait 而不是直接 await——直接 await 会在等待者被
            # 章墙钟 / stop 取消时连带 cancel 这个共享的退避任务，尸体留在表里，
            # 下一个等待者一 await 就抛 CancelledError 静默退出（整个研究冻住）。
            # asyncio.wait 只等不牵连；退避任务自己被取消也按「已释放」处理。
            if not backoff.done():
                await asyncio.wait({backoff})
            released_cause = self._backoff_causes.get(key)
            if self._backoff_tasks.get(key) is backoff:
                self._backoff_tasks.pop(key, None)
                self._backoff_causes.pop(key, None)
        return released_cause

    @staticmethod
    def _reset_at(event: Any) -> datetime | None:
        raw = getattr(event, "raw", None)
        raw = raw if isinstance(raw, Mapping) else {}
        info = raw.get("rate_limit_info") or raw.get("rateLimitInfo") or raw
        if not isinstance(info, Mapping):
            return None
        # D-023：Claude CLI 会周期性播报 status="allowed" 的 rate_limit_info，
        # 那是纯信息（额度窗口何时重置），不是限流；抖动退避不得借它的时钟睡觉。
        status = info.get("status")
        if isinstance(status, str) and status.strip().casefold() == "allowed":
            return None
        value = next((
            info.get(name)
            for name in (
                "resets_at", "resetsAt", "reset_at", "resetAt",
                "five_hour_resets_at", "fiveHourResetsAt",
            )
            if info.get(name) is not None
        ), None)
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def _is_rate_limit(self, event: Any) -> bool:
        if self._event_cause(event) == "rate_limit":
            return True
        raw = getattr(event, "raw", None)
        return isinstance(raw, Mapping) and (
            raw.get("api_error_status") == 429
            or "rate_limit_info" in raw
            or "rateLimitInfo" in raw
        )

    @staticmethod
    def _is_capacity(event: Any) -> bool:
        """D-074：这一条错误是不是「这一家现在满了」。

        只按报文措辞判，不按引擎名判——两家哪天都可能这么说。必须是错误事件：
        同一句话出现在正文里（写手复述报错）不算，那不是引擎在报自己的状态。
        """

        if not getattr(event, "is_error", False):
            return False
        text = str(getattr(event, "text", "") or "").casefold()
        return any(marker in text for marker in _CAPACITY_MARKERS)

    def _note_capacity(self, research_id: str, engine: str) -> str | None:
        """记下这一家满了，并把后续尝试改派到另一家。返回改派到的引擎。

        D-074 真机（09-16 r-20271e8a5028）：修前这类错误谁都不认，于是
        `MAX_ATTEMPTS` 两次 attempt 全落在同一家满负荷的 Codex 上，片没写出来
        ⇒ 片失败节不判 done ⇒ 整轮中止。改派走的是**现成的** `_route_overrides`
        那条让路路（限流让路用的也是它），⛔ 不新开失败路径、不起退避。

        两家都报过满了就**停在原地**：⛔ 不在两家之间来回倒——那只会把每一次重试
        都变成一次换家，跑满重试次数，还是原来的失败路收场。
        """

        seen = self._capacity_engines.setdefault(research_id, set())
        seen.add(engine)
        alternate = self._alternate(engine)
        if alternate in seen:
            return None
        self._route_overrides[research_id] = alternate
        return alternate

    def _start_backoff(
        self, research_id: str, engine: str, event: Any
    ) -> float | None:
        """起一次退避；返回本次睡眠秒数，已有退避在跑时返回 None。"""

        key = (research_id, engine)
        current = self._backoff_tasks.get(key)
        if current is not None and not current.done():
            return None
        count = self._backoff_counts.get(key, 0)
        reset_at = self._reset_at(event)
        if reset_at is None:
            delay = float(self._resilience_config.backoff_seconds(count))
        else:
            if self._utc_clock is None:
                raise RuntimeError("带 reset_at 的退避必须注入 UTC 时钟")
            delay = max(
                0.0,
                (reset_at - self._utc_clock()).total_seconds(),
            )
        # D-023：无论时钟来自哪里，一次退避不得超过档位封顶；
        # 到点重判，别让一条外部时间戳决定整个研究睡多久。
        delay = min(delay, float(self._resilience_config.backoff_max_seconds))
        self._backoff_counts[key] = count + 1
        self._backoff_causes[key] = self._event_cause(event) or "normal"

        async def sleep_then_release() -> None:
            try:
                await self._backoff_sleep(delay)
            finally:
                self._backoff_counts.pop(key, None)

        self._backoff_tasks[key] = asyncio.create_task(sleep_then_release())
        return delay

    def _backoff_started_event(
        self, research_id: str, engine: str, delay: float, cause: str | None
    ) -> NormalizedEvent:
        """D-023：退避开始就把「睡多久」写进事件，60 秒和 3 小时不能长一样。"""

        resume_at = None
        if self._utc_clock is not None:
            resume_at = (
                self._utc_clock() + timedelta(seconds=delay)
            ).isoformat()
        text = f"退避开始：{int(delay)} 秒后重试"
        if resume_at is not None:
            text += f"（预计 {resume_at} 恢复）"
        return NormalizedEvent(
            engine=engine,
            thread_id=research_id,
            turn_id=None,
            item_kind=ItemKind.THINKING,
            text=text,
            is_error=False,
            raw={
                "event": "BACKOFF_STARTED",
                "delay_seconds": delay,
                "resume_at": resume_at,
            },
            route_state="BACKOFF",
            cause=cause,
        )

    @staticmethod
    def _event_cause(event: Any) -> str | None:
        cause = getattr(event, "cause", None)
        value = getattr(cause, "value", cause)
        return value.casefold() if isinstance(value, str) else None

    async def _emit(self, callback: Any, event: NormalizedEvent) -> None:
        if callback is None:
            return
        callback_result = callback(event)
        if inspect.isawaitable(callback_result):
            await callback_result

    async def run(self, task: Any, ctx: Any, on_event: Any = None) -> Any:
        self._last_research_id = task.research_id
        planning = task.agent_kind in _PLANNING_KINDS
        selection = (
            EngineSelection("claude", "system")
            if planning
            else pick_engine(task.agent_kind, task.user_override)
        )
        run_key = (task.research_id, task.agent_id)
        run_number = self._agent_runs.get(run_key, 0) + 1
        self._agent_runs[run_key] = run_number
        after_attempt = self._manual_agent_alternates.get(run_key)
        manual_alternate = (
            task.research_id in self._manual_research_alternates
            or (after_attempt is not None and run_number > after_attempt)
        )
        preferred = (
            self._alternate(selection.engine)
            if manual_alternate and not planning
            else selection.engine
        )
        selected_engine = (
            preferred
            if planning
            else self._route_overrides.get(task.research_id, preferred)
        )
        backoff_cause = await self._await_route_gates(
            task.research_id, selected_engine
        )
        adapter = self._adapters[selected_engine]

        if backoff_cause is not None:
            await self._emit(on_event, NormalizedEvent(
                engine=selected_engine,
                thread_id=task.research_id,
                turn_id=None,
                item_kind=ItemKind.THINKING,
                text="退避结束",
                is_error=False,
                raw={"event": "BACKOFF_RELEASED"},
                route_state="CONTINUE",
                cause=backoff_cause,
            ))

        capacity_seen = False

        async def routed_event(event: Any) -> None:
            nonlocal capacity_seen
            route_state = getattr(event, "route_state", None)
            state_value = getattr(route_state, "value", route_state)
            started_delay = None
            # D-074：挡在最前面，且**不 return**——这条错误照常往下走事件管道，
            # 只是顺手把后续尝试改派到另一家。规划期固定走 claude、看不见这个覆盖，
            # 给它记一笔只会把别的任务无端赶去 codex，所以规划期不记。
            if not planning and self._is_capacity(event):
                capacity_seen = True
                self._note_capacity(task.research_id, selected_engine)
            if state_value == "BACKOFF":
                started_delay = self._start_backoff(
                    task.research_id, selected_engine, event
                )
            reason = str(getattr(event, "reason", None) or getattr(event, "text", ""))
            if state_value == "WARN" and "继续跑会计费" in reason:
                self._quota_gates.setdefault(task.research_id, asyncio.Event())
            target = getattr(event, "failover_target", None)
            scope = getattr(event, "scope", None)
            if target is not None and scope == "new_tasks":
                if target not in _ENGINES:
                    raise ValueError(f"未知限流让路目标：{target}")
                self._route_overrides[task.research_id] = target
            await self._emit(on_event, event)
            if started_delay is not None:
                await self._emit(on_event, self._backoff_started_event(
                    task.research_id,
                    selected_engine,
                    started_delay,
                    self._backoff_causes.get((task.research_id, selected_engine)),
                ))

        self._active = adapter
        prepare_source_events(task)
        try:
            try:
                parameters = inspect.signature(adapter.run).parameters
                kwargs = {"on_event": routed_event}
                if "source_adapter" in parameters:
                    kwargs["source_adapter"] = self._source_adapter
                result = await adapter.run(task, ctx, **kwargs)
            finally:
                await replay_source_events(task, routed_event)
            return result
        finally:
            self._active = None
            # D-074：这一轮没人喊满，说明容量回来了——把「谁满过」的记性整条清掉。
            # 不清的话，半小时前两家各满过一次，就再也不给这个研究让路了，
            # 那等于把这类错误当成「引擎永久不可用」，正是本包⛔的那一条。
            if not capacity_seen:
                self._capacity_engines.pop(task.research_id, None)

    async def run_planning_segment(
        self,
        request: PlanningSegmentRequest,
        *,
        on_text: Any = None,
    ) -> PlanningSegmentResult:
        """规划短流固定走 Claude。"""

        generator = getattr(self._adapters["claude"], "generate_plan_segment", None)
        if generator is None:
            if request.output_path is None:
                return PlanningSegmentResult(
                    text="",
                    completed=False,
                    error="规划短流请求缺少落盘路径",
                )
            from app.adapters import validation
            from app.adapters.capability import Capability, FileSystemScope
            from app.adapters.contracts import EngineTask

            task = EngineTask(
                body=request.prompt,
                output_path=request.output_path,
                output_format="json",
                research_id=request.research_id,
                goal_id="plan-segments",
                agent_id=f"plan-{request.segment_name}",
                agent_kind="planning",
                validators=["file_exists"],
                capability=Capability(
                    profile="custom",
                    tools=("fs.write",),
                    fs=FileSystemScope(write=("plan-segments/**",)),
                ),
            )
            ctx = validation.Ctx(
                output_path=request.output_path,
                output_format="json",
                research_id=request.research_id,
                goal_id="plan-segments",
                agent_id=f"plan-{request.segment_name}",
                read_text=lambda: request.output_path.read_text(encoding="utf-8"),
                read_json=lambda: json.loads(
                    request.output_path.read_text(encoding="utf-8")
                ),
                store=None,
                source_domains=frozenset(),
            )
            result = await self._adapters["claude"].run(task, ctx)
            text = (
                request.output_path.read_text(encoding="utf-8")
                if request.output_path.is_file()
                else ""
            )
            if on_text is not None and text:
                callback_result = on_text(text)
                if inspect.isawaitable(callback_result):
                    await callback_result
            transport = any(
                self._event_cause(event) == "transport"
                for event in getattr(result, "events", [])
            )
            causes = [
                self._event_cause(event)
                for event in getattr(result, "events", [])
            ]
            cause = next(
                (
                    item
                    for item in ("rate_limit", "transport", "service")
                    if item in causes
                ),
                None,
            )
            error = (
                getattr(result, "engine_error", None)
                or getattr(result, "conclusion_error", None)
            )
            if not error:
                details: list[str] = []
                report = getattr(result, "validation", None)
                for item in getattr(report, "results", []):
                    verdict = getattr(getattr(item, "verdict", None), "value", None)
                    if verdict == "pass":
                        continue
                    message = str(getattr(item, "message", "")).strip()
                    offenders = [str(value) for value in getattr(item, "offenders", [])]
                    if offenders:
                        message = f"{message}；offenders={offenders}"
                    if message:
                        details.append(message)
                error = "；".join(details) or None
            return PlanningSegmentResult(
                text=text,
                completed=bool(getattr(result, "succeeded", False)),
                transport_interrupted=transport,
                error=str(error) if error else None,
                cause=cause,
            )
        result = generator(request, on_text=on_text)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, PlanningSegmentResult):
            raise TypeError("规划短流适配器必须返回 PlanningSegmentResult")
        return result

    async def call_source(
        self,
        tool_name: str,
        query: str,
        window: str,
        *,
        research_id: str,
        goal_id: str,
        agent_id: str,
        capability: Any,
        on_event: Any = None,
        **kwargs: Any,
    ) -> Any:
        """在适配层解析 source.* 工具并转发源事件，不向编排层泄漏实现。"""

        return await self._source_adapter.call(
            tool_name,
            query,
            window,
            research_id=research_id,
            goal_id=goal_id,
            agent_id=agent_id,
            capability=capability,
            on_event=on_event,
            **kwargs,
        )

    async def interrupt(self) -> None:
        if self._active is None:
            raise RuntimeError("当前没有运行中的引擎任务")
        await self._active.interrupt()
