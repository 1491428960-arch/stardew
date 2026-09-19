"""`corpus` 的对白控制流拆分与清理。

2026-09-20 用覆盖率定位到 `corpus.py` 91%、44 行未覆盖，其中 **`L206-210`（连续 5 行）
是 `${…}` 表达式的整体保留分支**——而紧邻的 `{{…}}` 分支**已被覆盖**。又是
“**同构的两处只测了一处**”（与第 112 项同一模式）。

这两段的语义是：**在拆分对白分支时，不能把 `${男^女}` 与 `{{…}}` 这类表达式拆断**——
拆断了会把控制脚本当成 NPC 台词，直接污染模仿样本。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.corpus import (
    _split_dialogue_control_flow,
    clean_dialogue_noise,
    clean_dialogue_variants,
)


# --- 表达式不能被拆开 -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "${男^女}",
        "你好${男^女}再见",
        "${a}${b}",
        "{{i18n:x}}",
        "你好{{i18n:x}}再见",
    ],
)
def test_control_expressions_are_kept_whole(text: str) -> None:
    # 表达式内部可能含 `^`/`|`，拆开就会得到半截控制脚本。
    assert _split_dialogue_control_flow(text) == [text]


@pytest.mark.parametrize("text", ["${未闭合", "{{未闭合", "${a"])
def test_unterminated_expressions_fall_back_to_plain_text(text: str) -> None:
    # 找不到闭合符时不做特殊处理，整段当普通文本。
    assert _split_dialogue_control_flow(text) == [text]


# --- 分支分隔 ---------------------------------------------------------------


@pytest.mark.parametrize("separator", ["||", "^", "|"])
def test_branch_separators_split_the_text(separator: str) -> None:
    assert _split_dialogue_control_flow(f"a{separator}b") == ["a", "b"]


def test_a_stardew_branch_header_acts_as_a_boundary() -> None:
    # 形如 `6 0 Wed_01_02` 的分支头不是台词，但必须当边界，否则整段控制脚本
    # 会被当成一条可模仿的长句。
    branches = _split_dialogue_control_flow("6 0 Wed_01_02 你好")

    assert branches[-1] == " 你好"
    assert len(branches) == 2


def test_plain_text_stays_one_branch() -> None:
    assert _split_dialogue_control_flow("今天鸡舍那边挺忙的。") == ["今天鸡舍那边挺忙的。"]


# --- clean_dialogue_variants ------------------------------------------------


def test_narration_branches_are_dropped_entirely() -> None:
    # `%……` 是“NPC 没有理你”或事件旁白，不是 NPC 的说话内容。
    assert clean_dialogue_variants("%旁白一句") == []
    assert clean_dialogue_variants("  %前面有空格") == []


def test_gendered_expressions_keep_the_male_branch() -> None:
    # `${男^女}` 静态展开时取 `^` 左边那一支。
    assert clean_dialogue_variants("${男^女}你好") == ["男你好"]


def test_action_markers_are_stripped() -> None:
    assert clean_dialogue_variants("*微笑*你好") == ["你好"]


def test_the_at_sign_becomes_the_player_pronoun() -> None:
    assert clean_dialogue_variants("@你好") == ["你你好"]


def test_dialogue_markers_are_removed() -> None:
    # `$q`/`$d` 之类是控制标记，不该出现在台词里。
    #
    # 注意：它的模式是**贪婪**的（`[^#|]*`），而真实语法形如 `$q 0 null#问题#回答`
    # 一定带 `#` 终止符。这里把标记放在**末尾**，避免它把后面的正文一起吞掉——
    # 我最初写成 `"$q 你好"` 就踩了这个坑（整个字符串被吞成空）。
    variants = clean_dialogue_variants("今天鸡舍那边挺忙的。$q")

    assert variants == ["今天鸡舍那边挺忙的。"]


def test_a_branch_split_yields_one_variant_per_branch() -> None:
    variants = clean_dialogue_variants("第一句^第二句")

    assert variants == ["第一句", "第二句"]


def test_whitespace_is_collapsed() -> None:
    assert clean_dialogue_variants("你好    世界") == ["你好 世界"]


# --- clean_dialogue_noise ---------------------------------------------------


def test_single_letter_residue_between_chinese_is_cleaned() -> None:
    # 个别中文导出会在中文句间混入 OCR/编码残片（例如“…… e 你”）。
    assert clean_dialogue_noise("你好。 e 世界") == "你好。世界"
    assert clean_dialogue_variants("你好。 e 世界") == ["你好。世界"]


def test_it_is_conservative_about_letters_elsewhere() -> None:
    # 只在“中文标点 + 单个拉丁字母 + 中文”这一形态下动手，避免误删真正的英文术语。
    assert clean_dialogue_noise("N 你好") == "N 你好"
    assert clean_dialogue_noise("正常一句") == "正常一句"
    assert clean_dialogue_noise("Hello 世界") == "Hello 世界"
