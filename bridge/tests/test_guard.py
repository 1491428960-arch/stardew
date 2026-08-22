from __future__ import annotations

import pytest

try:
    from stardew_ai_bridge.guard import ResponseGuard
except ModuleNotFoundError:
    class ResponseGuard:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def check(self, reply: object) -> object:
            del reply
            pytest.fail("Task 4 Response Guard 尚未实现")


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
