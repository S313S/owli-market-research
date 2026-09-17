"""§D-081 判据 2：对沙盒成品 r-3b3482ca7f8b 的**库副本**重跑一次断言登记，量四个读数。

⛔ 只读 `../Owli-src5` 的产物目录与库（库还走 backup API 取过快照），
   一个字节都不往 8981 正在用的那个库上写。
用法：`../Owli/.venv/bin/python scripts/d081_probe_registration.py <快照库路径>`
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.plan.store import load_plan  # noqa: E402
from app.reliability import claims as claims_module  # noqa: E402
from app.reliability.claims import (  # noqa: E402
    ClaimsRegistrationError,
    claims_from_documents,
    prepare_claim_registration,
)
from app.store.dao import Store  # noqa: E402

RESEARCH_ID = "r-3b3482ca7f8b"
SRC5_RUNS = Path(
    "/Users/xiaoci/Downloads/Workspace/VibeCoding/InformationCollection"
    "/Owli-src5/var/runs"
)
SECTIONED = {"report-chapter", "report-finalizer"}


def _documents(plan) -> list[dict]:
    root = (SRC5_RUNS / plan.research_id).resolve(strict=False)
    documents: list[dict] = []
    seen: set[Path] = set()
    for goal in plan.goals:
        for agent in goal.agents:
            if str(agent.output.get("format")) != "json":
                continue
            path = (root / str(agent.output.get("path", ""))).resolve(strict=False)
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            document = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(document, dict) and "claims" in document:
                documents.append(document)
    return documents


def main() -> int:
    store = Store(Path(sys.argv[1]))
    plan = load_plan(store, RESEARCH_ID)
    assert plan is not None
    documents = _documents(plan)
    rows = store.list_evidence(RESEARCH_ID)
    evidence_ids = {str(row["id"]) for row in rows}
    stripped: list[dict] = []
    deduped: list[dict] = []
    rejected: list[dict] = []
    collected = claims_from_documents(documents, stripped=stripped)
    print(f"章产物文档数={len(documents)}  收集到的原始 claims={len(collected)}")
    print(f"库副本 evidence 行数={len(evidence_ids)}")
    kwargs = {"source": "chapter", "deduped": deduped, "rejected": rejected}
    try:
        prepare_claim_registration(rows, collected[:1], **kwargs)
    except TypeError as exc:
        if "rejected" not in str(exc):
            raise
        kwargs.pop("rejected")
        print("（base 上还没有 rejected 记账出参，退回旧签名重跑）")
    except ClaimsRegistrationError:
        pass
    deduped.clear()
    rejected.clear()
    try:
        registered, mapping, dropped = prepare_claim_registration(
            rows, collected, **kwargs,
        )
    except ClaimsRegistrationError as exc:
        print(f"登记整批否决：{exc}")
        print(f"  offenders 共 {len(exc.offenders)} 处，前 5 条：")
        for item in exc.offenders[:5]:
            print(f"    - {item}")
        print("读数①  extra.claims 条数 = 0（登记没跑成，库里留着 replay 复制来的旧值）")
        print("读数②  dropped = 0")
        print("读数③  剔除记账条数 = 0")
        print("读数④  本轮登记结果的 evidence_ids 命中率 = n/a（没有结果）")
        return 0
    refs = [e for claim in registered for e in claim["evidence_ids"]]
    hit = [e for e in refs if e in evidence_ids]
    print(f"读数①  extra.claims 条数 = {len(registered)}")
    print(f"读数②  dropped = {len(dropped)}")
    print(f"读数③  剔除记账条数 = {len(rejected)}（去重记账另计 {len(deduped)}）")
    rate = f"{len(hit) / len(refs) * 100:.2f}%" if refs else "n/a"
    print(f"读数④  evidence_ids 引用 {len(refs)} 条、命中 {len(hit)} 条、命中率 {rate}")
    for item in rejected[:5]:
        print(f"    剔除样例：{item}")

    if "--apply" not in sys.argv:
        return 0
    # 真落进库副本，再跑一次货 2 的悬空复查，量库上的读数。
    # ⛔ 记账列表另起一份，不跟上面那趟 prepare 的读数混着累加。
    applied_rejected: list[dict] = []
    claims_module.register_claims(
        store, RESEARCH_ID, collected,
        source="chapter", deduped=[], rejected=applied_rejected,
    )
    rejected = applied_rejected
    stats = claims_module.audit_dangling_claims(store, RESEARCH_ID)
    stored = store.get_report(RESEARCH_ID)["extra"]
    print("--- 落库之后（库副本读数）---")
    print(f"读数①  extra.claims 条数 = {len(stored.get('claims') or [])}")
    print(f"读数②  extra.claims_dropped 条数 = {len(stored.get('claims_dropped') or [])}")
    print(f"读数③  剔除记账条数 = {len(rejected)}")
    stored_refs = [
        e for claim in (stored.get("claims") or [])
        for e in (claim.get("evidence_ids") or [])
    ]
    stored_hit = [e for e in stored_refs if e in evidence_ids]
    stored_rate = (
        f"{len(stored_hit) / len(stored_refs) * 100:.2f}%" if stored_refs else "n/a"
    )
    print(
        f"读数④  evidence_ids 引用 {len(stored_refs)} 条、命中 {len(stored_hit)} 条、"
        f"命中率 {stored_rate}"
    )
    print(f"货 2 悬空复查读数：{ {k: v for k, v in stats.items() if k != 'purged'} }")
    print(f"  清掉的全悬空 claim 数 = {len(stats.get('purged') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
