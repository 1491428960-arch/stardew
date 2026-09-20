"""语义层「同概念多实现」审计（P0 #10 / P1 #28 #29 #31）的收口测试。

每节对应审计报告里的一条，docstring 写清**原来的分歧**与**本次建立的语义**，
后面再有改动时以这些断言为准：

- **#28「游戏事件是否已完成」四套匹配规则**：统一到
  ``relationship_gating.game_event_completed``，两边都认命名空间前缀
  （`flashshifter.SVE:56` ↔ `56`），并钉住报告点名的 3:1 分裂用例。
- **#29「群聊回合上限」四处**：统一到 ``group_conversation.turn_budget``；
  场景卡与回退 prompt 走同一个换算、同一份「过滤空 ID 之后」的名单，
  提示词文案也统一（此前全角 `（）` 与半角 `()` 两套）。
- **#31「addressedTo 约束」三处**：抽成 ``_canonical_participant_ids``，
  并把三处口径钉成同一份契约（第三处是只读的 ``providers.py``）。
- **#10「参与者上下文被构建两次」**：voice card 改为**按需构建**，
  主路径（角色卡可用）不再白跑一遍 ``ContextBuilder.build``。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.group_conversation import (
    GroupConversationService,
    GroupResponseError,
    _canonical_participant_ids,
    _normalize_addressed_to,
    build_group_prompt,
    parse_multi_turn_payload,
    turn_budget,
)
from stardew_ai_bridge.models import (
    DialogueTestRequest,
    GroupDialogueRequest,
    ProviderResult,
)
from stardew_ai_bridge.profile_index import ProfileIndexStore
from stardew_ai_bridge.providers import FakeProvider, ProviderRouter
from stardew_ai_bridge.relationship_gating import (
    game_event_completed,
    game_event_id_tokens,
    resolve_relationship_gate,
)
from stardew_ai_bridge.story_state import build_story_state


# ===========================================================================
# #28 游戏事件「是否已完成」：四套匹配规则统一
# ===========================================================================


def test_event_tokens_keep_the_namespace_prefix_and_its_tail() -> None:
    """权威 token 化：带前缀的 ID 同时产出全名与尾段（大小写/空白不敏感）。"""
    tokens = game_event_id_tokens("  FlashShifter.SVE:56  ")

    # 「候选前缀要拆」这条旧契约保留：全名、尾段，以及各自的去分隔符写法。
    assert {"flashshifter.sve:56", "56", "flashshiftersve56"} <= tokens
    assert game_event_id_tokens("   ") == set()
    assert game_event_id_tokens(None) == {"none"}  # 与 story_state 旧行为一致


@pytest.mark.parametrize(
    ("required", "completed"),
    [
        # 报告点名的潜伏分裂：requiredEventId="56" + completed=["flashshifter.SVE:56"]
        ("56", "flashshifter.SVE:56"),
        # 反方向：required 带前缀、completed 只有基线数字
        ("flashshifter.SVE:56", "56"),
        # 同一命名空间与裸 ID
        ("flashshifter.SVE:56", "flashshifter.SVE:56"),
        ("56", "56"),
        # 大小写与两端空白
        ("Fall_14", "  fall_14  "),
        # 分隔符差异（`shane-heart-6` 与人物卡里那种连写事件名原来是两回事，
        # 这条旧契约来自 `story_state` 的去分隔符 token）
        ("shaneheart6", "vanilla:shane-heart-6"),
    ],
)
def test_game_event_completed_accepts_both_prefix_directions(
    required: str, completed: str
) -> None:
    assert game_event_completed(required, {completed}) is True


@pytest.mark.parametrize(
    ("required", "completed"),
    [
        # 不同事件不能被“去分隔符”碰瓷
        ("56", "57"),
        ("1", "11"),
        ("Fall_14", "fall_15"),
        ("", "56"),
        ("   ", "56"),
    ],
)
def test_game_event_completed_rejects_unrelated_ids(
    required: str, completed: str
) -> None:
    assert game_event_completed(required, {completed}) is False


def test_game_event_completed_needs_a_non_empty_completed_set() -> None:
    assert game_event_completed("56", set()) is False


def test_story_state_event_matching_delegates_to_the_authority() -> None:
    """`story_state` 的四套之一改为委托：拆分候选前缀的旧口径要保住。"""
    from stardew_ai_bridge.story_state import _event_tokens, _matches_event

    tokens = _event_tokens("Mod.Pack:EventX")

    assert "mod.pack:eventx" in tokens
    assert "eventx" in tokens
    assert _matches_event("Mod.Pack:EventX", _event_tokens("EventX")) is True
    assert _matches_event("", _event_tokens("EventA")) is False


def test_story_state_completed_events_match_a_namespaced_game_id() -> None:
    """已完成事件带 Mod 命名空间时，内置事件规则同样要认。"""
    state = build_story_state(
        "Shane",
        "close",
        ["flashshifter.SVE:Shane6"],
    )

    assert "recovery" in state["completedStoryStates"]


def _profile_index_with_required_event(tmp_path: Path) -> ProfileIndexStore:
    index = {
        "schemaVersion": 2,
        "profiles": {},
        "voiceCards": {},
        "storyEvents": [
            {
                "eventId": "56",
                "requiredEventId": "56",
                "sourceMod": "Vanilla",
                "sourceKey": "harvey56",
                "participants": ["Harvey"],
                "summary": "诊所里的一次长谈。",
            }
        ],
        "knownCharacters": [
            {
                "npcId": "Harvey",
                "knownNpcId": "Maru",
                "knowledgeScope": "canon_confirmed",
                "confidence": "high",
                "requiredEventId": "56",
                "sourceMod": "Vanilla",
            }
        ],
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return ProfileIndexStore(path)


def test_profile_index_event_gate_accepts_a_namespaced_completed_id(
    tmp_path: Path,
) -> None:
    """报告点名的分裂用例：内容侧声明 `"56"`，游戏侧报 `flashshifter.SVE:56`。

    当前内容库里还没人触发这条（`storyEvents` 为空），所以是潜伏分歧；
    一旦内容侧启用，旧实现会静默把事件判成「没完成」。
    """
    store = _profile_index_with_required_event(tmp_path)

    events = store.story_events(
        "Harvey", ("Vanilla",), completed_event_ids=["flashshifter.SVE:56"]
    )

    assert [item["eventId"] for item in events] == ["56"]
    assert events[0]["status"] == "completed"


def test_profile_index_known_character_gate_accepts_a_namespaced_completed_id(
    tmp_path: Path,
) -> None:
    store = _profile_index_with_required_event(tmp_path)

    known = store.known_characters(
        "Harvey", ("Vanilla",), completed_event_ids=["flashshifter.SVE:56"]
    )

    assert [item["knownNpcId"] for item in known] == ["Maru"]


def test_profile_index_event_dialogue_gate_accepts_a_namespaced_completed_id(
    tmp_path: Path,
) -> None:
    """事件对白证据（第四套之一）同样要认命名空间前缀。"""
    index = {
        "schemaVersion": 2,
        "profiles": {},
        "storyEvents": [],
        "voiceCards": {},
        "speechEvidence": [
            {
                "npcId": "Harvey",
                "eventId": "56",
                "sourceMod": "Vanilla",
                "evidenceKind": "event_dialogue",
                "text": "你别太勉强自己。",
            }
        ],
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    store = ProfileIndexStore(path)

    got = store.speech_evidence(
        "Harvey", ("Vanilla",), completed_event_ids=["flashshifter.SVE:56"]
    )

    assert [item.get("eventId") for item in got] == ["56"]


def test_relationship_gate_and_profile_index_agree_on_the_split_case(
    tmp_path: Path,
) -> None:
    """两套规则必须给出同一答案——这就是「3:1 分裂」要消掉的东西。"""
    store = _profile_index_with_required_event(tmp_path)
    completed = ["flashshifter.SVE:56"]

    index_events = store.story_events("Harvey", ("Vanilla",), completed_event_ids=completed)
    gate = resolve_relationship_gate(
        "Harvey",
        relationship_stage="acquaintance",
        friendship_hearts=3,
        completed_event_ids=completed,
    )

    assert index_events, "内容侧事件应判为已完成"
    assert gate.event_gate_applied is False, "事件锁应判为已解锁"
    assert gate.missing_event_ids == ()


# ===========================================================================
# #29 群聊回合上限：四处统一
# ===========================================================================


@pytest.mark.parametrize(
    ("turn_count", "participant_count", "expected"),
    [
        (None, 2, 2),
        (None, 3, 3),
        (None, 4, 4),
        (None, 5, 4),
        (None, 0, 1),
        (2, 3, 2),
        (4, 2, 4),
    ],
)
def test_turn_budget_stays_the_single_authority(
    turn_count: int | None, participant_count: int, expected: int
) -> None:
    assert turn_budget(turn_count, participant_count) == expected


def _two_turn_prompt(turn_count: int | None) -> str:
    prompt = build_group_prompt(
        active_npc_id="Abigail",
        participants=[
            {"npcId": "Abigail", "displayName": "Abigail"},
            {"npcId": "Emily", "displayName": "Emily"},
        ],
        shared_game_state=None,
        relationship_world=None,
        recent_facts=[],
        public_history=[],
        player_message="你们最近都在忙什么？",
        strategy="multi_turn",
        turn_count=turn_count,
    )
    return json.dumps(prompt, ensure_ascii=False)


def test_prompt_and_scene_card_share_one_turn_budget_formula() -> None:
    """回退 prompt 自己算 limit 时，也要走 turn_budget（含 clamp 与按人数兜底）。"""
    assert "最多输出 2 个公开回合" in _two_turn_prompt(None)
    assert "最多输出 4 个公开回合" in _two_turn_prompt(9)  # clamp 到 _MAX_GROUP_TURNS


def test_prompt_and_scene_card_share_the_same_number_wording() -> None:
    """两条路径此前一个用全角括号、一个用半角，模型看到的是两句不同的话。"""
    rendered = _two_turn_prompt(3)

    assert "最多输出 3 个公开回合" in rendered
    assert "最多输出 3 个公开回合(" not in rendered


def test_turn_budget_counts_only_non_blank_participant_ids() -> None:
    """空 ID 的参与者不该被算进回合额度（此前回退 prompt 用未过滤的人数）。"""
    prompt = build_group_prompt(
        active_npc_id="Abigail",
        participants=[
            {"npcId": "Abigail", "displayName": "Abigail"},
            {"npcId": "Emily", "displayName": "Emily"},
            {"npcId": "", "displayName": "待定"},
        ],
        shared_game_state=None,
        relationship_world=None,
        recent_facts=[],
        public_history=[],
        player_message="你们最近都在忙什么？",
        strategy="multi_turn",
        turn_count=None,
    )
    payload = json.loads(prompt[0]["content"])

    assert "最多输出 2 个公开回合" in payload["instruction"]
    assert [item["npcId"] for item in payload["participants"]] == ["Abigail", "Emily"]


def test_group_turn_count_default_means_unspecified() -> None:
    """models 两处默认值语义统一：请求侧一律用 None 表示「未指定」。

    旧状态：`GroupDialogueRequest.turn_count` 默认 None（服务自己算），
    `DialogueTestRequest.group_turn_count` 默认 2（写死两个回合）——
    同一个概念两个默认值，谁也不知道该信谁。
    """
    request = GroupDialogueRequest.model_validate(
        {
            "strategy": "multi_turn",
            "participants": [{"npcId": "A"}, {"npcId": "B"}],
        }
    )

    assert request.turn_count is None


def test_unspecified_group_turn_count_never_leaks_a_none_slice() -> None:
    """「未指定」不能以 `None` 的形式漏到下游切片里。

    `providers.py` 的演示回复用 `[: request.group_turn_count]` 截断；Python 的
    `slice(stop=None)` **不报错**，而是「切到末尾」——默认值从 2 改成「未指定」
    时必须显式钉住这里跟随名单长度，否则就是一个静默的行为变更。
    语义按「演示回复跟随请求要的回合数」定，名单就是请求。
    """
    request = DialogueTestRequest.model_validate(
        {
            "npcId": "Abigail",
            "message": "你们最近都在忙什么？",
            "groupStrategy": "multi_turn",
            "groupParticipantIds": ["Abigail", "Emily", "Sophia"],
        }
    )

    assert request.group_turn_count == 3

    reply = json.loads(FakeProvider().generate(request).reply)
    assert [turn["speakerNpcId"] for turn in reply["turns"]] == [
        "Abigail",
        "Emily",
        "Sophia",
    ]


def test_private_request_without_a_group_has_no_turn_budget() -> None:
    """私聊请求没有群聊名单，就没有隐式的回合额度可用。"""
    request = DialogueTestRequest.model_validate({"npcId": "Abigail", "message": "嗨。"})

    assert request.group_turn_count is None


def test_group_turn_count_still_accepts_an_explicit_budget() -> None:
    request = DialogueTestRequest.model_validate(
        {"npcId": "Abigail", "message": "嗨。", "groupTurnCount": 3}
    )

    assert request.group_turn_count == 3

    single = DialogueTestRequest.model_validate(
        {
            "npcId": "Abigail",
            "message": "嗨。",
            "groupStrategy": "multi_turn",
            "groupParticipantIds": ["Abigail", "Emily", "Sophia"],
            "groupTurnCount": 1,
        }
    )

    assert single.group_turn_count == 1  # 显式值压过名单长度


# ===========================================================================
# #31 addressedTo 约束：三处同口径
# ===========================================================================


def test_canonical_participant_ids_is_the_shared_roster_index() -> None:
    ids = _canonical_participant_ids(["Sophia", "  emily ", "", "SOPHIA"])

    assert set(ids) == {"sophia", "emily"}
    assert ids["sophia"] == "Sophia"  # 保留规范写法，供回放页显示
    assert ids["emily"] == "emily"


def test_normalize_addressed_to_uses_that_index() -> None:
    ids = _canonical_participant_ids(["Sophia", "Emily"])

    assert _normalize_addressed_to(["player", "you"], set(ids.values())) == []
    assert _normalize_addressed_to(["sophia", "SOPHIA", "outsider"], set(ids.values())) == [
        "Sophia"
    ]
    assert _normalize_addressed_to("Sophia", set(ids.values())) == []


def test_parser_speaker_check_and_addressed_to_check_share_one_roster() -> None:
    """解析处的「发言人必须在名单内」与归一化处的「目标必须在名单内」同源：

    同一份名单既能拒绝 `outsider` 这种发言人，也能把 `EMILY` 归一成规范写法。
    """
    turns, _ = parse_multi_turn_payload(
        json.dumps(
            {
                "turns": [
                    {
                        "speakerNpcId": "sophia",
                        "content": "葡萄园的颜色确实让人停一下。",
                        "addressedTo": ["EMILY", "player"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        participant_ids={"Sophia", "Emily"},
        expected_turn_count=3,
    )

    assert turns[0].speaker_npc_id == "sophia"
    # 名单内的目标保留规范写法，名单外的 `player` 丢掉。
    assert turns[0].addressed_to == ["Emily"]
    with pytest.raises(GroupResponseError, match="未知发言人"):
        parse_multi_turn_payload(
            '{"turns":[{"speakerNpcId":"outsider","content":"我也说一句。"}]}',
            participant_ids={"Sophia", "Emily"},
            expected_turn_count=3,
        )


def test_fake_provider_addresses_nobody_outside_the_roster() -> None:
    """第三处（只读的 `providers.py`）输出空 addressedTo：与另两处口径一致。"""
    request = DialogueTestRequest.model_validate(
        {
            "npcId": "Abigail",
            "message": "你们最近都在忙什么？",
            "provider": "fake",
            "groupStrategy": "multi_turn",
            "groupParticipantIds": ["Abigail", "Emily", "outsider"],
            "groupTurnCount": 2,
        }
    )

    reply = json.loads(FakeProvider().generate(request).reply)
    roster = _canonical_participant_ids(request.group_participant_ids)

    assert reply["turns"]
    for turn in reply["turns"]:
        assert turn["addressedTo"] == []
        assert turn["speakerNpcId"].casefold() in roster


# ===========================================================================
# #10 参与者上下文只构建一次
# ===========================================================================


def _router(provider: object) -> ProviderRouter:
    return ProviderRouter(
        local_provider=provider,
        cloud_enabled=False,
        cloud_only=False,
        default_provider="local",
    )


class _RecordingReplyProvider:
    name = "recording"

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.requests = []

    def generate(self, request, *, messages=None):  # type: ignore[no-untyped-def]
        self.requests.append((request, messages))
        return ProviderResult(
            reply=self.replies.pop(0),
            provider=self.name,
            fallback=False,
            latencyMs=1,
        )


def _cards_service(provider: object, calls: list[str]) -> GroupConversationService:
    def voice_card_provider(participants):  # type: ignore[no-untyped-def]
        calls.append("voice_cards")
        return {item.npc_id.casefold(): {"tone": "轻快"} for item in participants}

    def prompt_provider(participants, request):  # type: ignore[no-untyped-def]
        calls.append("role_cards")
        return {
            item.npc_id.casefold(): [
                {"role": "system", "name": "npcIdentity", "content": f"你是 {item.npc_id}"}
            ]
            for item in participants
        }

    return GroupConversationService(
        _router(provider),
        voice_card_provider=voice_card_provider,
        prompt_provider=prompt_provider,
    )


def _multi_turn_request() -> GroupDialogueRequest:
    return GroupDialogueRequest.model_validate(
        {
            "message": "你们最近都在忙什么？",
            "provider": "local",
            "strategy": "multi_turn",
            "participants": [
                {"npcId": "Abigail", "displayName": "Abigail"},
                {"npcId": "Emily", "displayName": "Emily"},
            ],
            "turnCount": 2,
        }
    )


def test_main_path_never_builds_the_voice_cards() -> None:
    """主路径（角色卡可用）里那份声线卡产物没有任何人读——不该再构建它。"""
    calls: list[str] = []
    provider = _RecordingReplyProvider(
        [json.dumps({"turns": [{"speakerNpcId": "Abigail", "content": "在练琴。"}]}, ensure_ascii=False)]
    )

    response = _cards_service(provider, calls).generate(_multi_turn_request())

    assert [turn.speaker_npc_id for turn in response.turns] == ["Abigail"]
    assert calls == ["role_cards"]


def test_fallback_path_still_builds_the_voice_cards() -> None:
    """回退路径（没有角色卡）依然要声线卡，否则回退 prompt 的 voice 段就空了。"""
    calls: list[str] = []
    provider = _RecordingReplyProvider(
        [json.dumps({"turns": [{"speakerNpcId": "Abigail", "content": "在练琴。"}]}, ensure_ascii=False)]
    )
    service = GroupConversationService(
        _router(provider),
        voice_card_provider=lambda participants: (
            calls.append("voice_cards")
            or {item.npc_id.casefold(): {"tone": "轻快"} for item in participants}
        ),
        prompt_provider=None,
    )

    response = service.generate(_multi_turn_request())

    assert [turn.speaker_npc_id for turn in response.turns] == ["Abigail"]
    assert calls == ["voice_cards"]
    roster = json.loads(provider.requests[0][1][0]["content"])["participants"]
    assert roster[0]["voice"] == {"tone": "轻快"}
