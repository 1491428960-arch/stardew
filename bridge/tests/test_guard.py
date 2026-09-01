from __future__ import annotations

import pytest

try:
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
    ],
)
def test_response_guard_rejects_prompt_leakage(reply: str) -> None:
    result = ResponseGuard().check(reply)

    assert result.accepted is False
    assert result.reason == "prompt_leakage"


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
