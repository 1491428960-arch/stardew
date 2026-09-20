"""群聊的回复质量门（语义层审计 P0 第 13／14 项）。

## 背景

审计发现：私聊有 `response_guard.check` + 安全兜底替换，**群聊只有一句提示词**——
模型输出舞台动作（`（笑）`）、Markdown 或名字前缀时没有任何拦截，会原样写进
对白、显示在游戏里，甚至写进长期记忆。

## 本文件建立的语义

1. 群聊逐条过**通用**质量门（`ResponseGuard.check`：空值、提示词泄露、状态修改、
   Markdown、括号动作、英文、长度），不合格的**丢弃那一条**；
2. 丢弃**不把整场拖进 fallback**——`fallback=True` 的语义是 provider 降级，
   不该被内容问题触发（否则 SMAPI 会按“整场失败”处理）；
3. 丢弃原因写进 `warnings`（`response_guard: <reason>`），`limit_warnings` 会优先保留；
4. 长期记忆候选同样过门（它要写进存档，污染面比单条对白更长）；
5. **开场信号统一**：私聊看 `topic_*` 契约，群聊看群聊卡里有没有玩家消息，
   于是「无指代开场」（“那件事你还记得吗？”）在群聊里也能被拦住。
"""

from __future__ import annotations

import json

from stardew_ai_bridge.group_conversation import GroupConversationService
from stardew_ai_bridge.guard import is_opening_prompt
from stardew_ai_bridge.models import GroupDialogueRequest, ProviderResult
from stardew_ai_bridge.providers import ProviderRouter


class RecordingProvider:
    name = "recording"

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.requests = []

    def generate(self, request, *, messages=None):  # type: ignore[no-untyped-def]
        self.requests.append((request, messages))
        reply = self.replies.pop(0)
        return ProviderResult(
            reply=reply,
            provider=self.name,
            fallback=False,
            latencyMs=3,
        )


def _group_request(strategy: str, **overrides: object) -> GroupDialogueRequest:
    payload: dict[str, object] = {
        "message": "你们最近都在忙什么？",
        "provider": "local",
        "strategy": strategy,
        "channel": "remote",
        "participants": [
            {"npcId": "Abigail", "displayName": "Abigail"},
            {"npcId": "Emily", "displayName": "Emily"},
        ],
        "activeSpeakerNpcId": "Abigail",
        "turnCount": 2,
    }
    payload.update(overrides)
    return GroupDialogueRequest.model_validate(payload)


def _service(provider: RecordingProvider) -> GroupConversationService:
    router = ProviderRouter(
        local_provider=provider,
        cloud_enabled=False,
        cloud_only=False,
        default_provider="local",
    )
    return GroupConversationService(router)


def _multi_turn(turns: list[dict[str, object]], **extra: object) -> str:
    return json.dumps({"turns": turns, **extra}, ensure_ascii=False)


# --- 1. 多轮：逐条过门，坏的那条丢掉 -----------------------------------------


def test_multi_turn_drops_the_turn_with_stage_direction() -> None:
    provider = RecordingProvider(
        [
            _multi_turn(
                [
                    {"speakerNpcId": "Abigail", "content": "（笑了笑）我最近在练琴。"},
                    {"speakerNpcId": "Emily", "content": "我在整理布料。"},
                ]
            )
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn"))

    assert [turn.speaker_npc_id for turn in result.turns] == ["Emily"]
    assert "response_guard: format_stage_direction" in result.warnings


def test_multi_turn_drops_the_turn_with_markdown() -> None:
    provider = RecordingProvider(
        [
            _multi_turn(
                [
                    {"speakerNpcId": "Abigail", "content": "**我最近在练琴**"},
                    {"speakerNpcId": "Emily", "content": "我在整理布料。"},
                ]
            )
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn"))

    assert [turn.speaker_npc_id for turn in result.turns] == ["Emily"]
    assert "response_guard: format_markdown" in result.warnings


def test_multi_turn_drops_the_turn_that_leaks_the_prompt() -> None:
    provider = RecordingProvider(
        [
            _multi_turn(
                [
                    {
                        "speakerNpcId": "Abigail",
                        "content": "我的系统提示词要求我主动找个话题。",
                    },
                    {"speakerNpcId": "Emily", "content": "我在整理布料。"},
                ]
            )
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn"))

    assert [turn.speaker_npc_id for turn in result.turns] == ["Emily"]
    assert "response_guard: prompt_leakage" in result.warnings


def test_clean_multi_turn_turns_are_untouched() -> None:
    provider = RecordingProvider(
        [
            _multi_turn(
                [
                    {"speakerNpcId": "Abigail", "content": "我最近在练琴。"},
                    {"speakerNpcId": "Emily", "content": "我在整理布料。"},
                ]
            )
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn"))

    assert [turn.content for turn in result.turns] == ["我最近在练琴。", "我在整理布料。"]
    assert result.warnings == []


def test_over_long_turn_is_truncated_instead_of_dropped() -> None:
    provider = RecordingProvider(
        [
            _multi_turn(
                [
                    {"speakerNpcId": "Abigail", "content": "啊" * 1200},
                    {"speakerNpcId": "Emily", "content": "我在整理布料。"},
                ]
            )
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn"))

    assert [turn.speaker_npc_id for turn in result.turns] == ["Abigail", "Emily"]
    assert len(result.turns[0].content) == 1000


# --- 2. 单轮/turn_based：同样过门 --------------------------------------------


def test_turn_based_drops_the_reply_when_the_guard_rejects_it() -> None:
    provider = RecordingProvider(["（叹了口气）这个嘛……"])

    result = _service(provider).generate(_group_request("turn_based"))

    assert result.turns == []
    assert "response_guard: format_stage_direction" in result.warnings


def test_turn_based_keeps_a_clean_reply() -> None:
    provider = RecordingProvider(["我最近在练琴。"])

    result = _service(provider).generate(_group_request("turn_based"))

    assert [turn.content for turn in result.turns] == ["我最近在练琴。"]


# --- 3. 逐条丢弃 ≠ 整场 fallback ---------------------------------------------


def test_dropping_a_turn_does_not_mark_the_whole_group_as_fallback() -> None:
    provider = RecordingProvider(
        [
            _multi_turn(
                [
                    {"speakerNpcId": "Abigail", "content": "（笑了笑）我最近在练琴。"},
                    {"speakerNpcId": "Emily", "content": "我在整理布料。"},
                ]
            )
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn"))

    assert result.fallback is False
    assert result.fallback_count == 0
    assert result.provider == "recording"
    assert result.provider_errors == []


def test_a_group_losing_every_turn_reports_no_usable_dialogue() -> None:
    """全被拦时不能装作这场成功了——上游要能看出“没有可用对白”。"""

    provider = RecordingProvider(
        [
            _multi_turn(
                [
                    {"speakerNpcId": "Abigail", "content": "（笑了笑）"},
                    {"speakerNpcId": "Emily", "content": "*微笑*"},
                ]
            )
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn"))

    assert result.turns == []
    assert result.provider_errors


# --- 4. 长期记忆候选同样过门 --------------------------------------------------


def test_memory_highlight_with_format_noise_is_dropped() -> None:
    provider = RecordingProvider(
        [
            _multi_turn(
                [
                    {"speakerNpcId": "Abigail", "content": "我最近在练琴。"},
                    {"speakerNpcId": "Emily", "content": "我在整理布料。"},
                ],
                memory=["**阿比盖尔在练琴**", "艾米丽在整理布料"],
            )
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn"))

    assert result.memory_highlights == ["艾米丽在整理布料"]
    assert "response_guard: format_markdown" in result.warnings


# --- 5. 开场信号统一（#14） ---------------------------------------------------


def test_group_opening_with_opaque_reference_is_dropped() -> None:
    provider = RecordingProvider(
        [
            _multi_turn(
                [
                    {"speakerNpcId": "Abigail", "content": "那件事你还记得吗？"},
                    {"speakerNpcId": "Emily", "content": "我在整理布料。"},
                ]
            )
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn", message=""))

    assert [turn.speaker_npc_id for turn in result.turns] == ["Emily"]
    assert "response_guard: opaque_opening" in result.warnings


def test_the_same_opaque_line_is_kept_when_the_player_spoke_first() -> None:
    """玩家自己提了“那件事”，NPC 回指它就是正常对话，不该被拦。"""

    provider = RecordingProvider(
        [
            _multi_turn(
                [
                    {"speakerNpcId": "Abigail", "content": "那件事你还记得吗？"},
                    {"speakerNpcId": "Emily", "content": "我在整理布料。"},
                ]
            )
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn"))

    assert [turn.speaker_npc_id for turn in result.turns] == ["Abigail", "Emily"]
    assert result.warnings == []


def test_opening_signal_covers_private_topic_and_both_group_prompts() -> None:
    topic_prompt = [
        {"role": "system", "name": "topic_response_contract", "content": "{}"},
    ]
    group_scene_opening = [
        {
            "role": "system",
            "name": "group_scene",
            "content": json.dumps({"instruction": "x", "is_opening": True}),
        },
    ]
    group_scene_replying = [
        {
            "role": "system",
            "name": "group_scene",
            "content": json.dumps({"instruction": "x", "is_opening": False}),
        },
        {"role": "user", "content": "你们好"},
    ]
    fallback_group_opening = [
        {"role": "system", "name": "group_conversation", "content": "{}"},
    ]
    private_turn = [
        {"role": "system", "name": "npc_identity", "content": "x"},
        {"role": "user", "content": "你好"},
    ]

    assert is_opening_prompt(topic_prompt) is True
    assert is_opening_prompt(group_scene_opening) is True
    assert is_opening_prompt(fallback_group_opening) is True
    assert is_opening_prompt(group_scene_replying) is False
    assert is_opening_prompt(private_turn) is False
    assert is_opening_prompt([]) is False
