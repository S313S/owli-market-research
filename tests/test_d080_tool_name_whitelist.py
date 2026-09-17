"""§D-080：白名单项必须与 SDK 实际暴露的工具名逐字一致，且与注册名同源。

病象（真机 `r-96e0257a86b4` goal-1/ch-13 转录）：Codex 报 `at capacity` → §D-074
让路到 Claude → 会话 tools 里**有** `mcp__owli_sources__source_hacker_news`，模型
按这个名字调用 → 被自家闸拒 `工具不在 capability 白名单：...` → 写手落盘 `[]`，
章判 `tool_unavailable`。病根是注册名（`source.<id>`，被 SDK 改写成
`source_<id>`）与白名单项（自己拼的 `source.<id>`，保留了点）分了叉。

⚠️ 本文件的尺子有两把，缺一不可：
1. **对得上真机**——白名单项等于 SDK 实测拼法（实测表见 `source_mcp` 里
   `_SDK_UNSAFE_NAME_CHARS` 上方的注释，2026-09-17 真 CLI + 真 stdio server 量的）。
2. **不许再分叉**——白名单项必须从注册名推导，而不是各写各的字面量；只锁读数不锁
   推导的话，下次有人改注册名，尺子照样绿、线上照样全拒。
"""

from __future__ import annotations

import re

from app.adapters.source_mcp import (
    MCP_SERVER_NAME,
    exposed_tool_name,
    registered_tool_name,
    sdk_name_segment,
)


def test_d080_白名单项用下划线不用点() -> None:
    """真机里模型看到的就是这一个名字，⛔ 不是带点那个。"""

    assert exposed_tool_name("hacker_news") == "mcp__owli_sources__source_hacker_news"
    assert "." not in exposed_tool_name("hacker_news")


def test_d080_逻辑工具名仍然带点() -> None:
    """capability.tools / plan / `call_tool` 全线用的仍是 `source.<id>`，⛔ 不能跟着改。"""

    assert registered_tool_name("hacker_news") == "source.hacker_news"


def test_d080_sdk_改写规则按实测逐字符替换() -> None:
    """2026-09-17 实测读数逐条回放：非 `[A-Za-z0-9_-]` 逐字符换 `_`。

    ⛔ 不折叠连续下划线、⛔ 不去首尾下划线、⛔ 不改大小写、连字符原样留——
    这四条都是实测出来的，按单一样例「点变下划线」硬编会写错其中至少三条。
    """

    measured = {
        "source.hacker_news": "source_hacker_news",
        "a.b.c": "a_b_c",
        "Upper.Case": "Upper_Case",
        "dash-keep.dot": "dash-keep_dot",
        "double..dot": "double__dot",
        ".leading": "_leading",
        "trailing.": "trailing_",
        "sp ace": "sp_ace",
        "中文.源": "____",
        "under__score": "under__score",
        "plus+sign": "plus_sign",
        "slash/x": "slash_x",
        "colon:x": "colon_x",
        "owli.probe-X": "owli_probe-X",
    }
    assert {raw: sdk_name_segment(raw) for raw in measured} == measured


def test_d080_白名单项与注册名同源() -> None:
    """守卫：白名单项必须是「注册名过一遍 SDK 改写」，⛔ 不许两头各写各的字面量。

    改了注册名而忘了白名单（或反过来）时，这条会红——§D-080 那次分叉正是无人看守。
    """

    for source_id in ("hacker_news", "reddit", "xiaohongshu", "douyin", "x"):
        registered = registered_tool_name(source_id)
        expected = (
            f"mcp__{sdk_name_segment(MCP_SERVER_NAME)}__{sdk_name_segment(registered)}"
        )
        assert exposed_tool_name(source_id) == expected


def test_d080_注册名与白名单项确实来自同一个函数() -> None:
    """再拧一道：MCP 服务端注册工具时用的名字，就是 `registered_tool_name` 的返回值。

    上一条只证明「白名单由某个 `source.<id>` 推导」，证明不了服务端真按这个名字注册。
    这里直接去问 `_tool_definition`——它是 `_serve` 建工具清单的那个函数。
    """

    from app.adapters.source_mcp import _tool_definition

    class _Tool:
        def __init__(self, **values: object) -> None:
            self.__dict__.update(values)

    for source_id in ("hacker_news", "douyin"):
        definition = _tool_definition(_Tool, source_id)
        assert definition.name == registered_tool_name(source_id)
        assert exposed_tool_name(source_id).endswith(
            sdk_name_segment(definition.name)
        )


def test_d080_白名单项落在_sdk_允许的字符集里() -> None:
    """Anthropic 侧工具名只收 `[A-Za-z0-9_-]`；拼出集外字符等于必被拒。"""

    pattern = re.compile(r"^mcp__[A-Za-z0-9_-]+__[A-Za-z0-9_-]+$")
    for source_id in ("hacker_news", "reddit", "product_hunt", "x"):
        assert pattern.match(exposed_tool_name(source_id))
