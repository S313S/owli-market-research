"""§D-074-fu：容量让路的真机复验——两把尺子各自通电。

§D-074 的四条用例用的是假适配器（`_Engine`），证明的是「`RoutedAdapter` 的分支写对了」。
本文件补另一半：

1. **走真适配器与真 CLI 事件协议**：真的 `CodexAdapter` 起真的子进程，子进程逐字吐
   2026-09-16 `r-20271e8a5028` 转录里那几行；判据读 **transcript 落盘的 `engine`
   字段**——09-16 诊出病象用的就是这把尺子、这个文件形态。
2. **尺子本身也要验**（项目坑：自造脚本造过七次假数据）：货 2 的探子对「修复前的样子」
   必须判红、对「换了家」必须判绿、对「没有下一段」必须判 unknown。

⛔ 本文件不改被测行为，也不断言 `routing.py` 之外的任何东西。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_D074_DIR = ROOT / "scripts" / "acceptance" / "d074"


def _load(name: str):
    path = _D074_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"d074fu_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_桩引擎走真适配器时容量上限让路_转录里下一次尝试写着_Claude(tmp_path, monkeypatch):
    """货 1 绿侧：真 `CodexAdapter` + 真子进程 + 真事件管道，读转录 `engine` 字段。

    ⛔ 不读 `_Engine.calls`、不读日志文字——那两样在真机上都没有。
    """

    probe = _load("live_failover_probe")
    report = probe.run_scenario("head", tmp_path, attempts=2)

    attempts = report["attempts"]
    assert len(attempts) == 2
    # 第 1 次：落在满负荷的 Codex 上，两条容量报文（error + turn.failed）逐字落进转录。
    assert attempts[0]["transcript_engines"] == ["Codex"]
    assert attempts[0]["capacity_lines"] == 2
    assert attempts[0]["succeeded"] is False
    # 第 2 次：转录里写的是 Claude —— 这就是这条修复在生产里该有的读数。
    assert attempts[1]["transcript_engines"] == ["Claude"]
    assert attempts[1]["capacity_lines"] == 0
    assert attempts[1]["succeeded"] is True
    assert report["route_override"] == "claude"


def _row(seq: int, engine: str, output: str, event: dict) -> str:
    return json.dumps(
        {"ts": 0.0, "seq": seq, "engine": engine, "agent": "a", "output": output,
         "event": event},
        ensure_ascii=False,
    )


CAPACITY = "Selected model is at capacity. Please try a different model."
_STARTED = {"type": "thread.started", "thread_id": "t"}
_TURN = {"type": "turn.started"}
_ERROR = {"type": "error", "message": CAPACITY}
_FAILED = {"type": "turn.failed", "error": {"message": CAPACITY}}
_DONE = {"type": "turn.completed"}
_INIT = {"subtype": "init", "data": {"type": "system", "subtype": "init"}}


def test_探子把修复前_换了家_没有下一段三种形态分别判红绿与_unknown(tmp_path):
    """货 2 的通电证明：尺子量不出红，以后量出绿也说明不了什么。

    三份转录都照真机形态写：一次 attempt 起于 `thread.started`（Codex）或
    `subtype=init`（Claude），容量报文一次占 `error` + `turn.failed` 两行。
    """

    scanner = _load("scan_capacity_failover")

    # ① 修复前的样子：同一片连着两次 attempt 都落在 Codex（真机 seq 120–128 同形）。
    red = tmp_path / "red.transcript.jsonl"
    red.write_text("\n".join([
        _row(1, "Codex", "sec-1.part.1.md", _STARTED),
        _row(2, "Codex", "sec-1.part.1.md", _TURN),
        _row(3, "Codex", "sec-1.part.1.md", _ERROR),
        _row(4, "Codex", "sec-1.part.1.md", _FAILED),
        _row(5, "Codex", "sec-1.part.1.md", _STARTED),
        _row(6, "Codex", "sec-1.part.1.md", _TURN),
        _row(7, "Codex", "sec-1.part.1.md", _DONE),
    ]) + "\n", encoding="utf-8")

    # ② 让路生效的样子：下一次 attempt 的 engine 换成了 Claude。
    green = tmp_path / "green.transcript.jsonl"
    green.write_text("\n".join([
        _row(1, "Codex", "sec-1.part.1.md", _STARTED),
        _row(2, "Codex", "sec-1.part.1.md", _TURN),
        _row(3, "Codex", "sec-1.part.1.md", _ERROR),
        _row(4, "Codex", "sec-1.part.1.md", _FAILED),
        _row(5, "Claude", "sec-1.part.1.md", _INIT),
    ]) + "\n", encoding="utf-8")

    # ③ 那一轮就此收场：同一片再没有后续 attempt（真机 sec-2.part.1.md 同形）。
    dead = tmp_path / "dead.transcript.jsonl"
    dead.write_text("\n".join([
        _row(1, "Codex", "sec-1.part.1.md", _STARTED),
        _row(2, "Codex", "sec-1.part.1.md", _TURN),
        _row(3, "Codex", "sec-1.part.1.md", _ERROR),
        _row(4, "Codex", "sec-1.part.1.md", _FAILED),
        _row(5, "Codex", "sec-9.part.1.md", _STARTED),
    ]) + "\n", encoding="utf-8")

    verdicts = {
        path.stem: [item["verdict"] for item in scanner.scan_file(path, display=path.name)]
        for path in (red, green, dead)
    }

    assert verdicts["red.transcript"] == ["no-failover"]
    assert verdicts["green.transcript"] == ["failover-ok"]
    assert verdicts["dead.transcript"] == ["unknown"]


def test_探子按_output_分流_不被同章并发的别的片带偏(tmp_path):
    """真机转录是**按章**落盘的：同章并发的多个片交替写同一份文件。

    09-16 `consulting-parts` 里，shard-1 报完容量之后插进来的是 `01-执行摘要.md`
    的十几行 Claude 事件（seq 129–141），shard-1 自己的下一次 attempt 在 seq 142。
    尺子要是不按 output 分流，就会把隔壁片的 Claude 读成「换家了」——假绿。
    """

    scanner = _load("scan_capacity_failover")

    path = tmp_path / "chapter.transcript.jsonl"
    path.write_text("\n".join([
        _row(1, "Codex", "shard-1.md", _STARTED),
        _row(2, "Codex", "shard-1.md", _ERROR),
        _row(3, "Codex", "shard-1.md", _FAILED),
        # 隔壁片：同一份转录，另一个 output，另一家引擎。
        _row(4, "Claude", "01-执行摘要.md", _INIT),
        _row(5, "Claude", "01-执行摘要.md", {"subtype": "success"}),
        # shard-1 自己的下一次 attempt：还是 Codex。
        _row(6, "Codex", "shard-1.md", _STARTED),
        _row(7, "Codex", "shard-1.md", _TURN),
    ]) + "\n", encoding="utf-8")

    findings = scanner.scan_file(path, display=path.name)

    assert [item["verdict"] for item in findings] == ["no-failover"]
    assert findings[0]["output"] == "shard-1.md"
    assert findings[0]["next_attempt_first_seq"] == 6
