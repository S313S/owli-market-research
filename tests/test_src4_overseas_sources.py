"""§SRC-4 海外三源在 r-20271e8a5028 里空手而归的三处修法 + 正式稿原因人话。"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── X：钱闸六键退到 ~/.owli/.env ────────────────────────────────────────────

_X_KEYS = {
    "OWLI_X_WEEKLY_BUDGET_USD": "1",
    "OWLI_X_BALANCE_USD": "10",
    "OWLI_X_BILLING_CYCLE_CAP_USD": "10",
    "OWLI_X_BILLING_CYCLE_SPENT_USD": "0",
    "OWLI_X_PRICE_PER_READ_USD": "0.005",
}


def _write_env(path: Path, extra: dict[str, str]) -> Path:
    lines = ["# 注释行", 'X_BEARER_TOKEN="tok"', *[f"{k}={v}" for k, v in extra.items()]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_x_进程环境缺键时从env文件补齐(tmp_path) -> None:
    from app.sources import x

    env_file = _write_env(
        tmp_path / ".env",
        {**_X_KEYS, "OWLI_X_USAGE_DB_PATH": str(tmp_path / "usage.db")},
    )
    config, store = x.load_runtime_config({}, env_path=env_file)
    assert str(config.price_per_read_usd) == "0.005"
    assert str(config.balance_usd) == "10"
    assert (tmp_path / "usage.db").is_file()
    assert store is not None


def test_x_进程环境优先于env文件(tmp_path) -> None:
    from app.sources import x

    env_file = _write_env(
        tmp_path / ".env",
        {**_X_KEYS, "OWLI_X_USAGE_DB_PATH": str(tmp_path / "file.db")},
    )
    environ = {
        **_X_KEYS,
        "OWLI_X_BALANCE_USD": "3",
        "OWLI_X_USAGE_DB_PATH": str(tmp_path / "env.db"),
    }
    config, _ = x.load_runtime_config(environ, env_path=env_file)
    assert str(config.balance_usd) == "3"
    assert (tmp_path / "env.db").is_file()
    assert not (tmp_path / "file.db").exists()


def test_x_两边都缺时仍报缺失且点名键(tmp_path) -> None:
    from app.sources import x

    env_file = _write_env(tmp_path / ".env", {"OWLI_X_WEEKLY_BUDGET_USD": "1"})
    with pytest.raises(ValueError, match="OWLI_X_BALANCE_USD"):
        x.load_runtime_config({}, env_path=env_file)
    with pytest.raises(ValueError, match="X 运行时配置缺失"):
        x.load_runtime_config({}, env_path=tmp_path / "missing.env")


def test_x_search在文件补齐后不再报runtime_config_missing(tmp_path) -> None:
    from app.sources import x

    env_file = _write_env(
        tmp_path / ".env",
        {**_X_KEYS, "OWLI_X_USAGE_DB_PATH": str(tmp_path / "usage.db")},
    )
    events: list = []
    real_loader = x.load_runtime_config
    with (
        patch.object(
            x, "load_runtime_config",
            side_effect=lambda: real_loader({}, env_path=env_file),
        ),
        patch.object(x, "XRecentSearch") as recent,
    ):
        recent.return_value.search.return_value = x.XSearchResult(
            evidence=[], conclusion={"status": "ok"}
        )
        result = x.search("Doubao", "7d", on_event=events.append)
    assert result.conclusion == {"status": "ok"}
    assert not [e for e in events if e.get("type") == "source_unavailable"]


# ── Product Hunt：瞬时错误重试、原因透传、翻页封顶、429 等待封顶 ───────────────

def _ph_response(body: bytes):
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = body
    response.headers.items.return_value = [("x-rate-limit-remaining", "6000")]
    response.status = 200
    return response


def test_ph_握手EOF一次后重试成功() -> None:
    from app.sources import product_hunt as ph

    ok = _ph_response(b'{"data": {"viewer": 1}}')
    with (
        patch.object(
            ph, "urlopen",
            side_effect=[URLError("EOF occurred in violation of protocol"), ok],
        ) as open_url,
        patch.object(ph.time, "sleep") as sleep,
    ):
        result = ph._post_graphql("tok", "{ viewer }", {})
    assert result.status == 200 and result.payload == {"data": {"viewer": 1}}
    assert open_url.call_count == 2
    sleep.assert_called_once_with(0.5)


def test_ph_连续失败后错误原文进消息() -> None:
    from app.sources import product_hunt as ph

    with (
        patch.object(
            ph, "urlopen", side_effect=URLError("[SSL: UNEXPECTED_EOF_WHILE_READING]"),
        ),
        patch.object(ph.time, "sleep"),
    ):
        with pytest.raises(RuntimeError) as info:
            ph._post_graphql("tok", "{ viewer }", {})
    message = str(info.value)
    assert "网络请求失败" in message
    assert "UNEXPECTED_EOF_WHILE_READING" in message
    assert "tok" not in message


def _node(index: int, name: str) -> dict:
    return {
        "id": str(index), "name": name, "tagline": "一句话", "votesCount": 100 - index,
        "commentsCount": 1, "createdAt": "2026-08-19T00:00:00Z",
        "url": f"https://www.producthunt.com/posts/p-{index}",
        "topics": {"edges": []},
    }


def _page(nodes: list[dict], next_cursor: str | None):
    from app.sources.product_hunt import GraphQLResponse

    return GraphQLResponse(
        status=200, headers={"x-rate-limit-remaining": "6000"},
        payload={"data": {"posts": {
            "edges": [{"node": n} for n in nodes],
            "pageInfo": {"hasNextPage": next_cursor is not None, "endCursor": next_cursor},
        }}},
    )


def test_ph_冷门词翻到页数上限即停并如实报空(tmp_path) -> None:
    from app.sources import product_hunt as ph

    calls: list[dict] = []

    def fake_post(token, query, variables):
        calls.append(dict(variables))
        page = len(calls)
        return _page(
            [_node(page * 10 + i, f"别的产品 {page}-{i}") for i in range(2)],
            f"cursor-{page}",
        )

    events: list = []
    with (
        patch.object(ph, "_load_token", return_value="tok"),
        patch.object(ph, "_post_graphql", side_effect=fake_post),
        patch.object(ph, "_BUDGET", ph.CreditBudget()),
        patch.object(ph, "_utc_now", return_value=datetime(2026, 8, 20, tzinfo=timezone.utc)),
    ):
        result = ph.search(
            "Doubao", "365d", limit=20, page_size=2, max_pages=3,
            on_event=events.append, log_root=tmp_path,
        )

    assert result == []
    assert len(calls) == 3
    kinds = [e.raw.get("kind") for e in events]
    assert kinds == ["page_cap_reached", "empty_window"]
    capped = next(e for e in events if e.raw.get("kind") == "page_cap_reached")
    assert capped.raw["pages_scanned"] == 3 and capped.raw["matched"] == 0


def test_ph_封顶前命中的条目照常返回(tmp_path) -> None:
    from app.sources import product_hunt as ph

    pages = [
        _page([_node(1, "别的"), _node(2, "Doubao Desktop")], "c1"),
        _page([_node(3, "别的 2"), _node(4, "别的 3")], "c2"),
        _page([_node(5, "别的 4"), _node(6, "别的 5")], "c3"),
    ]
    with (
        patch.object(ph, "_load_token", return_value="tok"),
        patch.object(ph, "_post_graphql", side_effect=lambda *_: pages.pop(0)),
        patch.object(ph, "_BUDGET", ph.CreditBudget()),
        patch.object(ph, "_utc_now", return_value=datetime(2026, 8, 20, tzinfo=timezone.utc)),
    ):
        result = ph.search(
            "doubao", "365d", limit=20, page_size=2, max_pages=3, log_root=tmp_path,
        )
    assert [item["title"] for item in result] == ["Doubao Desktop"]


def test_ph_默认页数上限是常量且提示词写明本地匹配() -> None:
    from app.sources import product_hunt as ph

    assert ph._MAX_PAGES == 10
    assert "本地匹配" in ph.SOURCE_SPEC.prompt_hint
    with pytest.raises(ValueError, match="max_pages"):
        with patch.object(ph, "_load_token", return_value="tok"):
            ph.search("x", "7d", max_pages=0)


def test_ph_429等待封顶两分钟(tmp_path) -> None:
    from app.sources import product_hunt as ph

    limited = ph.GraphQLResponse(
        status=429,
        headers={"x-rate-limit-remaining": "0", "x-rate-limit-reset": "900"},
        payload={"errors": [{"message": "rate limited"}]},
    )
    with (
        patch.object(ph, "_load_token", return_value="tok"),
        patch.object(ph, "_BUDGET", ph.CreditBudget()),
        patch.object(
            ph, "_post_graphql", side_effect=[limited, _page([_node(1, "Doubao")], None)],
        ),
        patch.object(ph.time, "sleep") as sleep,
        patch.object(ph, "_utc_now", return_value=datetime(2026, 8, 20, tzinfo=timezone.utc)),
    ):
        result = ph.search("doubao", "7d", limit=1, log_root=tmp_path)
    assert len(result) == 1
    sleep.assert_called_once_with(120.0)


# ── HN：三级放宽 ───────────────────────────────────────────────────────────

def test_hn_高分口径无命中时放宽分数再纳入评论() -> None:
    from app.sources import hn

    comment_hit = {
        "objectID": "9001", "comment_text": "Doubao is &quot;fine&quot;",
        "story_title": "Seedance 2.5", "author": "bob", "points": None,
        "num_comments": None, "created_at": "2026-08-02T00:00:00Z",
        "_tags": ["comment", "author_bob", "story_1"],
    }
    responses = [{"hits": []}, {"hits": []}, {"hits": [comment_hit]}]
    with (
        patch.object(hn, "_now_epoch", return_value=1_800_000_000),
        patch.object(hn, "_utc_now_iso", return_value="2026-09-16T00:00:00+00:00"),
        patch.object(hn, "_fetch_json", side_effect=responses) as fetch,
    ):
        result = hn.search("Doubao", "90d")

    queries = [parse_qs(urlparse(call.args[0]).query) for call in fetch.call_args_list]
    assert [q["tags"] for q in queries] == [["story"], ["story"], ["comment"]]
    assert queries[0]["numericFilters"] == ["created_at_i>1792224000,points>50"]
    assert queries[1]["numericFilters"] == ["created_at_i>1792224000"]
    assert queries[2]["numericFilters"] == ["created_at_i>1792224000"]
    [evidence] = result
    assert evidence["source_type"] == "comment"
    assert evidence["title"] == "Seedance 2.5"
    assert evidence["content_excerpt"] == 'Doubao is "fine"'
    assert evidence["permalink"] == "https://news.ycombinator.com/item?id=9001"


def test_hn_第二级命中即停不再查评论() -> None:
    from app.sources import hn

    story = {
        "objectID": "1", "title": "ByteDance Launches Doubao Work", "points": 2,
        "created_at": "2026-08-26T00:00:00Z",
    }
    with (
        patch.object(hn, "_now_epoch", return_value=1_800_000_000),
        patch.object(
            hn, "_fetch_json",
            side_effect=[{"hits": []}, {"hits": [story]}, {"hits": [{"objectID": "x"}]}],
        ) as fetch,
    ):
        result = hn.search("Doubao", "90d")
    assert fetch.call_count == 2
    assert [e["platform_item_id"] for e in result] == ["1"]
    assert result[0]["source_type"] == "post"


def test_hn_三级全空返回空数组且恰好三次请求() -> None:
    from app.sources import hn

    with patch.object(hn, "_fetch_json", return_value={"hits": []}) as fetch:
        assert hn.search("nothing-here", "90d") == []
    assert fetch.call_count == 3


# ── 正式稿「哪些没采到」：tool_unavailable 不再印成「原因未记录」 ───────────

def test_polish_工具不可用与额度用尽有人话() -> None:
    from app.report.polish.run import missing_table

    md = missing_table([
        {"goal_id": "g", "chapter_id": "c1", "reason": "tool_unavailable"},
        {"goal_id": "g", "chapter_id": "c2", "reason": "quota_exhausted"},
        {"goal_id": "g", "chapter_id": "c3", "reason": "still_unknown"},
    ])
    assert "接不上" in md and "额度用完" in md
    assert md.count("原因未记录") == 1
    assert "tool_unavailable" not in md and "quota_exhausted" not in md
