"""群聊的「开场」语义：玩家一句话都没说时，由 NPC 自己起头。

## 背景（2026-09-20 用户反馈）

> 预设的群聊由 NPC 开始话题吧，不然起不到引导玩家的作用。

而现状不只是“没有开场”——**它是一个真 bug**：

- `_group_scene_instruction` 里写着「谁说话：**第一个发言的人先接玩家**」；
- `build_group_messages` 是 `if player_message:` 才追加 user 消息；
- `build_group_prompt` 更直接，**无条件**追加 `{"role": "user", "content": player_message}`。

于是当 `player_message` 为空（**接受邀约后还没打字，正是这个状态**），
指令在要求“接玩家”，而消息里根本没有玩家的话——模型只能凭空猜，
甚至可能“回应”一句玩家从未说过的话。

## 本次建立的语义

**`player_message` 为空（或纯空白）⇒ 这是「开场」**：

1. 指令改成让 NPC 自己起话题，而不是接玩家；
2. **明确禁止假定玩家说过任何话**——这与 `storyEvents` 那条
   “防止 NPC 全知”的原则是同一类问题；
3. 开场时**不再追加空的 user 消息**；
4. 其余约束（不替别人发言、不加名单外人、不改游戏状态）**一条都不能少**；
5. **邀约的 `topic`／`guidance` 上下文仍然在**——那才是开场的受控话题来源。
"""

from __future__ import annotations

import json

import pytest

from stardew_ai_bridge.group_conversation import (
    _group_scene_instruction,
    build_group_messages,
    build_group_prompt,
)

_ROSTER = ["Shane", "Emily"]
_PARTICIPANTS = [
    {"npcId": "Shane", "displayName": "谢恩"},
    {"npcId": "Emily", "displayName": "艾米丽"},
]


def _instruction(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "active_npc_id": "Shane",
        "roster_ids": _ROSTER,
        "strategy": "multi_turn",
        "turn_count": 2,
    }
    kwargs.update(overrides)
    return _group_scene_instruction(**kwargs)  # type: ignore[arg-type]


def _messages(player_message: str) -> tuple[str, list[dict[str, str]]]:
    messages = build_group_messages(
        participants=_PARTICIPANTS,
        active_npc_id="Shane",
        participant_prompts=None,
        strategy="multi_turn",
        turn_count=2,
        player_message=player_message,
    )
    scene = next(m for m in messages if m.get("name") == "group_scene")
    return json.loads(scene["content"])["instruction"], messages


# --- 1. 指令本身 -----------------------------------------------------------


def test_the_default_instruction_still_waits_for_the_player() -> None:
    # 回归保护：不传 is_opening 时必须与原来一致。
    text = _instruction()

    assert "第一个发言的人先接玩家" in text


def test_the_opening_instruction_asks_the_npcs_to_start() -> None:
    text = _instruction(is_opening=True)

    assert "第一个发言的人先接玩家" not in text
    assert "玩家" in text
    # 要明确“自己起个头”，而不是等玩家
    assert any(word in text for word in ("起个头", "起个话头", "自己开", "先开"))


def test_the_opening_instruction_forbids_assuming_the_player_spoke() -> None:
    # 关键约束：不能凭空“回应”玩家没说过的话。
    text = _instruction(is_opening=True)

    assert any(
        phrase in text
        for phrase in ("还没有说话", "没有说过", "不要假定玩家", "不得假定玩家")
    )


@pytest.mark.parametrize(
    "must_keep",
    # 注意：**不含“不能替……发言”** —— multi_turn 分支刻意允许多人发言，
    # 那条约束只存在于非 multi_turn 分支；这里的替代约束是
    # “每个回合只说对应 speakerNpcId 自己的话”。
    ["名单外", "不能修改关系", "只输出 JSON", "speakerNpcId"],
)
def test_the_opening_instruction_keeps_every_other_constraint(must_keep: str) -> None:
    # 加开场语义不能把原有约束挤掉。
    assert must_keep in _instruction(is_opening=True)


# --- 2. 多轮路径（build_group_messages）------------------------------------


def test_an_empty_player_message_uses_the_opening_instruction() -> None:
    instruction, messages = _messages("")

    assert "第一个发言的人先接玩家" not in instruction
    assert not any(m.get("role") == "user" for m in messages)


def test_a_whitespace_only_message_also_counts_as_opening() -> None:
    instruction, messages = _messages("   ")

    assert "第一个发言的人先接玩家" not in instruction
    assert not any(m.get("role") == "user" for m in messages)


def test_a_real_player_message_keeps_the_normal_flow() -> None:
    instruction, messages = _messages("你们周末都干嘛？")

    assert "第一个发言的人先接玩家" in instruction
    user_messages = [m for m in messages if m.get("role") == "user"]
    assert len(user_messages) == 1
    assert user_messages[0]["content"] == "你们周末都干嘛？"


def test_the_scene_card_is_always_present_when_opening() -> None:
    _, messages = _messages("")

    assert any(m.get("name") == "group_scene" for m in messages)


# --- 3. 单轮路径（build_group_prompt）--------------------------------------


def _prompt_messages(player_message: str) -> list[dict[str, str]]:
    return build_group_prompt(
        active_npc_id="Shane",
        participants=_PARTICIPANTS,  # type: ignore[arg-type]
        shared_game_state=None,
        relationship_world=None,
        recent_facts=[],
        public_history=[],
        player_message=player_message,
        strategy="multi_turn",
        turn_count=2,
        invitation_topic="矿洞传闻",
        invitation_guidance="围绕最近发现的矿石聊聊",
    )


def test_the_prompt_path_does_not_append_an_empty_user_message() -> None:
    # 这条现在是 bug：无论玩家消息是否为空都会追加。
    messages = _prompt_messages("")

    assert not any(m.get("role") == "user" for m in messages)


def test_the_prompt_path_still_appends_a_real_message() -> None:
    messages = _prompt_messages("你们周末都干嘛？")

    user_messages = [m for m in messages if m.get("role") == "user"]
    assert len(user_messages) == 1
    assert user_messages[0]["content"] == "你们周末都干嘛？"


def test_the_prompt_path_marks_it_as_an_opening() -> None:
    messages = _prompt_messages("")
    scene = next(m for m in messages if m.get("name") == "group_conversation")
    instruction = json.loads(scene["content"])["instruction"]

    assert any(word in instruction for word in ("起个头", "起个话头", "自己开", "先开"))


def test_the_prompt_path_keeps_the_invitation_context_when_opening() -> None:
    # 开场的话题来源正是邀约的 topic/guidance，不能丢。
    messages = _prompt_messages("")
    scene = next(m for m in messages if m.get("name") == "group_conversation")
    invitation = json.loads(scene["content"])["invitation"]

    assert invitation["topic"] == "矿洞传闻"
    assert invitation["guidance"] == "围绕最近发现的矿石聊聊"

# --- 4. 多轮路径必须带上邀约的话题 -----------------------------------------


def test_the_multi_turn_path_carries_the_invitation() -> None:
    """回归保护（2026-09-20 用户实测发现）。

    用户反馈“主题是动物，但具体内容还是矿洞”。真因是 `build_group_messages`
    的场景卡里**没有 invitation**，而实际用的正是多轮路径——于是邀约的
    topic/guidance 根本进不了 prompt，模型只知道“这是群聊”，便按角色卡
    自由发挥。单轮路径 `build_group_prompt` 一直带着它，两条路径在此不一致。
    """
    _, messages = _messages("")
    scene = next(m for m in messages if m.get("name") == "group_scene")
    assert "invitation" in json.loads(scene["content"])


def test_the_invitation_reaches_the_multi_turn_scene_card() -> None:
    messages = build_group_messages(
        participants=_PARTICIPANTS,
        active_npc_id="Shane",
        participant_prompts=None,
        strategy="multi_turn",
        turn_count=2,
        player_message="",
        invitation_topic="养的动物",
        invitation_guidance="说自己的观察和照料方式。",
    )
    scene = next(m for m in messages if m.get("name") == "group_scene")
    invitation = json.loads(scene["content"])["invitation"]

    assert invitation["topic"] == "养的动物"
    assert invitation["guidance"] == "说自己的观察和照料方式。"
    # 约定必须写明：方向不是已确认的事实
    assert "不是" in invitation["scope"]


def test_no_invitation_means_an_empty_object() -> None:
    messages = build_group_messages(
        participants=_PARTICIPANTS,
        active_npc_id="Shane",
        participant_prompts=None,
        strategy="multi_turn",
        turn_count=2,
        player_message="",
    )
    scene = next(m for m in messages if m.get("name") == "group_scene")

    assert json.loads(scene["content"])["invitation"] == {}

def test_limit_warnings_caps_and_keeps_guard_entries() -> None:
    """回归保护（2026-09-20 语义层审计）。

    群聊响应此前直接 `warnings=warnings` 不截断，而 models.py 声明 max_length=20，
    累积超过 20 条时 pydantic 校验失败 → 端点 500（私聊有 _limit_warnings，群聊没有）。
    现在两边共用 group_conversation.limit_warnings。
    """
    from stardew_ai_bridge.group_conversation import limit_warnings

    many = [f"provider: note {index}" for index in range(30)]
    capped = limit_warnings(many)
    assert len(capped) == 20
    # 保留的是末尾（最新的）
    assert capped[-1] == "provider: note 29"

    # guard 类警告必须保留，即使它在很前面
    mixed = ["response_guard: 越界"] + [f"provider: note {index}" for index in range(30)]
    kept = limit_warnings(mixed)
    assert len(kept) == 20
    assert "response_guard: 越界" in kept

