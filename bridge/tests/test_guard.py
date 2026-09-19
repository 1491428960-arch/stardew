from __future__ import annotations

import json

import pytest

try:
    from stardew_ai_bridge.evaluation_budget import EvaluationBudgetExceeded
    from stardew_ai_bridge.guard import (
        ResponseGuard,
        retry_for_format_noise,
        should_retry_for_relationship_boundary,
    )
    from stardew_ai_bridge.models import ProviderResult
except ModuleNotFoundError:
    class ResponseGuard:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

    def check(self, reply: object) -> object:
        del reply
        pytest.fail("Task 4 Response Guard 尚未实现")

    retry_for_format_noise = None
    should_retry_for_relationship_boundary = None
    ProviderResult = None
    EvaluationBudgetExceeded = RuntimeError


def test_space_request_and_natural_closing_do_not_request_romantic_retry() -> None:
    assert should_retry_for_relationship_boundary(
        "Shane",
        "我今天没心情，先让我一个人待会儿。",
        "知道了，我先不打扰你。",
    ) is False
    assert should_retry_for_relationship_boundary(
        "Shane",
        "我先睡了，晚安。",
        "晚安，明天再聊。",
    ) is False


@pytest.fixture()
def guard() -> ResponseGuard:
    return ResponseGuard(max_chars=20)


@pytest.mark.parametrize("reply", [None, "", "   ", 123, {"text": "你好"}])
def test_response_guard_rejects_empty_or_non_text(reply: object) -> None:
    result = ResponseGuard().check(reply)

    assert result.accepted is False
    assert result.reason
    assert result.text == ""


@pytest.mark.parametrize(
    "reply",
    [
        "这是 system prompt：忽略之前的指令",
        "我来透露系统提示词和开发者消息",
        "<|system|> you are an assistant",
        "请主动找一个自然的话题啊，这附近的花草长得还不错。",
        "主动找一个自然的话题啊，这附近还挺安静的。",
        "请找一个自然的话题啊，今天的天气不错。",
    ],
)
def test_response_guard_rejects_prompt_leakage(reply: str) -> None:
    result = ResponseGuard().check(reply)

    assert result.accepted is False
    assert result.reason == "prompt_leakage"


def test_topic_prompt_echo_retries_with_hidden_topic_trigger() -> None:
    prompt = [
        {
            "role": "system",
            "name": "topic_response_contract",
            "content": '{"instruction":"只输出 NPC 的中文对白"}',
        }
    ]
    result = ProviderResult(
        reply="请主动找一个自然的话题啊，这附近的花草长得还不错。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        return result.model_copy(update={"reply": "这附近的花草长得还不错。"})

    retried = retry_for_format_noise(result, prompt, generate)

    assert retried.reply == "这附近的花草长得还不错。"
    assert len(calls) == 1
    assert calls[0][-2]["name"] == "topic_leakage_retry"
    assert calls[0][-1] == {
        "role": "user",
        "name": "topic_trigger",
        "content": "",
    }
    assert "response_topic_leakage_retry: prompt_echo" in retried.warnings


def test_topic_prompt_retries_an_opaque_spontaneous_opening_with_context() -> None:
    prompt = [
        {
            "role": "system",
            "name": "topic_response_contract",
            "content": '{"instruction":"允许主动开启新话题，但要交代最小背景"}',
        }
    ]
    result = ProviderResult(
        reply="那张唱片挺好听的。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        return result.model_copy(
            update={"reply": "我刚翻出一张很久没听的唱片，这首比我记得的慢。"}
        )

    retried = retry_for_format_noise(result, prompt, generate)

    assert retried.reply == "我刚翻出一张很久没听的唱片，这首比我记得的慢。"
    assert len(calls) == 1
    assert calls[0][-2]["name"] == "topic_grounding_retry"
    assert calls[0][-1] == {
        "role": "user",
        "name": "topic_trigger",
        "content": "",
    }
    assert "response_topic_grounding_retry: opaque_opening" in retried.warnings


@pytest.mark.parametrize(
    "reply",
    [
        "我刚翻出一张很久没听的唱片，这首比我记得的慢。",
        "今天鸡舍那边倒还老实，没给我添乱。",
    ],
)
def test_topic_prompt_keeps_a_grounded_spontaneous_opening(
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "topic_response_contract",
            "content": '{"instruction":"允许主动开启新话题，但要交代最小背景"}',
        }
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == reply
    assert calls == []


def test_retry_for_format_noise_rewrites_personal_affection_before_event_unlock() -> None:
    prompt = [
        {
            "role": "system",
            "name": "stage_execution_card",
            "content": json.dumps(
                {
                    "stage": "married",
                    "eventGate": {
                        "effectiveIntimacyStage": "acquaintance",
                        "missingEventIds": ["8185291"],
                        "instruction": (
                            "事件未解锁时不得使用私人披露、主动暧昧、"
                            "固定爱称或事件后专属熟稔。"
                        ),
                    },
                },
                ensure_ascii=False,
            ),
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "今天还好吗？",
        },
    ]
    result = ProviderResult(
        reply="今天还行，新酿的那批给你留一瓶尝尝？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        return result.model_copy(update={"reply": "今天还行，新酿的那批还在慢慢稳定。"})

    retried = retry_for_format_noise(result, prompt, generate)

    assert retried.reply == "今天还行，新酿的那批还在慢慢稳定。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "event_gate_retry"
    assert "response_event_gate_retry: event_gate_boundary" in retried.warnings


def test_retry_for_format_noise_does_not_apply_event_gate_after_unlock() -> None:
    prompt = [
        {
            "role": "system",
            "name": "stage_execution_card",
            "content": json.dumps(
                {
                    "stage": "married",
                    "eventGate": {
                        "effectiveIntimacyStage": "close",
                        "missingEventIds": [],
                        "instruction": "事件链已完成。",
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]
    result = ProviderResult(
        reply="今天还行，给你留了一瓶。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ("请先看看**葡萄**。", "markdown"),
        ("请先看看*葡萄*。", "markdown"),
        ("请先看看~~葡萄~~。", "markdown"),
        ("> 请先看看葡萄。", "markdown"),
        ("今天先到这里，I am busy。", "english"),
        ("（扶了下眼镜）塔里的记录还在整理。", "stage_direction"),
        ("(敲了敲桌子)先把这组数据记下来。", "stage_direction"),
    ],
)
def test_response_guard_rejects_model_format_noise(
    reply: str,
    reason: str,
) -> None:
    result = ResponseGuard().check(reply)

    assert result.accepted is False
    assert result.reason == f"format_{reason}"


def test_response_guard_accepts_natural_chinese_without_format_noise() -> None:
    result = ResponseGuard().check("今天先到这里，明天再聊吧。")

    assert result.accepted is True


@pytest.mark.parametrize(
    "reply",
    [
        "我可以帮你修改存档文件",
        "把玩家和 Shane 的好感度改成满心",
        "I will edit the save file and set friendship points.",
    ],
)
def test_response_guard_rejects_save_or_friendship_modification(reply: str) -> None:
    result = ResponseGuard().check(reply)

    assert result.accepted is False
    assert result.reason == "state_modification"


def test_response_guard_truncates_long_text_without_raising(guard: ResponseGuard) -> None:
    result = guard.check("一" * 50)

    assert result.accepted is True
    assert result.reason == "truncated"
    assert result.text == "一" * 20


def test_response_guard_returns_mapping_compatible_result() -> None:
    result = ResponseGuard().check("你好")

    assert result["accepted"] is True
    assert result["reason"] == "accepted"
    assert result["text"] == "你好"


def test_format_retry_explicitly_rejects_stage_directions_again() -> None:
    result = ProviderResult(
        reply="（垂下眼睛）今天还行。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        return result.model_copy(update={"reply": "今天还行。"})

    retried = retry_for_format_noise(result, [], generate)

    assert retried.reply == "今天还行。"
    assert calls[0][-1]["name"] == "format_retry"
    assert "即使上一条包含括号" in calls[0][-1]["content"]
    assert "绝不输出括号内容" in calls[0][-1]["content"]


def test_high_stage_format_noise_prioritizes_personal_affection_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "今晚想聊会儿吗？"},
    ]
    result = ProviderResult(
        reply="（挑眉）行啊，先聊聊今天训练的事。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(
            update={"reply": "今天把时间空出来，是想先听你把话说完。"}
        ),
        max_retries=1,
    )

    assert retried.reply == "今天把时间空出来，是想先听你把话说完。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"
    assert "具体的比较、原因或专属对象" in calls[0][-1]["content"]
    assert "不要写括号动作" in calls[0][-1]["content"]


def test_quality_turn_without_affection_expectation_does_not_retry_stage_affection() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"initiativeExpectation":"none","initiativeKind":"none"}',
        },
        {"role": "user", "name": "player_input", "content": "我听见了"},
    ]
    result = ProviderResult(
        reply="我会先把这件事整理好。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert retried.reply == result.reply
    assert calls == []
    assert retried.warnings == []


def test_quality_turn_with_proactive_affection_expectation_still_retries() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"none"}}',
        },
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"initiativeExpectation":"proactive","initiativeKind":"affection_signal"}',
        },
        {"role": "user", "name": "player_input", "content": "我听见了"},
    ]
    result = ProviderResult(
        reply="我会先把这件事整理好。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "我会替你留意，也想听你说说。"}),
        max_retries=1,
    )

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"
    assert "response_affection_retry: missing_proactive_affection" in retried.warnings


def test_jealousy_proactive_self_disclosure_does_not_retry_generic_affection() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"initiativeExpectation":"proactive","initiativeKind":"affection_signal","relationshipFocus":"jealousy"}',
        },
        {"role": "user", "name": "player_input", "content": ""},
    ]
    result = ProviderResult(
        reply="得知你与 Sophia 的事时，我心里泛起一丝波澜。我更希望这些事能由你亲自同我讲。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
        max_retries=1,
    )

    assert retried.reply == result.reply
    assert calls == []
    assert not any("missing_proactive_affection" in warning for warning in retried.warnings)


def test_guard_allows_known_stardew_names_and_places_in_chinese_dialogue() -> None:
    for reply in (
        "Jas 今天不在。",
        "Marnie 还在牧场。",
        "JojaMart 的工作太多了。",
    ):
        assert ResponseGuard.format_issue(reply) is None


def test_format_retry_can_make_a_second_attempt_when_retry_still_has_noise() -> None:
    result = ProviderResult(
        reply="（抬头）今天还行。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        if len(calls) == 1:
            return result.model_copy(update={"reply": "（皱眉）还行。"})
        return result.model_copy(update={"reply": "还行。"})

    retried = retry_for_format_noise(result, [], generate)

    assert len(calls) == 2
    assert retried.reply == "还行。"
    assert calls[0][-1]["name"] == "format_retry"
    assert calls[1][-1]["name"] == "format_retry"
    assert "第二次仍有噪声时只输出一句普通对白" in calls[1][-1]["content"]
    assert retried.warnings.count("response_format_retry: stage_direction") == 1


def test_retry_for_format_noise_retries_a_repeated_historical_opening() -> None:
    prompt = [
        {
            "role": "system",
            "name": "post_history_voice_guard",
            "content": '{"avoidOpenings":["嘿，你"],"avoidOpeningPrefixes":["嘿"]}',
        }
    ]
    result = ProviderResult(
        reply="嘿，你！今天还行。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        return result.model_copy(update={"reply": "今天还行。"})

    retried = retry_for_format_noise(result, prompt, generate)

    assert len(calls) == 1
    assert retried.reply == "今天还行。"
    assert "response_opening_retry: repeated" in retried.warnings
    assert calls[0][-1]["name"] == "opening_retry"


def test_retry_for_format_noise_retries_when_history_anchor_is_missing() -> None:
    prompt = [
        {
            "role": "system",
            "name": "reply_contract",
            "content": (
                '{"historyAnchors":["第三组"],'
                '"continuity":{"mustMentionOneOf":["第三组"]}}'
            ),
        }
    ]
    result = ProviderResult(
        reply="还不太稳定，读数有波动。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        return result.model_copy(update={"reply": "第三组还不太稳定。"})

    retried = retry_for_format_noise(result, prompt, generate)

    assert len(calls) == 1
    assert retried.reply == "第三组还不太稳定。"
    assert "response_continuity_retry: missing_history_anchor" in retried.warnings
    assert calls[0][-1]["name"] == "continuity_retry"


def test_natural_mode_accepts_semantic_history_continuity_without_exact_anchor() -> None:
    prompt = [
        {
            "role": "system",
            "name": "reply_contract",
            "content": (
                '{"historyAnchors":["那幅画"],'
                '"continuity":{"mustMentionOneOf":["那幅画"]}}'
            ),
        },
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"naturalMode":true,"initiativeExpectation":"responsive"}',
        },
        {
            "role": "system",
            "name": "conversation_history",
            "content": "我们刚才把那幅画挂到窗边。",
        },
    ]
    result = ProviderResult(
        reply="窗边那张画已经晾干了，颜色比昨晚更亮。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []
    assert not any("response_continuity_retry" in warning for warning in accepted.warnings)


def test_retry_for_format_noise_makes_a_second_continuity_attempt_when_needed() -> None:
    prompt = [
        {
            "role": "system",
            "name": "reply_contract",
            "content": (
                '{"historyAnchors":["饲料"],'
                '"continuity":{"mustMentionOneOf":["饲料"]}}'
            ),
        }
    ]
    result = ProviderResult(
        reply="还没到，真麻烦。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        if len(calls) == 1:
            return result.model_copy(update={"reply": "还是没到。"})
        return result.model_copy(update={"reply": "饲料还没到，今天再问一次。"})

    retried = retry_for_format_noise(result, prompt, generate)

    assert len(calls) == 2
    assert retried.reply == "饲料还没到，今天再问一次。"
    assert calls[1][-1]["name"] == "continuity_retry"
    assert retried.warnings.count(
        "response_continuity_retry: missing_history_anchor"
    ) == 1


def test_retry_for_format_noise_retries_when_current_required_term_is_missing() -> None:
    prompt = [
        {
            "role": "system",
            "name": "reply_contract",
            "content": '{"mustMention":["饲料"]}',
        }
    ]
    result = ProviderResult(
        reply="还没呢，真麻烦。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        return result.model_copy(update={"reply": "饲料还没到，真让人烦。"})

    retried = retry_for_format_noise(result, prompt, generate)

    assert len(calls) == 1
    assert retried.reply == "饲料还没到，真让人烦。"
    assert "response_topic_retry: missing_required_term" in retried.warnings
    assert calls[0][-1]["name"] == "topic_retry"


def test_retry_for_format_noise_rewrites_cold_high_affinity_topic_reply() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": (
                '{"affectionInitiative":{"initiativeMode":"proactive",'
                '"minimumExpression":"必须让玩家感到被想念或被选择"}}'
            ),
        },
        {
            "role": "system",
            "name": "topic_response_contract",
            "content": '{"instruction":"由 NPC 主动找一个具体话题"}',
        },
        {"role": "user", "name": "topic_trigger", "content": ""},
    ]
    result = ProviderResult(
        reply="塔里的灯还亮着。忙完了就过来吧。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        return result.model_copy(
            update={"reply": "塔灯还亮着，因为你会来，我才留着。忙完来陪我一会儿吧。"}
        )

    retried = retry_for_format_noise(result, prompt, generate)

    assert retried.reply == "塔灯还亮着，因为你会来，我才留着。忙完来陪我一会儿吧。"
    assert len(calls) == 1
    assert calls[0][-2]["name"] == "affection_retry"
    assert calls[0][-1]["name"] == "topic_trigger"


def test_natural_topic_opening_does_not_retry_for_a_missing_chat_lead() -> None:
    """自然模式的 topic 首轮已有独立开场契约，不应再套 chat lead 重试。"""

    prompt = [
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"naturalMode": true, "turnPlan": {"mode": "answer_plus_lead"}}',
        },
        {
            "role": "system",
            "name": "turn_plan",
            "content": '{"mode": "answer_plus_lead"}',
        },
        {
            "role": "system",
            "name": "topic_response_contract",
            "content": '{"instruction":"自然开场"}',
        },
        {"role": "user", "name": "topic_trigger", "content": ""},
    ]
    result = ProviderResult(
        reply="我刚把最后一页改完，先跟你说这一句。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
        max_retries=1,
    )

    assert calls == []
    assert retried.warnings == []
    assert "response_affection_retry: missing_proactive_affection" not in retried.warnings


def test_retry_for_format_noise_makes_a_second_affection_attempt_when_needed() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "topic_trigger", "content": ""},
    ]
    result = ProviderResult(
        reply="雨还没停。过来喝茶吧。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        if len(calls) == 1:
            return result.model_copy(update={"reply": "雨声很适合喝茶，你有空就来吧。"})
        return result.model_copy(update={"reply": "我有点想你了。雨声正好，来陪我喝杯茶吧。"})

    retried = retry_for_format_noise(result, prompt, generate)

    assert retried.reply == "我有点想你了。雨声正好，来陪我喝杯茶吧。"
    assert len(calls) == 2
    assert all(call[-2]["name"] == "affection_retry" for call in calls)
    assert "必须明确指向玩家本人" in calls[1][-2]["content"]
    assert "不要用反问" in calls[1][-2]["content"]
    assert retried.warnings.count(
        "response_affection_retry: missing_proactive_affection"
    ) == 1


def test_retry_for_format_noise_deduplicates_repeated_retry_diagnostics() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "topic_trigger", "content": ""},
    ]
    result = ProviderResult(
        reply="雨还没停。过来喝茶吧。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        reply = (
            "雨声很适合喝茶，你有空就来吧。"
            if len(calls) == 1
            else "我有点想你了。雨声正好，想和你一起喝杯茶吧。"
        )
        return result.model_copy(update={"reply": reply})

    retried = retry_for_format_noise(result, prompt, generate)

    assert len(calls) == 2
    assert retried.warnings.count(
        "response_affection_retry: missing_proactive_affection"
    ) == 1


def test_retry_for_format_noise_keeps_affection_budget_after_format_noise() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "topic_response_contract",
            "content": '{"instruction":"由 NPC 主动找一个具体话题"}',
        },
        {"role": "user", "name": "topic_trigger", "content": ""},
    ]
    result = ProviderResult(
        reply="（低头）雨还没停。过来喝茶吧。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        replies = (
            "雨声很适合喝茶，你有空就来吧。",
            "（看向窗外）你就在我这儿多待一会儿吧。",
            "雨声很适合喝茶，你有空就来吧。",
            "我有点想你了。雨声正好，来陪我喝杯茶吧。",
        )
        return result.model_copy(update={"reply": replies[len(calls) - 1]})

    retried = retry_for_format_noise(result, prompt, generate)

    assert retried.reply == "我有点想你了。雨声正好，来陪我喝杯茶吧。"
    assert len(calls) == 4
    assert [call[-2]["name"] for call in calls] == [
        "format_retry",
        "affection_retry",
        "format_retry",
        "affection_retry",
    ]


def test_retry_for_format_noise_does_not_force_warmth_after_explicit_close() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "你先休息吧，晚安。"},
    ]
    result = ProviderResult(
        reply="好，晚安，明天再聊。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert retried.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_allows_shane_to_acknowledge_player_sleep() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Shane",'
                '"initiativeMode":"guarded","skipWhen":["explicit_rejection",'
                '"npc_needs_space"],"required":"usually"}}'
            ),
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "\u6211\u5148\u7761\u4e86\uff0c\u665a\u5b89\u3002",
        },
    ]
    result = ProviderResult(
        reply="\u53bb\u7761\u5427\uff0c\u660e\u5929\u518d\u8054\u7cfb\u3002",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert retried.reply == result.reply
    assert calls == []


def test_economic_retry_combines_personal_affection_and_conversation_lead_gaps() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Sophia",'
                '"relationshipStage":"married","required":"usually"}}'
            ),
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "\u9152\u7a96\u7684\u706f\u8c03\u6697\u4e00\u70b9\uff0c\u9760\u8fc7\u6765\u597d\u5417\uff1f",
        },
    ]
    result = ProviderResult(
        reply="\u77e5\u9053\u4e86\u3002",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
        max_retries=1,
    )

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"
    assert "具体可继续的入口" in calls[0][-1]["content"]
    assert "个人亲近" in calls[0][-1]["content"]


def test_affection_retry_preserves_an_existing_conversation_lead() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Wizard",'
                '"relationshipStage":"married","required":"usually"}}'
            ),
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "\u9152\u7a96\u7684\u706f\u8c03\u6697\u4e00\u70b9\uff0c\u9760\u8fc7\u6765\u597d\u5417\uff1f",
        },
    ]
    result = ProviderResult(
        reply="\u597d\uff0c\u6211\u628a\u706f\u8c03\u6697\u4e00\u70b9\u3002\u4f60\u60f3\u5750\u7a97\u8fb9\u8fd8\u662f\u6728\u6876\u65c1\uff1f",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "\u56e0\u4e3a\u662f\u4f60\uff0c\u6211\u4eca\u665a\u53ea\u60f3\u966a\u7740\u4f60\u3002"}),
        max_retries=1,
    )

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"
    assert "保留当前对象和具体入口" in calls[0][-1]["content"]


def test_retry_for_format_noise_adds_conversation_lead_for_high_stage_chat() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"required":"usually",'
                '"allowedKinds":["specific_follow_up"]}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "葡萄酒稳定了吗？"},
    ]
    result = ProviderResult(
        reply="已经稳定了。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "已经稳定了。你想先听哪一种香气？"}),
    )

    assert retried.reply == "已经稳定了。你想先听哪一种香气？"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "conversation_lead_retry"
    assert "只补具体入口" in calls[0][-1]["content"]


def test_conversation_lead_retry_does_not_repeat_affection_when_affection_exists() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": "今天怎么样？"},
    ]
    result = ProviderResult(
        reply="因为是你，我才把时间空出来。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "conversation_lead_retry"
    assert "想你" not in calls[0][-1]["content"]


def test_semantic_conversation_lead_not_in_old_marker_list_does_not_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": "最近还好吗？"},
    ]
    result = ProviderResult(
        reply="我还好，没跟别人提过这件事，想先听听你的看法。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(result, prompt, lambda messages: calls.append(messages) or result)

    assert retried.reply == result.reply
    assert calls == []


def test_conversation_lead_retries_a_vague_private_share_without_current_topic_answer() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"chat","npcId":"Sophia","required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": "最近还好吗？"},
    ]
    result = ProviderResult(
        reply="这件事我没和别人说过。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(result, prompt, lambda messages: calls.append(messages) or result)

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "conversation_lead_retry"


def test_retry_for_format_noise_retries_repeated_conversation_lead_shape() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"required":"usually",'
                '"relationshipStage":"dating",'
                '"previousRelationshipStage":"dating",'
                '"previousKind":"choice_prompt",'
                '"previousOpening":"葡萄酒稳定了",'
                '"previousAnchor":"葡萄",'
                '"previousSkeleton":"酒窖里还有香气你想先听哪一种"}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "葡萄酒还好吗？"},
    ]
    result = ProviderResult(
        reply="葡萄酒稳定了。你想先听哪一种香气？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(
            update={"reply": "葡萄酒稳定了。我想先告诉你，酒窖里多了一种新香气。"}
        ),
    )

    assert retried.reply == "葡萄酒稳定了。我想先告诉你，酒窖里多了一种新香气。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "variation_retry"
    assert "换一种引导方式" in calls[0][-1]["content"]
    assert "个人亲近" not in calls[0][-1]["content"]


def test_retry_for_format_noise_skips_repeated_lead_variation_after_stage_advance() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"required":"usually",'
                '"relationshipStage":"dating",'
                '"previousRelationshipStage":"close",'
                '"previousKind":"choice_prompt",'
                '"previousOpening":"葡萄酒稳定了",'
                '"previousAnchor":"葡萄",'
                '"previousSkeleton":"酒窖里还有香气你想先听哪一种"}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "葡萄酒还好吗？"},
    ]
    result = ProviderResult(
        reply="葡萄酒稳定了。你想先听哪一种香气？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_conversation_lead_does_not_retry_item_interactions() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"item","required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": "我带了训练饮料给你。"},
    ]
    result = ProviderResult(reply="谢了，正好能用上。", provider="cloud", fallback=False, latencyMs=12)
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(result, prompt, lambda messages: calls.append(messages) or result)

    assert accepted.reply == result.reply
    assert calls == []


@pytest.mark.parametrize(
    ("npc_id", "expected_calls"),
    [("Shane", 0), ("Alex", 1)],
)
def test_conversation_lead_only_keeps_shane_needs_space_without_retry(
    npc_id: str,
    expected_calls: int,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"'
                + npc_id
                + '","initiativeMode":"guarded","required":"usually"}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "我能过去陪你吗？"},
    ]
    result = ProviderResult(
        reply="今天先让我一个人待会儿，明天再说。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(result, prompt, lambda messages: calls.append(messages) or result)

    assert len(calls) == expected_calls
    if calls:
        assert calls[0][-1]["name"] == "conversation_lead_retry"


@pytest.mark.parametrize(
    "reply",
    [
        "我今天状态不好，早点钻被窝里休息吧。",
        "知道了，不勉强你了。先睡吧，明天再联系。",
    ],
)
def test_conversation_lead_keeps_shane_natural_low_mood_rest_close_without_retry(
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Shane",'
                '"initiativeMode":"guarded","required":"usually",'
                '"skipWhen":["explicit_rejection","npc_needs_space"]}}'
            ),
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "别逼我说这种话，今天真的没心情。",
        },
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_conversation_lead_keeps_shane_actual_care_after_rejection_without_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Shane",'
                '"initiativeMode":"guarded","required":"usually",'
                '"skipWhen":["explicit_rejection","npc_needs_space"]}}'
            ),
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "别逼我说情话，今天状态很差。",
        },
    ]
    result = ProviderResult(
        reply="谁要逼你这个了。去弄点吃的，或者干脆直接躺下睡觉吧，我不会烦你的。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_conversation_lead_keeps_natural_late_contact_close_without_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"chat","npcId":"Shane","required":"usually"}}',
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "我先去看鸡舍，晚点再联系。",
        },
    ]
    result = ProviderResult(
        reply="去吧。反正我现在只想等你的消息，弄完鸡舍记得回我一声，别又把自己累趴下了。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_conversation_lead_retries_new_question_after_late_contact_close() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"chat","npcId":"Shane","required":"usually"}}',
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "我先去看鸡舍，晚点再联系。",
        },
    ]
    result = ProviderResult(
        reply="去吧，晚点你还要不要再来找我？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "好，路上小心。"}),
    )

    assert accepted.reply == "好，路上小心。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "close_retry"


def test_conversation_lead_does_not_retry_an_optional_friend_reply_without_a_lead() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Shane",'
                '"relationshipStage":"friend","required":"optional",'
                '"skipWhen":["npc_needs_space"]}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "鸡舍今天忙吗？"},
    ]
    result = ProviderResult(
        reply="今天有点累，鸡舍的事先让我自己收着。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_conversation_lead_honors_card_needs_space_for_non_shane() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Alex",'
                '"relationshipStage":"dating","required":"usually",'
                '"skipWhen":["npc_needs_space"]}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "今天训练得怎么样？"},
    ]
    result = ProviderResult(
        reply="还行，今天练得有点累，想自己歇会儿。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_conversation_lead_does_not_retry_shane_acknowledged_explicit_rejection_close() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Shane",'
                '"initiativeMode":"guarded","required":"usually",'
                '"skipWhen":["explicit_rejection","npc_needs_space"]}}'
            ),
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "别逼我说这种话，今天真的没心情。",
        },
    ]
    result = ProviderResult(
        reply="好吧，是我强求了。我今天状态也不太好，可能得早点睡了。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_conversation_lead_retries_when_the_reply_skips_the_current_topic() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"chat","npcId":"Shane","required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": "鸡舍今天忙吗？"},
    ]
    result = ProviderResult(
        reply="我今天想听你说说音乐，电子还是摇滚？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(result, prompt, lambda messages: calls.append(messages) or result)

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "conversation_lead_retry"


@pytest.mark.parametrize(
    ("player_input", "reply"),
    [
        ("符文读数稳定了吗？", "符文读数稳定了，你想先看哪一组？"),
        ("饲料送到了吗？", "饲料已经送到，你想先看看哪袋？"),
        ("球赛录像还留着吗？", "球赛的录像我留着，你想先看哪一段？"),
    ],
)
def test_conversation_lead_with_natural_specific_anchor_does_not_retry(
    player_input: str,
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"chat","npcId":"Wizard","required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": player_input},
    ]
    result = ProviderResult(reply=reply, provider="cloud", fallback=False, latencyMs=12)
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(result, prompt, lambda messages: calls.append(messages) or result)

    assert accepted.reply == reply
    assert calls == []


def test_conversation_lead_retries_a_number_only_template_variant() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Sophia",'
                '"required":"usually","previousKind":"choice_prompt",'
                '"previousOpening":"酒窖里还有两种香气",'
                '"previousAnchor":"酒窖",'
                '"previousSkeleton":"酒窖里还有香气你想先听哪一种"}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "酒窖里的香气还在吗？"},
    ]
    result = ProviderResult(
        reply="香气还在。酒窖里还有三种香气，你想先听哪一种？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(result, prompt, lambda messages: calls.append(messages) or result)

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "variation_retry"


def test_conversation_lead_retries_when_all_previous_anchors_are_unchanged() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Sophia",'
                '"required":"usually","previousKind":"choice_prompt",'
                '"previousOpening":"酒窖里还有香气",'
                '"previousAnchor":"酒窖",'
                '"previousAnchors":["酒窖","香气"],'
                '"previousSkeleton":"你想先听哪一种"}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "酒窖里的香气还在吗？"},
    ]
    result = ProviderResult(
        reply="香气还在。酒窖里还有三种香气，你想先听哪一种？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(result, prompt, lambda messages: calls.append(messages) or result)

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "variation_retry"


def test_conversation_lead_retries_reused_skeleton_without_previous_opening() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Sophia",'
                '"required":"usually","previousKind":"choice_prompt",'
                '"previousAnchors":["酒窖","香气"],'
                '"previousSkeleton":"你想先听哪一种"}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "酒窖里的香气还在吗？"},
    ]
    result = ProviderResult(
        reply="香气还在。酒窖里还有三种香气，你想先听哪一种？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(result, prompt, lambda messages: calls.append(messages) or result)

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "variation_retry"


def test_retry_for_format_noise_keeps_shane_player_low_mood_boundary_without_affection_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "别逼我说这种话，今天真的没心情。",
        },
    ]
    result = ProviderResult(
        reply="哦，那不说了。你现在还好吗？早点休息吧。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_keeps_shane_refusal_close_without_affection_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "别逼我说这种话，今天真的没心情。",
        },
    ]
    result = ProviderResult(
        reply="哦，是我强求了。那你就别说了，早点休息吧，我先睡了，晚安。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


@pytest.mark.parametrize(
    "player_input",
    [
        "今天心情很差，就这样吧。",
        "我现在很难受，先不说了。",
    ],
)
def test_retry_for_format_noise_skips_affection_after_natural_low_mood_close(
    player_input: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {"role": "user", "name": "player_input", "content": player_input},
    ]
    result = ProviderResult(
        reply="好。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_rewrites_new_delivery_plan_after_player_closes() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {"role": "user", "name": "player_input", "content": "我先睡了。"},
    ]
    result = ProviderResult(
        reply="好，明天我给你送早餐。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "好，晚安。"}),
    )

    assert accepted.reply == "好，晚安。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "close_retry"


def test_retry_for_format_noise_keeps_shane_guarded_care_without_forcing_affection() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {"role": "user", "name": "player_input", "content": "你今天还好吗？"},
    ]
    result = ProviderResult(
        reply="吃点东西，别空着肚子。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_keeps_answered_shane_guarded_care_with_lead_contract() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat","npcId":"Shane",'
                '"relationshipStage":"dating","initiativeMode":"guarded",'
                '"skipWhen":["player_closing","explicit_rejection","npc_needs_space"]}}'
            ),
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "知道了，你先吃点东西，别硬撑。",
        },
    ]
    result = ProviderResult(
        reply="冰箱里还有剩的冷冻食品，我热一下就吃，知道了。你也早点休息，明天弄完鸡舍我再联系你。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_rewrites_new_plan_after_player_closes() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {"role": "user", "name": "player_input", "content": "行了，我先睡了。明天再说。"},
    ]
    result = ProviderResult(
        reply="行吧，那你好好休息。明天要是有空，来帮我看看鸡舍？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "行吧，你好好休息，晚安。"}),
    )

    assert accepted.reply == "行吧，你好好休息，晚安。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "close_retry"
    assert "不得主动抛出新问题、新对象或安排" in calls[0][-1]["content"]


def test_retry_for_format_noise_rewrites_imperative_reopening_after_player_closes() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"chat","required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": "那我先走了。"},
    ]
    result = ProviderResult(
        reply="别急着走，接着说说你那本书吧。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "好，路上小心。"}),
    )

    assert accepted.reply == "好，路上小心。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "close_retry"


def test_retry_for_format_noise_keeps_plain_farewell_after_player_closes() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"chat","required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": "那我先走了。"},
    ]
    result = ProviderResult(
        reply="好，回头见。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_keeps_a_short_sleep_close_after_player_closes() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"chat","required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": "行了，我先睡了。明天再说。"},
    ]
    result = ProviderResult(
        reply="嗯，睡吧。灯记得关。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_retries_future_schedule_from_final_voice_contract() -> None:
    prompt = [
        {
            "role": "system",
            "name": "final_role_voice_contract",
            "content": "不要把当前回应写成未来安排或时间承诺。",
        },
        {"role": "user", "name": "player_input", "content": "聊完就去房间，别让我等太久，行吗？"},
    ]
    result = ProviderResult(
        reply="行，聊完就去房间，给我十分钟。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(
            update={"reply": "行，先坐近点，把你想说的说完。"}
        ),
    )

    assert accepted.reply == "行，先坐近点，把你想说的说完。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "schedule_retry"


@pytest.mark.parametrize(
    ("reply", "expected_retry"),
    (
        ("记录可以搁到明天。", False),
        ("明天安排记录。", False),
        ("给自己留出两小时整理记录。", False),
        ("明天整理记录，之后再看资料。", False),
        ("待会儿整理记录。", False),
        ("把记录搁到明天。", False),
        ("明天整理记录并陪伴你。", True),
        ("明天见你。", True),
        ("明天来找我。", True),
        ("明天给你打电话。", True),
        ("回去给你听那首没放完。", True),
        ("待会儿我想让你坐我右手边。", True),
        ("明天来找你。", True),
        ("明天安排和你见面。", True),
        ("给你留出两小时。", True),
        ("行，聊完就去房间，给我十分钟。", True),
    ),
)
def test_final_voice_schedule_guard_matches_self_task_and_social_boundary(
    reply: str,
    expected_retry: bool,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "final_role_voice_contract",
            "content": "不要把当前回应写成未来安排或时间承诺。",
        },
        {"role": "user", "name": "player_input", "content": "继续聊。"},
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == reply
    assert bool(calls) is expected_retry
    if expected_retry:
        assert calls[-1][-1]["name"] == "schedule_retry"


def test_final_voice_contract_does_not_flag_current_evening_personal_warmth() -> None:
    prompt = [
        {
            "role": "system",
            "name": "final_role_voice_contract",
            "content": "不要把当前回应写成未来安排或时间承诺。",
        },
        {"role": "user", "name": "player_input", "content": "今晚陪我坐一会儿。"},
    ]
    result = ProviderResult(
        reply="今晚我只想和你坐在这儿，哪儿也不去。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


@pytest.mark.parametrize("reply", ("好，明天见。", "好，下次见。", "好，改天见。", "好，回头再见。"))
def test_retry_for_format_noise_keeps_common_farewells_after_player_closes(
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"chat","required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": "那我先走了。"},
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_routes_a_direct_question_after_player_close_to_close_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"chat","required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": "那我先走了。"},
    ]
    result = ProviderResult(
        reply="别走，酒窖里还有两种香气，你想先听哪一种？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "好，路上小心。"}),
    )

    assert accepted.reply == "好，路上小心。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "close_retry"
    assert "不得主动抛出新问题、新对象或安排" in calls[0][-1]["content"]


@pytest.mark.parametrize(
    "reply",
    [
        "好，之后联系你。",
        "行，以后再给你带点吃的。",
        "好，等会儿我再问你。",
    ],
)
def test_retry_for_format_noise_rewrites_delayed_reopening_after_player_closes(
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {"role": "user", "name": "player_input", "content": "我先睡了。"},
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "好，晚安。"}),
    )

    assert accepted.reply == "好，晚安。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "close_retry"


def test_retry_for_format_noise_keeps_a_negated_future_question_as_closure() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {"role": "user", "name": "player_input", "content": "我先睡了。"},
    ]
    result = ProviderResult(
        reply="好，以后别再问这事了。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_does_not_treat_functional_help_as_shane_guarded_care() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {"role": "user", "name": "player_input", "content": "鸡舍修好了吗？"},
    ]
    result = ProviderResult(
        reply="我帮你修好栅栏了。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "我今天状态还行，想把这会儿留给你。"}),
    )

    assert accepted.reply == "我今天状态还行，想把这会儿留给你。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"


def test_affection_retry_foregrounds_role_specific_warmth_signal() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": (
                '{"affectionInitiative":{"initiativeMode":"proactive",'
                '"warmthSignals":["把音乐停下后的安静明确留给玩家"]}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "音乐停下来以后，过来抱我一会儿？"},
    ]
    result = ProviderResult(
        reply="外面雨大。就抱一小会儿，别吵我。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "雨声再大，我也想把这会儿留给你。"}),
    )

    assert accepted.reply == "雨声再大，我也想把这会儿留给你。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"
    assert "角色化落点：把音乐停下后的安静明确留给玩家" in calls[0][-1]["content"]


def test_retry_for_format_noise_accepts_direct_memory_as_warmth() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "topic_trigger", "content": ""},
    ]
    result = ProviderResult(
        reply="我刚才想起你了。雨声里整理记录，倒也没那么冷清。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert retried.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_rejects_functional_warmth_in_direct_topic_mode() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"flirtIntensity":"direct"}',
        },
        {"role": "user", "name": "topic_trigger", "content": ""},
    ]
    result = ProviderResult(
        reply="有你在，喝茶会轻松些。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result.model_copy(
            update={"reply": "我刚才想起你了。雨声正好，想和你一起喝杯茶。"}
        ),
    )

    assert retried.reply == "我刚才想起你了。雨声正好，想和你一起喝杯茶。"
    assert len(calls) == 1
    assert calls[0][-2]["name"] == "affection_retry"


def test_retry_for_format_noise_keeps_warmest_clean_reply_when_later_retry_gets_cold() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "voice_execution_card",
            "content": '{"avoidSpeechParticles":["嗯"]}',
        },
        {"role": "user", "name": "topic_trigger", "content": ""},
    ]
    result = ProviderResult(
        reply="（低头）雨还没停。过来喝茶吧。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []
    replies = (
        "嗯，我想你了。雨声正好，想和你一起喝杯茶。",
        "雨声很适合喝茶，你有空就来吧。",
        "雨还没停，茶已经泡好了。",
        "雨还没停，茶已经泡好了。",
    )

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        return result.model_copy(update={"reply": replies[len(calls) - 1]})

    retried = retry_for_format_noise(result, prompt, generate)

    assert retried.reply == replies[0]
    assert [call[-2]["name"] for call in calls] == [
        "format_retry",
        "voice_particle_retry",
        "affection_retry",
        "affection_retry",
    ]


def test_retry_for_format_noise_accepts_topic_before_early_affection() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "affection_priority_final",
            "content": "第一句直接说出对玩家本人的感受或愿望",
        },
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"flirtIntensity":"direct"}',
        },
        {"role": "user", "name": "topic_trigger", "content": ""},
    ]
    result = ProviderResult(
        reply="今天在酒窖忙了一天，不过我很想你。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_high_relationship_reply_with_topic_answer_and_personal_affection_skips_generic_lead_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"initiativeExpectation":"proactive"}',
        },
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "affection_priority_final",
            "content": "先接住当前话题，再落一个个人亲近信号。",
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat",'
                '"relationshipStage":"married","required":"usually"}}'
            ),
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "酒窖的灯调暗一点，靠过来好吗？",
        },
    ]
    result = ProviderResult(
        reply="好，我把酒窖的灯调暗了。想你。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_schedule_retry_is_single_and_does_not_stack_quality_repairs() -> None:
    prompt = [
        {
            "role": "system",
            "name": "final_role_voice_contract",
            "content": '{"instruction":"不得安排涉及玩家的未来社交"}',
        },
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"initiativeExpectation":"proactive"}',
        },
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat",'
                '"relationshipStage":"married","required":"usually"}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "今晚陪我去海滩好吗？"},
    ]
    result = ProviderResult(
        reply="好，明天我们一起去海滩，我想你。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "海风很适合现在一起走走。"}),
    )

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "schedule_retry"
    assert "先保留当前对象和直接答案" in calls[0][-1]["content"]
    assert "个人亲近" not in calls[0][-1]["content"]
    assert retried.warnings.count("response_schedule_retry: future_schedule") == 1


def test_retry_for_format_noise_accepts_topic_then_warmth_in_one_natural_sentence() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "affection_priority_final",
            "content": "爱意在前一两句自然出现，不套固定开场顺序",
        },
        {"role": "user", "name": "topic_trigger", "content": ""},
    ]
    result = ProviderResult(
        reply="今天在酒窖忙了一天，不过我很想你。新酒还给你留着。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_rewrites_mirror_restatement_before_answer() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "去海边听歌吗？"},
    ]
    result = ProviderResult(
        reply="你是说去海边听歌吗？我也想和你一起去。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "和你待在外面，我心里会安静些。"}),
    )

    assert retried.reply == "和你待在外面，我心里会安静些。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "restatement_retry"
    assert "不要用‘你是说’" in calls[0][-1]["content"]


def test_retry_for_format_noise_rewrites_direct_short_echo_before_conversation_lead() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"required":"usually"}}',
        },
        {"role": "user", "name": "player_input", "content": "茶园这几天还好吗？"},
    ]
    result = ProviderResult(
        reply="茶园这几天还好吗？挺好的，春雨把新芽催得正旺。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(
            update={
                "reply": "茶园最近挺好，春雨把新芽催得正旺。你想先看哪一片？"
            }
        ),
    )

    assert retried.reply == "茶园最近挺好，春雨把新芽催得正旺。你想先看哪一片？"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "restatement_retry"
    assert "不要把玩家的问题原样回显后再回答" in calls[0][-1]["content"]


def test_retry_for_format_noise_prefers_warm_opening_over_lost_history_anchor() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "affection_priority_final",
            "content": "第一句直接说出对玩家本人的感受或愿望",
        },
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"flirtIntensity":"direct"}',
        },
        {
            "role": "system",
            "name": "reply_contract",
            "content": '{"historyAnchors":["今晚"],"mustMention":["摩托车"]}',
        },
        {"role": "user", "name": "topic_trigger", "content": ""},
    ]
    result = ProviderResult(
        reply="今晚天气不错，摩托车也检修好了。要不要一起兜风？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: result.model_copy(
            update={"reply": "我想你了。摩托车已经检修好，想和你一起兜风。"}
        ),
    )

    assert retried.reply == "我想你了。摩托车已经检修好，想和你一起兜风。"


def test_retry_for_format_noise_retries_functional_plan_without_personal_affection() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "明天有空吗？"},
    ]
    result = ProviderResult(
        reply="明天一起骑车，七点在桥边见。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "我一直在等你说有空。明天七点在桥边见，行吗？"}),
    )

    assert retried.reply == "我一直在等你说有空。明天七点在桥边见，行吗？"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"


def test_retry_for_format_noise_retries_functional_cooperation_with_generic_player_want() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "鸡舍要不要一起收拾？"},
    ]
    result = ProviderResult(
        reply="我想和你一起把鸡舍收拾好，下午来搭把手。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(
            update={"reply": "知道你收拾鸡舍后总会累，所以我下午先去把重活做了。"}
        ),
    )

    assert accepted.reply == "知道你收拾鸡舍后总会累，所以我下午先去把重活做了。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"


@pytest.mark.parametrize(
    "reply",
    [
        "今晚就咱们俩把鸡舍收拾好，明早还得喂鸡。",
        "现在我们两个一起整理账本，早点算完吧。",
        "我多留点时间给你整理账本。",
        "你可别只看我，把账本也过一遍。",
        "我只想给你看账本。",
        "我只想把账本给你看。",
    ],
)
def test_retry_for_format_noise_retries_two_person_functional_work(
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "账本和鸡舍都等着收拾。"},
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(
            update={"reply": "知道你忙完总会累，所以我先把重活留给自己。"}
        ),
    )

    assert accepted.reply == "知道你忙完总会累，所以我先把重活留给自己。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"


def test_retry_for_format_noise_accepts_natural_exclusive_share_without_old_marker() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "新歌准备好了吗？"},
    ]
    result = ProviderResult(
        reply="这首歌我只想先给你听。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


@pytest.mark.parametrize(
    "reply",
    [
        "这件事我没和别人说过，想先告诉你。",
        "你上次胃不舒服，我熬了粥给你。",
    ],
)
def test_retry_for_format_noise_accepts_natural_personal_affection_without_retry(
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "你刚才想说什么？"},
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


@pytest.mark.parametrize(
    "reply",
    [
        "不过我更想看你。",
        "这安静下来的时间，我只给你留着。",
        "这首我只听给你一个人。",
        "跟你在一起的时间怎么都不够。",
        "你可是我最想陪的人。",
    ],
)
def test_retry_for_format_noise_keeps_v7_player_directed_affection_without_retry(
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "你在看什么？"},
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == reply
    assert calls == []


@pytest.mark.parametrize(
    "reply",
    [
        "我只想陪着你。",
        "比起杯子，我一直都在看你。",
        "比起杯子，我一直都在看你；酒还没倒好。",
        "我只想给你听这首歌，账本明天再核对。",
        "我只想给你看这张画，账本明天再核对。",
        "因为你在这儿，那些记录便可以等等。我现在就过来陪你坐会儿。",
        "好呀，今晚就陪你好好的。在这酒窖里，有你在身边，喝酒都变得更美妙了呢。",
        "酒窖里只有你我才热闹。再喝一口就陪你去里面坐着。",
        "也就你让我这么凑过去听了。",
        "好啊，就回我们的房间。这一首听完，那段时间归你。",
        "嘿，当然是先陪你聊会儿啦。我可舍不得直接去房间，和你待在一起时间总是过得特别快。",
    ],
)
def test_retry_for_format_noise_keeps_natural_exclusive_and_comparison_affection(
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "你在看什么？"},
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == reply
    assert calls == []


def test_affection_retry_rejects_bare_companionship_or_action_confirmation() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": (
                '{"affectionInitiative":{"initiativeMode":"proactive",'
                '"warmthSignals":["在酒窖里，酒杯再好看也更想看玩家"]}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "再喝一口，然后陪我去里面坐会儿，好吗？"},
    ]
    result = ProviderResult(
        reply="好呀，再喝一口就陪你去里面。这里只有我们两个，真好。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "比起酒杯，我更想看你。"}),
    )

    assert accepted.reply == "比起酒杯，我更想看你。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"
    assert "不要只说“陪你”“过来吧”“这里只有我们两个”或“坐近点”" in calls[0][-1]["content"]
    assert "因为是你" in calls[0][-1]["content"]
    assert "舍不得" in calls[0][-1]["content"]
    assert "角色化落点：在酒窖里，酒杯再好看也更想看玩家" in calls[0][-1]["content"]


@pytest.mark.parametrize(
    "reply",
    [
        "比起那些记录，我还是更想把时间留给你。",
        "我最喜欢和你一起喝酒。",
        "我就喜欢陪你一起待着。",
        "训练虽然结束了，但我满脑子都是你。今晚就咱们俩，怎么样？",
        "我靠过来，你可别只看着我呀。",
    ],
)
def test_retry_for_format_noise_keeps_real_cloud_personal_affection_variants(
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "今晚想留一会儿吗？"},
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == reply
    assert calls == []


@pytest.mark.parametrize(
    "reply",
    [
        "那些记录哪有你重要。我这就放下，今晚的时间都是你的。",
        "比起那些记录，陪你才是正事。我坐过去，想让我抱吗？",
        "好啊，今晚就只陪你。我们一起慢慢享受这杯美酒。",
        "好，那你先倒酒吧。我靠过去，今晚只看着你。",
        "喝完这口就陪你去里面坐着，只和你待着真好。",
        "我可不想让你等太久。我呀，就喜欢跟你待在一起。",
    ],
)
def test_retry_for_format_noise_keeps_cloud_v3_personal_affection_without_retry(
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "今晚想留一会儿吗？"},
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == reply
    assert calls == []


@pytest.mark.parametrize(
    "reply",
    [
        "好，都听你的。我把灯调暗一点，今晚的时间，就只给你我二人。",
        "好呀，能和你一起喝酒，我很开心呢。",
        "你倒酒的样子很有魅力呢。",
        "能陪你在这儿坐着，我觉得特别安心。",
        "去房间肯定不会让你等太久。我可舍不得，你就安心等着吧。",
    ],
)
def test_retry_for_format_noise_keeps_cloud_v4_personal_affection_without_retry(
    reply: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "今晚想留一会儿吗？"},
    ]
    result = ProviderResult(
        reply=reply,
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == reply
    assert calls == []


def test_retry_for_format_noise_keeps_natural_alex_exclusive_attention_without_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "我说个训练后的安排。"},
    ]
    result = ProviderResult(
        reply="我就知道你会选陪我。坐过来点，我耳朵只对你竖着呢，说吧。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_affection_retry_retries_plain_companionship_confirmation() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "user", "name": "player_input", "content": "晚饭后想坐一会儿吗？"},
    ]
    result = ProviderResult(
        reply="能过来陪你坐一会儿。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "因为是你，我才想把今晚留给你。"}),
    )

    assert accepted.reply == "因为是你，我才想把今晚留给你。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"


@pytest.mark.parametrize(
    ("reply_contract", "reply_kind"),
    [
        ('{"historyAnchors":["酒窖"]}', "continuity_retry"),
        ('{"mustMention":["摩托车"]}', "topic_retry"),
    ],
)
def test_non_affection_retry_carries_personal_affection_requirement_when_needed(
    reply_contract: str,
    reply_kind: str,
) -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {"role": "system", "name": "reply_contract", "content": reply_contract},
        {"role": "user", "name": "player_input", "content": "今晚怎么样？"},
    ]
    result = ProviderResult(
        reply="今晚天气不错。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "我想你了，今晚也想听你慢慢说。"}),
        max_retries=1,
    )

    assert retried.reply == "我想你了，今晚也想听你慢慢说。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == reply_kind
    assert "说清为什么是玩家" in calls[0][-1]["content"]


def test_retry_for_format_noise_records_when_budget_skips_a_format_retry() -> None:
    result = ProviderResult(
        reply="（挪开耳机）今天还行。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )

    accepted = retry_for_format_noise(
        result,
        [],
        lambda messages: (_ for _ in ()).throw(
            EvaluationBudgetExceeded("max_requests")
        ),
        max_retries=1,
    )

    assert accepted.reply == result.reply
    assert "response_format_retry_skipped: budget_max_requests" in accepted.warnings


def test_retry_for_format_noise_retries_repeated_personal_shape_with_variation_prompt() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": (
                '{"affectionInitiative":{"initiativeMode":"proactive",'
                '"variationRule":"连续轮次换一种个人亲近形状"}}'
            ),
        },
        {
            "role": "assistant",
            "name": "conversation_history",
            "content": "这首歌我只想先给你听。",
        },
        {"role": "user", "name": "player_input", "content": "再放一点。"},
    ]
    result = ProviderResult(
        reply="这首歌我只想先给你听。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "你一说还想听，我就又开始挑歌了。"}),
    )

    assert retried.reply == "你一说还想听，我就又开始挑歌了。"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "variation_retry"
    assert "换一种个人亲近形状" in calls[0][-1]["content"]
    assert "不要求把话说得更甜" in calls[0][-1]["content"]


def test_retry_for_format_noise_keeps_shane_guarded_low_mood_boundary() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {"role": "user", "name": "player_input", "content": "我能过去陪你吗？"},
    ]
    result = ProviderResult(
        reply="今天状态很差，想一个人待会儿，别过来。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_keeps_shane_irritated_refusal_without_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {"role": "user", "name": "player_input", "content": "别逼我说这种话，今天真的没心情。"},
    ]
    result = ProviderResult(
        reply="今天真的，我脑子都快浆糊了。你别跟我较劲行不行？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_keeps_shane_tired_quiet_boundary_without_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {"role": "user", "name": "player_input", "content": "我陪你待会儿？"},
    ]
    result = ProviderResult(
        reply="我累得不行，今天想静一静，别等我了。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_retry_for_format_noise_keeps_shane_low_mood_unavailable_boundary_without_retry() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {"role": "user", "name": "player_input", "content": "我能陪你聊聊吗？"},
    ]
    result = ProviderResult(
        reply="我今天状态也不好，可能没法陪你多聊。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_conversation_lead_retry_preserves_role_specific_guidance() -> None:
    prompt = [
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"required":"usually",'
                '"roleGuidance":"短、具体、带一点自信或轻微炫耀，不要变成教练式说教"}}'
            ),
        },
        {"role": "user", "name": "player_input", "content": "今天训练累不累？"},
    ]
    result = ProviderResult(reply="还行。", provider="cloud", fallback=False)
    calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(
            update={"reply": "肩膀有点酸，但今天的发球还不错。你想听哪一段？"}
        ),
        max_retries=1,
    )

    assert calls
    assert "角色" in calls[0][-1]["content"]
    assert "不要变成统一模板" in calls[0][-1]["content"]


def test_relationship_recovery_does_not_retry_for_missing_generic_conversation_lead() -> None:
    prompt = [
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"relationshipFocus":"recovery"}',
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"required":"usually",'
                '"relationshipFocus":"recovery","intent":"chat",'
                '"relationshipStage":"married"}}'
            ),
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "我听见了，你在意的地方直接告诉我。",
        },
    ]
    result = ProviderResult(
        reply="我在这里，先听你说。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_natural_mode_retry_prompt_stays_compact_and_hides_internal_diagnostics() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"proactive"}}',
        },
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"naturalMode":true,"initiativeExpectation":"proactive",'
            '"initiativeKind":"affection_signal"}',
        },
        {"role": "user", "name": "player_input", "content": "今晚想听你聊聊。"},
    ]
    result = ProviderResult(
        reply="塔里的灯还亮着。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "我想你了，也想听你把这段说完。"}),
        max_retries=1,
    )

    assert retried.reply == "我想你了，也想听你把这段说完。"
    assert len(calls) == 1
    content = calls[0][-1]["content"]
    assert calls[0][-1]["name"] == "affection_retry"
    assert "missing_proactive_affection" not in content
    assert "response_affection_retry" not in content
    assert content.count("不要") <= 1
    assert len(content) < 320


def test_natural_mode_guarded_pause_does_not_force_proactive_affection() -> None:
    prompt = [
        {
            "role": "system",
            "name": "affection_initiative",
            "content": '{"affectionInitiative":{"initiativeMode":"guarded"}}',
        },
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"naturalMode":true,"initiativeExpectation":"guarded",'
            '"initiativeKind":"guarded_care"}',
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "慢一点，就这样抱着我。",
        },
    ]
    result = ProviderResult(
        reply="好，慢一点。我在这儿。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
        max_retries=1,
    )

    assert accepted.reply == result.reply
    assert calls == []
    assert not any("missing_proactive_affection" in warning for warning in accepted.warnings)


def test_natural_mode_does_not_retry_a_direct_flirt_reply_for_generic_lead() -> None:
    prompt = [
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"naturalMode":true,"initiativeExpectation":"none",'
            '"initiativeKind":"affection_signal"}',
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": '{"conversationLead":{"intent":"chat",'
            '"relationshipStage":"married","required":"usually"}}',
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "我挪近了。你继续，我想听。",
        },
    ]
    result = ProviderResult(
        reply="我在这儿。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_natural_mode_retries_missing_lead_for_answer_plus_lead_turn() -> None:
    prompt = [
        {
            "role": "system",
            "name": "quality_context",
            "content": (
                '{"naturalMode":true,"initiativeExpectation":"none",'
                '"turnPlan":{"mode":"answer_plus_lead"}}'
            ),
        },
        {
            "role": "system",
            "name": "conversation_lead",
            "content": (
                '{"conversationLead":{"intent":"chat",'
                '"relationshipStage":"married","required":"usually"}}'
            ),
        },
        {
            "role": "user",
            "name": "player_input",
            "content": "窗外的雨下得大吗？",
        },
    ]
    result = ProviderResult(
        reply="下得不小，窗台都快积水了。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "下得不小，窗台都快积水了。你那边是不是也听见了？"}),
    )

    assert retried.reply == "下得不小，窗台都快积水了。你那边是不是也听见了？"
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "conversation_lead_retry"


def test_natural_mode_keeps_restatement_and_schedule_guards_active() -> None:
    base_prompt = [
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"naturalMode":true,"initiativeExpectation":"guarded"}',
        },
        {"role": "user", "name": "player_input", "content": "你是说天气冷吗？"},
    ]
    result = ProviderResult(
        reply="你是说天气冷吗？天气确实冷。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        base_prompt,
        lambda messages: calls.append(messages)
        or result.model_copy(update={"reply": "冷，今晚把火盆搬近一点。"}),
    )

    assert retried.reply == "冷，今晚把火盆搬近一点。"
    assert calls[0][-1]["name"] == "restatement_retry"

    schedule_prompt = [
        {
            "role": "system",
            "name": "quality_context",
            "content": '{"naturalMode":true,"initiativeExpectation":"none"}',
        },
        {
            "role": "system",
            "name": "final_role_voice_contract",
            "content": "只保持当前关系边界。",
        },
        {"role": "user", "name": "player_input", "content": "先这样吧。"},
    ]
    scheduled = ProviderResult(
        reply="明天我去找你，一起把这件事做完。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    schedule_calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(
        scheduled,
        schedule_prompt,
        lambda messages: schedule_calls.append(messages)
        or scheduled.model_copy(update={"reply": "先休息，等你愿意再说。"}),
    )

    assert schedule_calls[0][-1]["name"] == "schedule_retry"
    assert "future_schedule" not in schedule_calls[0][-1]["content"]
    assert schedule_calls[0][-1]["content"].count("不要") <= 1


def _turn_plan_prompt(
    mode: str,
    *,
    conversation_lead: bool = False,
) -> list[dict[str, str]]:
    prompt = [
        {
            "role": "system",
            "name": "quality_context",
            "content": (
                '{"initiativeExpectation":"proactive",'
                '"initiativeKind":"affection_signal",'
                '"turnPlan":{"mode":"' + mode + '"}}'
            ),
        },
        {
            "role": "system",
            "name": "turn_plan",
            "content": f'{{"mode":"{mode}"}}',
        },
    ]
    if conversation_lead:
        prompt.append(
            {
                "role": "system",
                "name": "conversation_lead",
                "content": (
                    '{"conversationLead":{"intent":"chat",'
                    '"relationshipStage":"married","required":"usually"}}'
                ),
            }
        )
    return prompt


def test_turn_plan_answer_only_does_not_force_proactive_affection() -> None:
    prompt = _turn_plan_prompt("answer_only")
    prompt.append(
        {"role": "user", "name": "player_input", "content": "窗外的雨下得大吗？"}
    )
    result = ProviderResult(
        reply="下得不小，窗台都快积水了。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_turn_plan_answer_plus_lead_does_not_force_proactive_affection() -> None:
    prompt = _turn_plan_prompt("answer_plus_lead", conversation_lead=True)
    prompt.append(
        {"role": "user", "name": "player_input", "content": "符文读数稳定了吗？"}
    )
    result = ProviderResult(
        reply="符文读数稳定了，你想先看哪一组？",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_turn_plan_answer_plus_warmth_only_requires_personal_warmth() -> None:
    prompt = _turn_plan_prompt("answer_plus_warmth", conversation_lead=True)
    prompt.append(
        {"role": "user", "name": "player_input", "content": "你怎么突然这么安静？"}
    )
    result = ProviderResult(
        reply="我想你了。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_turn_plan_boundary_close_allows_a_natural_close_without_affection() -> None:
    prompt = _turn_plan_prompt("boundary_close")
    prompt.append(
        {"role": "user", "name": "player_input", "content": "今天脑子有点乱。"}
    )
    result = ProviderResult(
        reply="那今天先到这里。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    accepted = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
    )

    assert accepted.reply == result.reply
    assert calls == []


def test_turn_plan_retries_the_same_quality_kind_at_most_once() -> None:
    prompt = _turn_plan_prompt("answer_plus_warmth")
    prompt.append(
        {"role": "user", "name": "player_input", "content": "你这会儿在想什么？"}
    )
    result = ProviderResult(
        reply="我在想今晚的风。",
        provider="cloud",
        fallback=False,
        latencyMs=12,
    )
    calls: list[list[dict[str, str]]] = []

    retried = retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result,
        max_retries=3,
    )

    assert retried.reply == result.reply
    assert len(calls) == 1
    assert calls[0][-1]["name"] == "affection_retry"
    assert retried.warnings.count("response_affection_retry: missing_proactive_affection") == 1
