"""`_select_behavior_examples` 的边界与两条兜底路径。

按**缺失行数**排序挑出来的（缺 12 行）。它从行为样例里挑少量“参考卡”进 few-shot，
而代码里的注释点明了三道门：

    索引构建层已经拦截未审核样例；这里再做一次边界防护，避免直接传入 PromptBuilder 的
    model_draft/model_review 进入 few-shot。缺少 sourceType 的旧测试/旧调用保持兼容。

以及一条重要的保守规则：

    泛日常没有可提取的具体对象……**具体话题仍然必须命中**，只有泛日常示例允许走这个
    保守兜底。

所以下面既测“拒绝”（未审核、空文本、具体话题不命中），也测“兜底”（泛日常 + 无重复主题）。
"""

from __future__ import annotations

from stardew_ai_bridge.prompts import _select_behavior_examples


def _example(
    player_input: str = "鸡舍那边怎么样",
    reply: str = "今天鸡舍那边挺忙的，不过还行。",
    *,
    topic: str = "farm_work",
    topic_keywords: tuple[str, ...] = ("鸡舍",),
    source_type: str | None = "handcrafted_example",
) -> dict[str, object]:
    item: dict[str, object] = {
        "playerInput": player_input,
        "npcReply": reply,
        "topic": topic,
        "topicKeywords": list(topic_keywords),
    }
    if source_type is not None:
        item["sourceType"] = source_type
    return item


# --- 入口与上限 -------------------------------------------------------------


def test_a_non_sequence_input_yields_nothing() -> None:
    for bad in (None, "不是序列", 42, {"k": 1}):
        assert _select_behavior_examples(bad, "你好") == []


def test_a_zero_limit_yields_nothing() -> None:
    assert _select_behavior_examples([_example()], "鸡舍那边怎么样", limit=0) == []


def test_the_limit_is_capped() -> None:
    # 上限是 2；给很大的值也只能拿到 2 条。
    examples = [
        _example(player_input="鸡舍那边怎么样", reply=f"第 {i} 条鸡舍回复。")
        for i in range(5)
    ]

    assert len(_select_behavior_examples(examples, "鸡舍那边怎么样", limit=99)) <= 2


# --- 条目级过滤 -------------------------------------------------------------


def test_non_mapping_items_are_skipped() -> None:
    assert _select_behavior_examples(["不是映射", 42], "鸡舍那边怎么样") == []


def test_items_without_both_sides_of_the_exchange_are_skipped() -> None:
    assert _select_behavior_examples([_example(player_input="")], "鸡舍那边怎么样") == []
    assert _select_behavior_examples([_example(reply="")], "鸡舍那边怎么样") == []


def test_unapproved_source_types_are_rejected() -> None:
    # model_draft / model_review 不能进 few-shot。
    for bad in ("model_draft", "model_review", "随便什么"):
        assert _select_behavior_examples([_example(source_type=bad)], "鸡舍那边怎么样") == [], bad


def test_a_missing_source_type_is_still_accepted() -> None:
    # “缺少 sourceType 的旧测试/旧调用保持兼容”。
    assert _select_behavior_examples([_example(source_type=None)], "鸡舍那边怎么样") != []


def test_a_bad_item_does_not_hide_a_good_one() -> None:
    examples = [_example(source_type="model_draft"), _example(reply="今天鸡舍那边挺忙的。")]

    assert _select_behavior_examples(examples, "鸡舍那边怎么样") != []


# --- 具体话题必须命中 -------------------------------------------------------


def test_a_specific_topic_that_does_not_match_yields_nothing() -> None:
    # 玩家问的是别的事，而样例只讲鸡舍 → 不能拿它当参考卡。
    example = _example(player_input="镇上的图书馆怎么样", topic_keywords=("鸡舍",))

    assert _select_behavior_examples([example], "你最近在看什么书") == []


def test_a_matching_specific_topic_is_selected() -> None:
    example = _example()

    assert _select_behavior_examples([example], "鸡舍那边怎么样") != []


# --- 泛日常的保守兜底 -------------------------------------------------------


def test_generic_small_talk_without_plain_candidates_yields_nothing() -> None:
    # 泛日常输入 + 样例的主题都不在“日常主题”白名单里 → 不兜底。
    example = _example(topic="farm_work", topic_keywords=("鸡舍",))

    assert _select_behavior_examples([example], "最近怎么样") == []


def test_generic_small_talk_with_a_plain_candidate_is_selected() -> None:
    # 这条正是注释里说的兜底：泛日常没有可提取的对象，允许用 daily 类行为卡。
    example = _example(topic="daily_status", topic_keywords=("最近", "怎么样"))

    assert _select_behavior_examples([example], "最近怎么样") != []


def test_an_empty_player_input_skips_the_generic_fallback() -> None:
    # player_input 为空时不走兜底分支，直接按匹配分排序。
    example = _example(topic="daily_status", topic_keywords=("最近",))

    assert isinstance(_select_behavior_examples([example], "   "), list)


# --- 两轮去重 ---------------------------------------------------------------


def test_repeated_topics_are_deferred_not_dropped() -> None:
    # 第二轮才补位：两条主题相同但内容不同，选不满时仍能都拿到。
    examples = [
        _example(reply="今天鸡舍那边挺忙的，不过还行。"),
        _example(reply="鸡舍的鸡最近下蛋很勤快。"),
    ]

    got = _select_behavior_examples(examples, "鸡舍那边怎么样", limit=2)

    assert len(got) == 2


def test_identical_deferred_entries_are_not_duplicated() -> None:
    # 第二轮补位时会跳过“问题与回复都相同”的条目。
    examples = [_example(), _example()]

    assert len(_select_behavior_examples(examples, "鸡舍那边怎么样", limit=2)) == 1


def test_different_topics_are_both_selected() -> None:
    examples = [
        _example(reply="今天鸡舍那边挺忙的。"),
        _example(
            player_input="鸡舍那边怎么样",
            reply="鸡舍的鸡最近下蛋很勤快。",
            topic="farm_eggs",
            topic_keywords=("鸡舍", "下蛋"),
        ),
    ]

    assert len(_select_behavior_examples(examples, "鸡舍那边怎么样", limit=2)) == 2


def test_the_result_is_a_list_of_dicts() -> None:
    got = _select_behavior_examples([_example()], "鸡舍那边怎么样")

    assert isinstance(got, list)
    assert all(isinstance(item, dict) for item in got)
