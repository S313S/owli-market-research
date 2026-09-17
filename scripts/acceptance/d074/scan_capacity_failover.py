#!/usr/bin/env python3
"""§D-074-fu 货 2：真机探子——扫 transcript，判每一处「at capacity」后有没有换家。

容量上限是外部状态，干等 Codex 再满一次等于把验证交给运气。这把尺子留在树上：
下次真撞到，直接重跑它就有读数，不用再翻转录。

**读的是什么**：`var/runs/**/*.transcript.jsonl` 里每一行的 `engine` 字段。
09-16 那次病象就是这么诊出来的（同一片连着两次 attempt 都写着 `"engine": "Codex"`），
让路生效后同一个位置应当写着 `"engine": "Claude"`。⛔ 不读日志文字、不读代码分支。

**怎么切 attempt**（按真机转录实测的形态定，不是猜的）：
转录是**按章**落盘的，同一章里并发的多个片交替写同一份文件，所以必须先按 `output`
分流，再在单个 output 的行序列里切段。一段 = 一次引擎调用 = 一次 attempt。段的起点：

1. 该 output 的第一行；
2. `engine` 与上一行不同（换家本身就是新的一次调用）；
3. `{"type": "thread.started"}` —— 一次 `codex exec` 正好发一条；
4. `{"subtype": "init"}` —— Claude SDK 一次会话的起手。

**三档判定**（对每一处 `at capacity` 命中）：

- `failover-ok`  同一 output 的**下一段**引擎换了家 —— 让路生效。
- `no-failover`  下一段还是同一家 —— 修复前的样子（红）。
- `unknown`      同一 output 没有下一段 —— 那一轮就此收场，这处判不出来。

⛔ 只读：不写、不改、不碰任何被扫的树。

用法：

    python scripts/acceptance/d074/scan_capacity_failover.py            # 默认三棵树
    python scripts/acceptance/d074/scan_capacity_failover.py --root <某棵树>
    python scripts/acceptance/d074/scan_capacity_failover.py --json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

#: 匹配措辞：`app/adapters/routing.py::_CAPACITY_MARKERS` 的同一串，逐字。
#: 尺子和被测代码认的是同一句话，否则量出来的不是同一件事。
CAPACITY_MARKERS = ("at capacity", "please try a different model")

#: 默认扫的三棵树（相对本仓库的上一级）。
DEFAULT_ROOT_NAMES = ("Owli", "Owli-wx1", "Owli-serve")

VERDICT_OK = "failover-ok"
VERDICT_RED = "no-failover"
VERDICT_UNKNOWN = "unknown"


def default_roots() -> list[Path]:
    siblings = Path(__file__).resolve().parents[3].parent
    return [siblings / name for name in DEFAULT_ROOT_NAMES]


def _event_text(event: Any) -> str:
    """一行事件的全文；转录里 `event` 可能是 dict，也可能是 CLI 的裸 stderr 字符串。"""

    if isinstance(event, str):
        return event
    try:
        return json.dumps(event, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(event)


def is_capacity_row(row: dict) -> bool:
    text = _event_text(row.get("event")).casefold()
    return any(marker in text for marker in CAPACITY_MARKERS)


def read_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    for line in content.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _starts_attempt(row: dict, previous: dict | None) -> bool:
    if previous is None:
        return True
    if row.get("engine") != previous.get("engine"):
        return True
    event = row.get("event")
    if isinstance(event, dict):
        if event.get("type") == "thread.started":
            return True
        if event.get("subtype") == "init":
            return True
    return False


def segment_attempts(rows: Iterable[dict]) -> list[dict]:
    """把一个 output 的行序列切成若干次 attempt。"""

    attempts: list[dict] = []
    previous: dict | None = None
    for row in rows:
        if _starts_attempt(row, previous):
            attempts.append({
                "engine": row.get("engine"),
                "first_seq": row.get("seq"),
                "last_seq": row.get("seq"),
                "rows": [row],
            })
        else:
            attempts[-1]["last_seq"] = row.get("seq")
            attempts[-1]["rows"].append(row)
        previous = row
    return attempts


def scan_file(path: Path, *, display: str) -> list[dict]:
    rows = read_rows(path)
    if not rows:
        return []
    by_output: dict[str, list[dict]] = {}
    for row in sorted(rows, key=lambda item: item.get("seq") or 0):
        by_output.setdefault(str(row.get("output") or ""), []).append(row)

    findings: list[dict] = []
    for output, output_rows in by_output.items():
        attempts = segment_attempts(output_rows)
        for index, attempt in enumerate(attempts):
            hits = [row for row in attempt["rows"] if is_capacity_row(row)]
            if not hits:
                continue
            following = attempts[index + 1] if index + 1 < len(attempts) else None
            if following is None:
                verdict = VERDICT_UNKNOWN
            elif following["engine"] != attempt["engine"]:
                verdict = VERDICT_OK
            else:
                verdict = VERDICT_RED
            findings.append({
                "file": display,
                "output": output,
                "attempt_index": index + 1,
                "attempt_engine": attempt["engine"],
                "attempt_seq": [attempt["first_seq"], attempt["last_seq"]],
                "capacity_hits": len(hits),
                "capacity_seq": [row.get("seq") for row in hits],
                "next_attempt_engine": following["engine"] if following else None,
                "next_attempt_first_seq": following["first_seq"] if following else None,
                "verdict": verdict,
            })
    return findings


def scan_roots(roots: list[Path]) -> dict:
    per_root: list[dict] = []
    findings: list[dict] = []
    for root in roots:
        runs = root / "var" / "runs"
        files = sorted(runs.rglob("*.transcript.jsonl")) if runs.is_dir() else []
        root_findings: list[dict] = []
        for path in files:
            try:
                display = str(path.relative_to(root.parent))
            except ValueError:
                display = str(path)
            root_findings.extend(scan_file(path, display=display))
        per_root.append({
            "root": str(root),
            "runs_dir_exists": runs.is_dir(),
            "transcript_files": len(files),
            "findings": len(root_findings),
        })
        findings.extend(root_findings)

    counts = {
        VERDICT_OK: 0,
        VERDICT_RED: 0,
        VERDICT_UNKNOWN: 0,
    }
    for finding in findings:
        counts[finding["verdict"]] += 1
    return {
        "roots": per_root,
        "capacity_hit_rows": sum(item["capacity_hits"] for item in findings),
        "capacity_attempts": len(findings),
        "counts": counts,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="§D-074-fu 货 2 容量让路探子（只读）")
    parser.add_argument(
        "--root", action="append", default=None,
        help="要扫的树（可给多次）；缺省为 Owli / Owli-wx1 / Owli-serve",
    )
    parser.add_argument("--json", action="store_true", help="只打 JSON")
    args = parser.parse_args()

    roots = [Path(item).resolve() for item in args.root] if args.root else default_roots()
    report = scan_roots(roots)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    for item in report["roots"]:
        state = "有 var/runs" if item["runs_dir_exists"] else "⛔ 无 var/runs"
        print(
            f"{item['root']}：{state}，"
            f"transcript {item['transcript_files']} 份，命中 {item['findings']} 处"
        )
    print()
    print(
        f"命中行数 {report['capacity_hit_rows']}，"
        f"落在 {report['capacity_attempts']} 次 attempt 上"
    )
    counts = report["counts"]
    print(
        f"  {VERDICT_OK}={counts[VERDICT_OK]}  "
        f"{VERDICT_RED}={counts[VERDICT_RED]}  "
        f"{VERDICT_UNKNOWN}={counts[VERDICT_UNKNOWN]}"
    )
    print()
    for finding in report["findings"]:
        print(
            f"  [{finding['verdict']:<12}] {finding['file']}\n"
            f"      output={finding['output']} "
            f"attempt#{finding['attempt_index']} engine={finding['attempt_engine']} "
            f"seq={finding['attempt_seq'][0]}–{finding['attempt_seq'][1]} "
            f"命中 seq={finding['capacity_seq']}\n"
            f"      下一次 attempt：engine={finding['next_attempt_engine']} "
            f"first_seq={finding['next_attempt_first_seq']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
