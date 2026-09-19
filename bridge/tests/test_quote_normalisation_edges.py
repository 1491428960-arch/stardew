"""`_normalise_single_quoted_strings` 的手写状态机。

按**缺失行数**排序挑出来的（缺 6 行，其中 4 行真语句）。它把 Content Patcher 常见的
**单引号字符串**改成 JSON 字符串——CP 脚本里 `'...'` 是合法字符串，而 JSON 只认 `"..."`，
所以要把引号与内部转义**一起**改写成 JSON 语义。

缺的 4 行全在**单引号内的转义处理**上：

    \\'  → '         转义的单引号变成裸单引号
    \\\\ → \\\\        转义的反斜杠变成双反斜杠
    \\x  → \\x        其他转义原样保留反斜杠与字符

这三条错了会让 CP 原文里的转义序列变成非法 JSON 或语义变形——而它是**给下游解析用**的，
错了要到解析阶段才暴露。所以下面全部用**探针确认过的真实输出**当断言。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.profile_index import _normalise_single_quoted_strings


# --- 基本转换 ---------------------------------------------------------------


def test_a_single_quoted_string_becomes_double_quoted() -> None:
    assert _normalise_single_quoted_strings("'abc'") == '"abc"'


def test_chinese_content_is_kept() -> None:
    assert _normalise_single_quoted_strings("中文'引号'") == '中文"引号"'


def test_text_outside_quotes_is_kept_and_bare_quotes_are_converted() -> None:
    # 引号外的内容原样；每遇到一个单引号就切换状态并输出一个双引号。
    assert _normalise_single_quoted_strings("a'b'c") == 'a"b"c'
    assert _normalise_single_quoted_strings("a'b'c'd") == 'a"b"c"d'


def test_a_double_quoted_section_is_not_touched() -> None:
    # 双引号内的单引号不该被改写。
    assert _normalise_single_quoted_strings("\"a'b\"") == '"a\'b"'


# --- 单引号内的转义（缺的那几行）--------------------------------------------


def test_an_escaped_single_quote_becomes_a_bare_one() -> None:
    # 探针确认：`'a\'b'` → `"a'b"`。
    assert _normalise_single_quoted_strings("'a\\'b'") == '"a\'b"'


def test_an_escaped_backslash_stays_escaped() -> None:
    # 探针确认：`'a\\b'`（源码里两字符 `\` `\`）→ `"a\\b"`。
    assert _normalise_single_quoted_strings("'a\\\\b'") == '"a\\\\b"'


def test_other_escapes_keep_their_backslash() -> None:
    # 转义后跟普通字符时，反斜杠与字符都保留（这是给下游解析的 JSON 文本）。
    assert _normalise_single_quoted_strings("'a\\nb'") == '"a\\nb"'


def test_a_double_quote_inside_a_single_quoted_string_is_escaped() -> None:
    assert _normalise_single_quoted_strings("'a\"b'") == '"a\\"b"'


def test_control_characters_become_unicode_escapes() -> None:
    # TAB（0x09）在 JSON 字符串里必须转义。
    assert _normalise_single_quoted_strings("'a\tb'") == '"a\\u0009b"'


# --- 边界 -------------------------------------------------------------------


def test_an_unterminated_single_quote_still_opens() -> None:
    # 未闭合时：开头的单引号已转成双引号，其余按单引号内容处理。
    assert _normalise_single_quoted_strings("'unclosed") == '"unclosed'


def test_an_unterminated_double_quote_still_opens() -> None:
    assert _normalise_single_quoted_strings("\"unclosed") == '"unclosed'


@pytest.mark.parametrize("text", ["", "没有引号的普通文本", "123", "a b c"])
def test_plain_text_is_returned_unchanged(text: str) -> None:
    assert _normalise_single_quoted_strings(text) == text


def test_quotes_alternate_between_sections() -> None:
    # 先从双引号段出来，再进单引号段：两段的引号各自保持自己的形态。
    assert _normalise_single_quoted_strings("'a'\"b\"") == '"a""b"'


def test_the_result_is_always_a_string() -> None:
    for text in ["'a'", "", "a'b", "\"a", "'a\\'b'"]:
        assert isinstance(_normalise_single_quoted_strings(text), str)
