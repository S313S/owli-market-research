"""报告断言的显式登记、permalink 联接与双向落库。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from app.store.dao import normalize_permalink


CLAIM_ID_PATTERN = re.compile(r"^c-\d{2,}$")
CLAIM_FIELDS = frozenset({"id", "text", "evidence", "conflict_note"})
CLAIM_EVIDENCE_FIELDS = frozenset({
    "permalink", "stance", "firsthand", "origin_url",
})
FIRSTHAND_SOURCES = frozenset({
    # §XSEM-1 条 1：C-1 只做到「撰写方声明可分辨」，闸门没守住。audited = §3.2 第 5 项
    # 真正由 reliability-auditor 逐 (证据, 断言) 对判过、且留了一句依据。
    "declared_by_writer", "declared_by_backfill", "audited",
})
_FIRSTHAND_SOURCE_BY_CLAIMS_SOURCE = {
    "chapter": "declared_by_writer",
    "backfill": "declared_by_backfill",
}
CLAIM_DROP_REASONS = frozenset({
    "dangling_evidence", "all_evidence_dangling",
})
#: §D-081 货 2：悬空断言被复查清掉时沿用登记期同一个词，报告侧只认一套说法。
DANGLING_CLAIM_REASON = "all_evidence_dangling"
#: §D-081 货 1：证据链里**逐条可降级**的闭集——越界只剔这一条链，不退整批。
#: ⛔ 闭集本身一个字不放宽（`neutral` 不是合法取值，是写手写错了）。
CLAIM_LINK_CLOSED_SETS: dict[str, frozenset[str]] = {
    "stance": frozenset({"supports", "contradicts"}),
}


@dataclass(frozen=True)
class ClaimsRegistrationError(ValueError):
    """断言登记失败；offenders 可直接进入报告校验事件。"""

    message: str
    offenders: list[str]

    def __str__(self) -> str:
        return self.message


def _error(message: str, offenders: Iterable[str]) -> ClaimsRegistrationError:
    return ClaimsRegistrationError(message, list(offenders))


def _accountable(value: Any) -> Any:
    """记账里的「原值」必须原样可读，且必须能进事件（JSON 可序列化）。"""

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return repr(value)


def claims_from_documents(
    documents: Iterable[Mapping[str, Any]],
    *,
    stripped: list[dict[str, Any]] | None = None,
) -> list[Any]:
    """按章产物顺序收集可选顶层 claims；不从正文推断。

    §FIX-2 货 1（D-037）：id 由分片写手按「节序+片序+条序」生成，goal 与章两个
    维度缺席，跨章同位片必撞 `c-010101`（真机 250 条只剩 84 唯一、166 处重复）。
    这里按**文档序**给合法 id 加确定性命名空间 `c-{文档序:02d}{原数字}`——机械改写，
    不靠提示词约束写手；形态仍满足 CLAIM_ID_PATTERN。文档内重复加前缀后照旧相撞、
    id 格式违规原样透传，两条检出能力都不被掩盖。claim id 只是报告内部键：正文角标
    走 `[Sxx]`，不引用 claim id，故改写不动正文。
    """

    result: list[Any] = []
    for index, document in enumerate(documents, start=1):
        claims = document.get("claims")
        if claims is None:
            continue
        if not isinstance(claims, list):
            raise _error("章产物 claims 必须是数组", ["claims"])
        for position, claim in enumerate(claims):
            claim = _namespaced_claim(claim, index)
            result.append(_strip_unknown_keys(
                claim, location=f"claims[{len(result)}]",
                origin=f"文档 {index} 的第 {position + 1} 条", account=stripped,
            ))
    return result


def _strip_unknown_keys(
    claim: Any, *, location: str, origin: str, account: list[dict[str, Any]] | None,
) -> Any:
    """机械剥离闭集外的键（用户 09-03 拍板「甲」），剥了什么逐条记账。

    §FIX-2 货 1：写手会在 claim 顶层多写 `stance`、在 evidence 条目里多写 `fetched_at`
    这类闭集外字段，登记是「一处不合规整批退回」，于是 250 条断言全被拒、库里恒空。
    这里只剥**闭集外**的键（CLAIM_FIELDS / CLAIM_EVIDENCE_FIELDS 本身一个字不放宽），
    剥掉的键与出处进 account，由调用方落进事件；剥不动的（缺 id、类型不对）原样透传，
    照旧由 prepare_claim_registration 报错。
    """

    if not isinstance(claim, Mapping):
        return claim
    removed: dict[str, list[str]] = {}
    kept = {k: v for k, v in claim.items() if k in CLAIM_FIELDS}
    top_unknown = sorted(set(claim) - CLAIM_FIELDS)
    if top_unknown:
        removed["claim"] = top_unknown
    evidence = kept.get("evidence")
    if isinstance(evidence, list):
        cleaned: list[Any] = []
        for item in evidence:
            if not isinstance(item, Mapping):
                cleaned.append(item)
                continue
            unknown = sorted(set(item) - CLAIM_EVIDENCE_FIELDS)
            if unknown:
                removed.setdefault("evidence", [])
                removed["evidence"].extend(k for k in unknown if k not in removed["evidence"])
            cleaned.append({k: v for k, v in item.items() if k in CLAIM_EVIDENCE_FIELDS})
        kept["evidence"] = cleaned
    if not removed:
        return claim
    if account is not None:
        account.append({
            "location": location, "origin": origin,
            "claim_id": kept.get("id") if isinstance(kept.get("id"), str) else None,
            "removed": removed,
        })
    return kept


def _namespaced_claim(claim: Any, document_index: int) -> Any:
    """给合法 id 加文档命名空间；其余原样返回（含非 Mapping 与非法 id）。"""

    if not isinstance(claim, Mapping):
        return claim
    claim_id = claim.get("id")
    if not isinstance(claim_id, str) or CLAIM_ID_PATTERN.fullmatch(claim_id) is None:
        return claim
    return {**claim, "id": f"c-{document_index:02d}{claim_id[2:]}"}


def prepare_claim_registration(
    evidence_rows: Sequence[Mapping[str, Any]],
    raw_claims: Sequence[Any],
    *,
    source: str,
    deduped: list[dict[str, Any]] | None = None,
    rejected: list[dict[str, Any]] | None = None,
) -> tuple[
    list[dict[str, Any]],
    dict[str, list[str]],
    list[dict[str, Any]],
]:
    """校验断言并联接 evidence；只把悬空 permalink 降级为丢弃账。

    §D-075：**同一条主张内逐字节重复的 permalink** 一并降级——机械去重保留第一条，
    去掉的逐条进 `deduped`，由调用方落进事件。真机 r-20271e8a5028 的读数：1380 条
    主张里只有 1 条把同一条小红书评论写了两遍（`claims[732].evidence[2]`），按
    「一处不合规整批退回」端掉了全部 1380 条，`reports.extra` 里连 `claims` 键都
    没有、正式稿交叉验证表整张空。同一条主张重复引同一个来源是**书写冗余**不是
    结构违规：下面本来就用 `seen_urls` 把重复那条跳过了，联接结果一字不差，
    「整批退回」是它唯一的后果。⛔ 这一处只治逐字节重复，别的校验一个字不放宽；
    ⛔ 也不静默——去了什么必须查得到，否则等于把证据质量问题藏起来。

    §D-081 货 1：**闭集越界**（`CLAIM_LINK_CLOSED_SETS`，目前只有 `stance`）同样
    逐条降级——剔掉那一条证据链 + 逐条进 `rejected`。真机 r-3b3482ca7f8b 的读数：
    写手在 sec-4 两条主张里把 `stance` 写成 `neutral`，**2 个越界值把 1360 条断言
    整批打回**，`reports.extra.claims` 原样留着 replay 复制来的旧值。D-075 那次只
    覆盖了「重复链接」，`stance` 越闭集没被覆盖，所以是同形状、不同触发条件。
    ⛔ 闭集本身一个字不放宽：越界的链不进 `evidence_ids`、不进 `mapping`、
    ⛔ 也不按默认值 `supports` 兜底——写错的立场当没写过，不当成支持。
    ⛔ 同样不静默：哪条 claim、哪个字段、原值是什么，三样都进 `rejected`。
    """

    if source not in {"chapter", "backfill"}:
        raise ValueError("claims_source 只能是 chapter 或 backfill")
    if isinstance(raw_claims, (str, bytes)) or not isinstance(raw_claims, Sequence):
        raise TypeError("claims 必须是数组")
    evidence_by_url: dict[str, str] = {}
    for row in evidence_rows:
        evidence_id = str(row.get("id") or "")
        permalink = row.get("permalink")
        if not evidence_id or not isinstance(permalink, str):
            continue
        evidence_by_url[normalize_permalink(permalink)] = evidence_id

    registered: list[dict[str, Any]] = []
    mapping: dict[str, list[str]] = {}
    dropped: list[dict[str, Any]] = []
    seen_claim_ids: set[str] = set()
    offenders: list[str] = []
    for index, raw_claim in enumerate(raw_claims):
        location = f"claims[{index}]"
        if not isinstance(raw_claim, Mapping):
            offenders.append(f"{location} 不是 object")
            continue
        unknown = sorted(set(raw_claim) - CLAIM_FIELDS)
        if unknown:
            offenders.append(f"{location} 含未知键 {unknown}")
        claim_id = raw_claim.get("id")
        if not isinstance(claim_id, str) or CLAIM_ID_PATTERN.fullmatch(claim_id) is None:
            offenders.append(f"{location}.id 不符合 c-\\d{{2,}}")
            continue
        if claim_id in seen_claim_ids:
            offenders.append(f"{location}.id 报告内重复：{claim_id}")
            continue
        seen_claim_ids.add(claim_id)
        text = raw_claim.get("text")
        if not isinstance(text, str) or not text.strip():
            offenders.append(f"{location}.text 缺失或为空")
        raw_evidence = raw_claim.get("evidence")
        if not isinstance(raw_evidence, list) or not raw_evidence:
            offenders.append(f"{location}.evidence 至少需要 1 条")
            continue

        evidence_ids: list[str] = []
        contradicts: dict[str, str] = {}
        firsthand: list[str] = []
        origins: dict[str, str] = {}
        dangling_permalinks: list[str] = []
        seen_urls: set[str] = set()
        for evidence_index, raw_link in enumerate(raw_evidence):
            link_location = f"{location}.evidence[{evidence_index}]"
            if not isinstance(raw_link, Mapping):
                offenders.append(f"{link_location} 不是 object")
                continue
            link_unknown = sorted(set(raw_link) - CLAIM_EVIDENCE_FIELDS)
            if link_unknown:
                offenders.append(f"{link_location} 含未知键 {link_unknown}")
            permalink = raw_link.get("permalink")
            try:
                normalized = normalize_permalink(str(permalink or ""))
            except ValueError:
                offenders.append(f"{link_location}.permalink 不是 HTTP(S) 绝对链接")
                continue
            if normalized in seen_urls:
                # §D-075：书写冗余，机械去重 + 记账，⛔ 不再整批退回、⛔ 不静默。
                if deduped is not None:
                    deduped.append({
                        "claim_id": claim_id,
                        "location": link_location,
                        "permalink": str(permalink),
                    })
                continue
            seen_urls.add(normalized)
            stance = raw_link.get("stance", "supports")
            # §D-081 货 1：闭集越界逐条剔除 + 记账，⛔ 不再整批退回、⛔ 不静默。
            stance_rejected = stance not in CLAIM_LINK_CLOSED_SETS["stance"]
            if stance_rejected and rejected is not None:
                rejected.append({
                    "claim_id": claim_id,
                    "location": link_location,
                    "permalink": str(permalink),
                    "field": "stance",
                    "value": _accountable(stance),
                })
            if "firsthand" in raw_link and not isinstance(raw_link["firsthand"], bool):
                offenders.append(f"{link_location}.firsthand 必须是 bool")
            origin_url = raw_link.get("origin_url")
            normalized_origin: str | None = None
            if origin_url is not None:
                try:
                    normalized_origin = normalize_permalink(str(origin_url))
                except ValueError:
                    offenders.append(f"{link_location}.origin_url 不是 HTTP(S) 绝对链接")
            if stance_rejected:
                # 剔除排在别的校验**之后**：同一条链上的结构违规照旧算数，
                # ⛔ 不许让「立场写错」把 firsthand/origin_url 的检出能力一起掩盖掉。
                continue
            # 悬空只改变证据的登记去向，不能让同一 link 绕过结构契约。
            evidence_id = evidence_by_url.get(normalized)
            if evidence_id is None:
                dangling_permalinks.append(normalized)
                continue
            evidence_ids.append(evidence_id)
            mapping.setdefault(evidence_id, []).append(claim_id)
            if stance == "contradicts":
                contradicts[evidence_id] = "contradicts"
            if raw_link.get("firsthand") is True:
                firsthand.append(evidence_id)
            if normalized_origin is not None:
                origins[evidence_id] = normalized_origin

        claim: dict[str, Any] = {
            "id": claim_id,
            "text": text.strip() if isinstance(text, str) else "",
            "evidence_ids": evidence_ids,
            "claims_source": source,
            "firsthand_source": _FIRSTHAND_SOURCE_BY_CLAIMS_SOURCE[source],
        }
        conflict_note = raw_claim.get("conflict_note")
        if conflict_note is not None:
            if not isinstance(conflict_note, str):
                offenders.append(f"{location}.conflict_note 必须是字符串")
            elif conflict_note.strip():
                claim["conflict_note"] = conflict_note.strip()
        if contradicts:
            claim["stance"] = contradicts
        if firsthand:
            claim["firsthand"] = firsthand
        if origins:
            claim["origin_overrides"] = origins
        if dangling_permalinks:
            dropped.append({
                "claim_id": claim_id,
                "reason": (
                    "dangling_evidence"
                    if evidence_ids
                    else "all_evidence_dangling"
                ),
                "permalinks": dangling_permalinks,
            })
        # 全悬空断言若保留，会违反至少一条 evidence 的既有契约，也无法计算证据簇；
        # 丢弃正文登记项但保留 claims_dropped 审计记录。
        if evidence_ids:
            registered.append(claim)

    if offenders:
        raise _error(f"断言登记失败，共 {len(offenders)} 处", offenders)
    return registered, mapping, dropped


def register_claims(
    store: Any,
    report_id: str,
    raw_claims: Sequence[Any],
    *,
    source: str,
    deduped: list[dict[str, Any]] | None = None,
    rejected: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """两条生产路径共用的固定落库入口。"""

    claims, mapping, dropped = prepare_claim_registration(
        store.list_evidence(report_id), raw_claims,
        source=source, deduped=deduped, rejected=rejected,
    )
    store.set_report_claims(report_id, claims, dropped=dropped)
    store.attach_claim_ids(report_id, mapping)
    return claims


def audit_dangling_claims(store: Any, report_id: str) -> dict[str, Any]:
    """§D-081 货 2：复查库里的 claims 引不引得到**本研究**的证据，悬空的必须显形。

    病象（真机 r-3b3482ca7f8b）：replay 原样复制了上一轮的 `extra.claims`，而
    `import_research` 给每行 evidence **重新生成 id**（两轮 820 行 id 交集 0）；
    本轮登记又被 2 个 `stance` 越界值整批打回，于是 `extra.claims` 留着那 1380 条
    复制来的断言，**2001 个 `evidence_ids` 在本研究一个都不存在**。`_audit_firsthand`
    算出 0 对一声不吭 return ⇒ 成品看着有 1380 条断言、其实一条都对不上证据，零报警。

    **显形阈值取「命中率 < 100%」，不拍经验阈值。** 理由：正常生产路径上
    `prepare_claim_registration` 只把**查得到的** evidence 写进 `evidence_ids`
    （悬空的 permalink 早进了 `claims_dropped`），所以本轮登记出来的 claims 命中率
    恒为 100%。任何 < 100% 都意味着「库里这份 claims 不是本轮登记出来的」——
    replay 复制来的、或登记失败留下的旧值——本身就是异常，没有需要容忍的正常带。

    **处置分两档：**
    - **全悬空**（`evidence_ids` 非空、一条都对不上）⇒ 移出 `extra.claims`，并写进
      `claims_dropped`（reason 沿用登记期的 `all_evidence_dangling`）。它在报告侧是
      纯假值：交叉验证维会把它当「有据的断言」计数，留着就是误导，清掉才叫显形。
    - **部分悬空** ⇒ **只报警不动它**。它还有真证据撑着，清掉会连真内容一起丢。

    只返回读数、只改库，⛔ 不在这里发事件也不打日志——判据要落在库与事件上，
    事件由调用方（`runtime._finalize_if_terminal`）按返回的读数发。
    """

    report = store.get_report(report_id)
    if report is None:
        return {}
    extra = report.get("extra") or {}
    claims = extra.get("claims")
    if not isinstance(claims, list) or not claims:
        return {}
    known = {str(row.get("id") or "") for row in store.list_evidence(report_id)}
    kept: list[Any] = []
    purged: list[str] = []
    refs = 0
    hit = 0
    for claim in claims:
        evidence_ids = (
            [str(value) for value in (claim.get("evidence_ids") or [])]
            if isinstance(claim, Mapping)
            else []
        )
        found = [value for value in evidence_ids if value in known]
        refs += len(evidence_ids)
        hit += len(found)
        claim_id = claim.get("id") if isinstance(claim, Mapping) else None
        if evidence_ids and not found and isinstance(claim_id, str) and claim_id:
            purged.append(claim_id)
            continue
        kept.append(claim)
    if purged:
        dropped = [
            dict(item) for item in (extra.get("claims_dropped") or [])
            if isinstance(item, Mapping)
        ]
        seen = {
            (str(item.get("claim_id")), str(item.get("reason"))) for item in dropped
        }
        for claim_id in purged:
            if (claim_id, DANGLING_CLAIM_REASON) in seen:
                continue
            seen.add((claim_id, DANGLING_CLAIM_REASON))
            dropped.append({
                "claim_id": claim_id,
                "reason": DANGLING_CLAIM_REASON,
                # 复制来的 claims 只带 evidence_ids，没有 permalink 可记；
                # 悬空的具体 id 进事件，这里只留「这条被清掉了」的库侧留痕。
                "permalinks": [],
            })
        store.set_report_claims(report_id, kept, dropped=dropped)
    return {
        "claims": len(claims),
        "refs": refs,
        "hit": hit,
        "missing": refs - hit,
        "hit_rate": (hit / refs) if refs else 1.0,
        "purged": purged,
        "kept": len(kept),
    }


__all__ = [
    "CLAIM_ID_PATTERN",
    "CLAIM_DROP_REASONS",
    "CLAIM_LINK_CLOSED_SETS",
    "DANGLING_CLAIM_REASON",
    "FIRSTHAND_SOURCES",
    "ClaimsRegistrationError",
    "audit_dangling_claims",
    "claims_from_documents",
    "prepare_claim_registration",
    "register_claims",
]
