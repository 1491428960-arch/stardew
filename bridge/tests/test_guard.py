from __future__ import annotations

import pytest

try:
    from stardew_ai_bridge.evaluation_budget import EvaluationBudgetExceeded
    from stardew_ai_bridge.guard import ResponseGuard, retry_for_format_noise
    from stardew_ai_bridge.models import ProviderResult
except ModuleNotFoundError:
    class ResponseGuard:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

    def check(self, reply: object) -> object:
        del reply
        pytest.fail("Task 4 Response Guard 尚未实现")

    retry_for_format_noise = None
    ProviderResult = None
    EvaluationBudgetExceeded = RuntimeError


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
    assert retried.warnings.count("response_format_retry: stage_direction") == 2


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
    ) == 2


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
    assert "response_affection_retry: missing_proactive_affection" in retried.warnings


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
    ) == 2


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
