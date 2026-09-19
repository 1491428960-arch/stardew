"""宽容 JSON 的四个文本预处理器：注释、单引号、尾逗号、控制字符。

`profile_index` 靠它们读 Mod 的 `content.json`（Content Patcher 允许注释、尾逗号与单引号字符串），
读错了整个资料索引都会偏。四条都是**手写状态机**，最容易出错的正是“字符串里的内容被误判”：
`"http://x"` 里的 `//` 不是注释，`"x,}"` 里的 `,}` 也不是尾逗号。这里把这些保护钉住。
"""

from __future__ import annotations

import json

import pytest

from stardew_ai_bridge.profile_index import (
    _escape_control_chars_in_strings,
    _normalise_single_quoted_strings,
    _remove_trailing_commas,
    _strip_json_comments,
)


# --- _strip_json_comments ---------------------------------------------------


def test_double_slash_inside_a_string_is_not_a_comment() -> None:
    # 最容易踩的一条：URL 里的 // 必须原样保留。
    assert _strip_json_comments('{"url": "http://x/y"}') == '{"url": "http://x/y"}'


def test_block_comment_openers_inside_a_string_are_kept() -> None:
    raw = '{"a": "/* not a comment */"}'

    assert _strip_json_comments(raw) == raw


def test_single_quoted_strings_also_protect_their_contents() -> None:
    # 单引号同样会开启“字符串状态”，里面的 // 也不删。
    assert _strip_json_comments("{'a': 'http://x'}") == "{'a': 'http://x'}"


def test_line_comments_are_removed_but_the_newline_survives() -> None:
    assert _strip_json_comments('{"a": 1} // c\n{"b": 2}') == '{"a": 1} \n{"b": 2}'


def test_block_comments_are_removed() -> None:
    assert _strip_json_comments('{"a": /* c */ 1}') == '{"a":  1}'


def test_an_unterminated_block_comment_swallows_the_rest() -> None:
    # 没闭合就一路吞到结尾——不做“猜哪里结束”的补救。
    assert _strip_json_comments('{"a": 1} /* open') == '{"a": 1} '


def test_escaped_quote_does_not_end_the_string() -> None:
    # \" 之后的 // 仍在字符串里，不该被当注释。
    raw = '{"a": "say \\" // still inside"}'

    assert _strip_json_comments(raw) == raw


# --- _normalise_single_quoted_strings ---------------------------------------


def test_single_quotes_become_double_quotes() -> None:
    assert _normalise_single_quoted_strings("{'a': 'b'}") == '{"a": "b"}'


def test_double_quotes_inside_single_quoted_strings_get_escaped() -> None:
    assert (
        _normalise_single_quoted_strings("""{'a': 'say "hi"'}""")
        == '{"a": "say \\"hi\\""}'
    )


def test_control_characters_become_unicode_escapes() -> None:
    # JSON 字符串里不能有裸换行。
    assert _normalise_single_quoted_strings("{'a': 'x\ny'}") == '{"a": "x\\u000ay"}'


def test_single_quotes_inside_double_quoted_strings_are_untouched() -> None:
    raw = '{"a": "it\'s"}'

    assert _normalise_single_quoted_strings(raw) == raw


# --- _remove_trailing_commas ------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[1, 2, ]", "[1, 2 ]"),
        ('{"a": 1, }', '{"a": 1 }'),
        ('{"a": [1, ], "b": 2}', '{"a": [1 ], "b": 2}'),
    ],
)
def test_trailing_commas_are_removed(raw: str, expected: str) -> None:
    assert _remove_trailing_commas(raw) == expected


def test_comma_followed_by_brace_inside_a_string_is_kept() -> None:
    # 与注释那条同源的保护：字符串里的 ,} 不是尾逗号。
    raw = '{"a": "x,}"}'

    assert _remove_trailing_commas(raw) == raw


# --- _escape_control_chars_in_strings ---------------------------------------


def test_raw_newlines_inside_strings_are_escaped() -> None:
    assert _escape_control_chars_in_strings('{"a": "x\ny"}') == '{"a": "x\\u000ay"}'


def test_text_outside_strings_is_left_alone() -> None:
    # 结构里的换行（美化格式）不属于字符串内容，不该被动。
    raw = '{"a": 1,\n "b": 2}'

    assert _escape_control_chars_in_strings(raw) == raw


# --- 组合：四个处理器串起来后仍应可解析 -------------------------------------


def test_the_four_processors_together_produce_parsable_json() -> None:
    dirty = """{
        // 注释
        'url': 'http://example.com/a',
        'note': 'say "hi"',
        'list': [1, 2, ],
    }"""

    repaired = _escape_control_chars_in_strings(
        _remove_trailing_commas(
            _normalise_single_quoted_strings(_strip_json_comments(dirty))
        )
    )

    assert json.loads(repaired) == {
        "url": "http://example.com/a",
        "note": 'say "hi"',
        "list": [1, 2],
    }
