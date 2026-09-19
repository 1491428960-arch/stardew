"""`_longest_common_phrase_length`：最长公共**连续**短语的 DP 实现。

它给行为样例的匹配打分提供输入（`_behavior_topic_score` 等），
**算错了不会崩，只会静默选错证据**——所以边界值得钉住。此前它**没有任何直接测试**。

注意一个容易误解的语义：函数会**丢弃所有非字母数字字符**（标点、空白都算），
因此 `"a-b-c"` 与 `"abc"` 会被判为最长公共短语 **3**——标点两侧的内容被当成连续。
对中文（标点密集）这是有意的宽松，但值得写清楚。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.profile_index import _longest_common_phrase_length


@pytest.mark.parametrize("value", [None, 42, [], {}, b"abc"])
def test_non_string_inputs_give_zero(value: object) -> None:
    assert _longest_common_phrase_length(value, "abc") == 0
    assert _longest_common_phrase_length("abc", value) == 0


@pytest.mark.parametrize("value", ["", "   ", "!!!", "，。！"])
def test_inputs_without_alphanumeric_characters_give_zero(value: str) -> None:
    # 标点与空白被完全忽略，所以这些等价于空串。
    assert _longest_common_phrase_length(value, "abc") == 0
    assert _longest_common_phrase_length("abc", value) == 0


def test_matching_is_case_insensitive() -> None:
    assert _longest_common_phrase_length("Hello", "hello") == 5
    assert _longest_common_phrase_length("HELLO", "hello") == 5


def test_it_finds_the_longest_run_not_the_total_overlap() -> None:
    # "abcXdef" 与 "abcYdef" 公共字符不少，但**连续**的最长只有 3。
    assert _longest_common_phrase_length("abcXdef", "abcYdef") == 3


def test_it_handles_chinese_phrases() -> None:
    assert _longest_common_phrase_length("谢恩今天心情不错", "今天天气很好") == 2  # “今天”
    assert _longest_common_phrase_length("鸡舍今天忙吗", "鸡舍今天忙吗") == 6


def test_punctuation_is_ignored_on_both_sides() -> None:
    # 中文标点密集，忽略标点后“你好，世界”能与“你好世界”匹配上。
    assert _longest_common_phrase_length("你好，世界", "你好世界") == 4


def test_punctuation_can_make_two_segments_look_contiguous() -> None:
    # 上面那条宽松规则的副作用：标点被丢掉后，“a-b-c”与“abc”被判为连续 3 个字符。
    # 固化成契约——若将来改成“标点也参与比较”，这条会失败并提醒更新。
    assert _longest_common_phrase_length("a-b-c", "abc") == 3


def test_no_shared_characters_gives_zero() -> None:
    assert _longest_common_phrase_length("abc", "xyz") == 0
    assert _longest_common_phrase_length("中文", "abc") == 0


def test_empty_side_gives_zero() -> None:
    assert _longest_common_phrase_length("abc", "") == 0
    assert _longest_common_phrase_length("", "abc") == 0


def test_single_character_matches() -> None:
    assert _longest_common_phrase_length("a", "a") == 1
    assert _longest_common_phrase_length("a", "b") == 0
