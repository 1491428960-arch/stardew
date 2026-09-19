import json

import pytest
from pydantic import ValidationError

from stardew_ai_bridge.group_conversation import (
    GroupResponseError,
    GroupConversationService,
    build_group_prompt,
    parse_multi_turn_payload,
    parse_multi_turn_reply,
    turn_budget,
)
from stardew_ai_bridge.group_conversation_cases import (
    comparable_group_payload,
    group_case_catalog,
)
from stardew_ai_bridge.models import DialogueTestRequest, GroupDialogueRequest, ProviderResult
from stardew_ai_bridge.providers import FakeProvider, ProviderRouter


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


def test_group_request_accepts_remote_participants_and_public_history() -> None:
    request = GroupDialogueRequest.model_validate(
        {
            "message": "你们最近都在忙什么？",
            "provider": "fake",
            "strategy": "turn_based",
            "channel": "remote",
            "participants": [
                {"npcId": "Abigail", "displayName": "Abigail"},
                {"npcId": "Emily", "displayName": "Emily"},
            ],
            "activeSpeakerNpcId": "Abigail",
            "history": [
                {
                    "speakerType": "player",
                    "speakerId": "player",
                    "content": "晚上好。",
                    "visibility": "public",
                }
            ],
        }
    )

    assert request.channel == "remote"
    assert [item.npc_id for item in request.participants] == ["Abigail", "Emily"]
    assert request.history[0].speaker_id == "player"


def test_group_request_accepts_invitation_context() -> None:
    request = GroupDialogueRequest.model_validate(
        {
            "message": "你们怎么看？",
            "provider": "fake",
            "strategy": "turn_based",
            "channel": "remote",
            "participants": [
                {"npcId": "Abigail", "displayName": "Abigail"},
                {"npcId": "Emily", "displayName": "Emily"},
            ],
            "invitationTopic": "奇怪的矿石",
            "invitationGuidance": "只把它当作讨论方向，不把它当作已经确认的事实。",
        }
    )

    assert request.invitation_topic == "奇怪的矿石"
    assert "讨论方向" in request.invitation_guidance


def test_group_request_rejects_empty_message_for_every_strategy() -> None:
    for strategy in ("fanout", "turn_based", "multi_turn"):
        with pytest.raises(ValidationError, match="消息不能为空"):
            _group_request(strategy, message="")


@pytest.mark.parametrize(
    "patch",
    [
        {"channel": "face_to_face"},
        {"participants": [{"npcId": "Abigail"}]},
        {
            "participants": [
                {"npcId": "A"},
                {"npcId": "B"},
                {"npcId": "C"},
                {"npcId": "D"},
            ]
        },
        {"strategy": "unknown"},
    ],
)
def test_group_request_rejects_unsupported_shape(patch: dict[str, object]) -> None:
    payload = {
        "message": "测试",
        "provider": "fake",
        "strategy": "fanout",
        "channel": "remote",
        "participants": [
            {"npcId": "Abigail"},
            {"npcId": "Emily"},
        ],
    }
    payload.update(patch)

    with pytest.raises(ValidationError):
        GroupDialogueRequest.model_validate(payload)


def test_group_prompt_marks_roster_and_forbids_speaking_for_other_npcs() -> None:
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
        player_message="你们谁更喜欢夜市？",
        strategy="turn_based",
    )
    rendered = json.dumps(prompt, ensure_ascii=False)

    assert "Abigail" in rendered
    assert "Emily" in rendered
    assert "只能说 Abigail 自己的话" in rendered
    assert "不能替 Emily 发言" in rendered
    assert "channel=remote" in rendered


def test_multi_turn_prompt_allows_natural_interruption_without_forcing_one_reply_each() -> None:
    prompt = build_group_prompt(
        active_npc_id="Abigail",
        participants=[
            {"npcId": "Abigail", "displayName": "Abigail"},
            {"npcId": "Emily", "displayName": "Emily"},
            {"npcId": "Sebastian", "displayName": "Sebastian"},
        ],
        shared_game_state=None,
        relationship_world=None,
        recent_facts=[],
        public_history=[],
        player_message="你们谁先说说今晚想听什么？",
        strategy="multi_turn",
    )
    rendered = json.dumps(prompt, ensure_ascii=False)

    assert "自然接话流" in rendered
    assert "不要求每个人都发言" in rendered
    assert "允许另一个 NPC 插话" in rendered
    assert "当前发言人只能说 Abigail" not in rendered


def test_multi_turn_prompt_requires_addressed_follow_up_and_one_exchange() -> None:
    prompt = build_group_prompt(
        active_npc_id="Sophia",
        participants=[
            {"npcId": "Sophia", "displayName": "Sophia"},
            {"npcId": "Emily", "displayName": "Emily"},
        ],
        shared_game_state=None,
        relationship_world=None,
        recent_facts=[],
        public_history=[],
        player_message="我昨天路过葡萄园，那些颜色让我有点走神。",
        strategy="multi_turn",
        turn_count=3,
    )
    rendered = json.dumps(prompt, ensure_ascii=False)

    assert "点名了名单里的另一个人（addressedTo），那个人应当接一轮" in rendered
    assert "整段至少出现一次来回" in rendered
    assert "不要求每个人都发言" in rendered


def test_group_prompt_forbids_name_prefixes_and_stage_directions() -> None:
    for strategy in ("fanout", "turn_based", "multi_turn"):
        prompt = build_group_prompt(
            active_npc_id="Shane",
            participants=[
                {"npcId": "Shane", "displayName": "Shane"},
                {"npcId": "Harvey", "displayName": "Harvey"},
            ],
            shared_game_state=None,
            relationship_world=None,
            recent_facts=[],
            public_history=[],
            player_message="我最近总是睡不好。",
            strategy=strategy,
            turn_count=3,
        )
        rendered = json.dumps(prompt, ensure_ascii=False)

        assert "不要在对白开头重复写自己的名字" in rendered
        assert "不要写括号里的舞台动作" in rendered


def test_group_prompt_carries_each_participant_voice_card() -> None:
    prompt = build_group_prompt(
        active_npc_id="Sophia",
        participants=[
            {"npcId": "Sophia", "displayName": "Sophia"},
            {"npcId": "Elliott", "displayName": "Elliott"},
        ],
        shared_game_state=None,
        relationship_world=None,
        recent_facts=[],
        public_history=[],
        player_message="我昨天路过葡萄园。",
        strategy="multi_turn",
        turn_count=3,
        participant_cards={
            "sophia": {
                "tone": "轻快、跳拍",
                "voiceAnchors": ["呃……你好。你需要点什么吗？"],
                "signatureMoves": ["先惊呼再补具体事实"],
            },
            "elliott": {
                "tone": "铺陈、自嘲",
                "voiceAnchors": ["我写的东西，大多还在抽屉里躺着。"],
                "topicHints": ["克制的干燥幽默"],
            },
        },
    )
    payload = json.loads(prompt[0]["content"])
    roster = {item["npcId"]: item for item in payload["participants"]}

    assert roster["Sophia"]["voice"]["tone"] == "轻快、跳拍"
    assert roster["Sophia"]["voice"]["voiceAnchors"] == ["呃……你好。你需要点什么吗？"]
    assert roster["Elliott"]["voice"]["topicHints"] == ["克制的干燥幽默"]
    assert "voice" not in roster.get("Unknown", {})


def test_group_prompt_states_natural_dialogue_contract() -> None:
    prompt = build_group_prompt(
        active_npc_id="Elliott",
        participants=[
            {"npcId": "Elliott", "displayName": "Elliott"},
            {"npcId": "Harvey", "displayName": "Harvey"},
        ],
        shared_game_state=None,
        relationship_world=None,
        recent_facts=[],
        public_history=[],
        player_message="我在整理一份旧记录。",
        strategy="multi_turn",
        turn_count=3,
    )
    rendered = json.dumps(prompt, ensure_ascii=False)

    assert "不要写成散文或统一的书面模板" in rendered
    assert "比喻只在角色本来就会用时才用" in rendered
    assert "优先参考每个参与者 voice.voiceAnchors 的句式和口语颗粒度" in rendered


def test_build_group_voice_cards_reuses_the_single_npc_pipeline() -> None:
    from stardew_ai_bridge.prompts import build_group_voice_cards

    calls: list[dict] = []

    class FakeContextBuilder:
        def build(self, payload, source_mods=(), **values):
            calls.append(dict(payload))
            return {
                "identity": {
                    "npcId": payload["npcId"],
                    "voiceStyle": {
                        "tone": "轻快、跳拍",
                        "signatureMoves": ["先惊呼再补具体事实"],
                    },
                },
                "voiceCard": {
                    "topicHints": ["明确不确定性"],
                    "voiceAnchors": [
                        {"text": "呃……你好。你需要点什么吗？"},
                        {"text": "长" * 200},
                    ],
                },
            }

    cards = build_group_voice_cards(
        FakeContextBuilder(),
        [
            {"npcId": "Sophia", "displayName": "Sophia", "sourceMods": ["SVE"]},
            {"npcId": "Elliott", "displayName": "Elliott"},
        ],
    )

    assert calls[0]["npcId"] == "Sophia"
    assert calls[0]["sourceMods"] == ["SVE"]
    assert cards["sophia"]["tone"] == "轻快、跳拍"
    assert cards["sophia"]["voiceAnchors"] == ["呃……你好。你需要点什么吗？"]
    assert cards["sophia"]["signatureMoves"] == ["先惊呼再补具体事实"]
    assert cards["sophia"]["topicHints"] == ["明确不确定性"]
    assert cards["elliott"]["tone"] == "轻快、跳拍"


def test_build_group_voice_cards_tolerates_missing_persona_data() -> None:
    from stardew_ai_bridge.prompts import build_group_voice_cards

    class EmptyContextBuilder:
        def build(self, payload, source_mods=(), **values):
            return {}

    cards = build_group_voice_cards(EmptyContextBuilder(), [{"npcId": "Harvey"}])

    assert cards == {}


def test_group_messages_reuse_the_single_npc_role_cards() -> None:
    from stardew_ai_bridge.group_conversation import build_group_messages

    sophia_card = [
        {"role": "system", "name": "identity", "content": "你是 Sophia"},
        {"role": "system", "name": "voice_card", "content": "sophia voice"},
        {"role": "user", "content": "我昨天路过葡萄园。"},
    ]
    emily_card = [
        {"role": "system", "name": "identity", "content": "你是 Emily"},
        {"role": "system", "name": "voice_card", "content": "emily voice"},
        {"role": "user", "content": "我昨天路过葡萄园。"},
    ]

    messages = build_group_messages(
        participants=[{"npcId": "Sophia"}, {"npcId": "Emily"}],
        active_npc_id="Sophia",
        participant_prompts={"sophia": sophia_card, "emily": emily_card},
        strategy="multi_turn",
        turn_count=3,
        player_message="我昨天路过葡萄园。",
    )

    contents = [item["content"] for item in messages]
    # 两个角色卡都是私聊同源内容，且玩家输入只追加一次
    assert "你是 Sophia" in contents
    assert "你是 Emily" in contents
    assert [item["role"] for item in messages].count("user") == 1
    assert messages[-1] == {"role": "user", "content": "我昨天路过葡萄园。"}
    scene = next(item for item in messages if item.get("name") == "group_scene")
    instruction = json.loads(scene["content"])["instruction"]
    assert "覆盖角色卡里“只输出当前 NPC 的对白”" in instruction
    assert "整段至少出现一次真正的来回" in instruction


def test_group_messages_turn_based_only_uses_the_active_speaker_card() -> None:
    from stardew_ai_bridge.group_conversation import build_group_messages

    sophia_card = [{"role": "system", "name": "identity", "content": "你是 Sophia"}]
    emily_card = [{"role": "system", "name": "identity", "content": "你是 Emily"}]

    messages = build_group_messages(
        participants=[{"npcId": "Sophia"}, {"npcId": "Emily"}],
        active_npc_id="Emily",
        participant_prompts={"sophia": sophia_card, "emily": emily_card},
        strategy="turn_based",
        player_message="晚上好。",
    )

    contents = [item["content"] for item in messages]
    assert "你是 Emily" in contents
    assert "你是 Sophia" not in contents


def test_group_messages_fall_back_when_no_role_card_is_available() -> None:
    from stardew_ai_bridge.group_conversation import build_group_messages

    messages = build_group_messages(
        participants=[{"npcId": "Sophia"}],
        active_npc_id="Sophia",
        participant_prompts=None,
        strategy="fanout",
        player_message="嗨。",
    )

    scene = next(item for item in messages if item.get("name") == "group_scene")
    assert "当前策略是 fanout" in json.loads(scene["content"])["instruction"]
    assert messages[-1]["role"] == "user"


def test_multi_turn_retries_once_when_the_reply_is_not_valid_json() -> None:
    provider = RecordingProvider(
        [
            "这不是 JSON，我先解释一下——",
            json.dumps(
                {"turns": [{"speakerNpcId": "Abigail", "content": "最近在练琴。"}]},
                ensure_ascii=False,
            ),
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn"))

    assert [turn.speaker_npc_id for turn in result.turns] == ["Abigail"]
    assert len(provider.requests) == 2
    assert result.provider_errors == []
    repair_messages = provider.requests[1][1]
    assert any(
        item["role"] == "system" and "JSON" in item["content"] for item in repair_messages
    )


def test_multi_turn_gives_up_after_a_single_retry() -> None:
    provider = RecordingProvider(["坏输出", "还是坏输出"])

    result = _service(provider).generate(_group_request("multi_turn"))

    assert result.turns == []
    assert result.provider_errors
    assert len(provider.requests) == 2


def test_multi_turn_scene_card_asks_for_at_least_one_npc_to_npc_reply() -> None:
    from stardew_ai_bridge.group_conversation import build_group_messages

    messages = build_group_messages(
        participants=[{"npcId": "Abigail"}, {"npcId": "Sebastian"}, {"npcId": "Sophia"}],
        active_npc_id="Abigail",
        participant_prompts={},
        strategy="multi_turn",
        turn_count=4,
        player_message="我想做一份晚上的歌单。",
    )
    instruction = json.loads(
        next(item for item in messages if item.get("name") == "group_scene")["content"]
    )["instruction"]

    assert "不必每条都严丝合缝地对上" in instruction
    assert "几个人各给一条建议、各说各的近况都很正常" in instruction
    # 接话可以不强求，但“每个人都有机会开口”这条底线要保住
    assert "不要让一个人把话说完" in instruction
    assert "两个人里不要只有一个人说话" in instruction
    assert "至少有一条对白是在回应名单里的另一个 NPC" not in instruction


def test_multi_turn_scene_card_states_group_specific_dialogue_rules() -> None:
    from stardew_ai_bridge.group_conversation import build_group_messages

    messages = build_group_messages(
        participants=[{"npcId": "Sophia"}, {"npcId": "Emily"}],
        active_npc_id="Sophia",
        participant_prompts={
            "sophia": [{"role": "system", "name": "identity", "content": "你是 Sophia"}],
            "emily": [{"role": "system", "name": "identity", "content": "你是 Emily"}],
        },
        strategy="multi_turn",
        turn_count=3,
        player_message="我昨天路过葡萄园。",
    )
    scene = next(item for item in messages if item.get("name") == "group_scene")
    instruction = json.loads(scene["content"])["instruction"]

    # 自然节奏：反“轮流汇报”的机械感，优先于格式要求
    assert "像几个熟人同时在群里说话" in instruction
    assert "不要写成轮流做任务汇报" in instruction
    assert "自然节奏优先于任何格式要求" in instruction
    assert "长度要参差" in instruction
    assert "允许只是附和、追问、吐槽" in instruction
    assert "不需要推进话题" in instruction
    assert "不要每条都以总结、感悟或小道理收尾" in instruction
    assert "节奏示例" in instruction
    # 节奏要求不能被旧的“每条都必须推进”约束抵消
    assert "每个回合都要带来新的信息" not in instruction
    assert "必须接住上一条" not in instruction
    # 保留的硬约束
    assert "第一个发言的人先接玩家" in instruction
    assert "整段至少出现一次真正的来回" in instruction
    # 事实一致性：不能把人数说错，也不能议论别人却不给对方回合
    assert "人数必须与名单一致" in instruction
    assert "只有两个别人就说“你们俩”" in instruction
    assert "不能只被别人议论却没有自己的回合" in instruction
    # 当面说话用第二人称，不要叫名字或用第三人称
    assert "对名单里某个人说话时直接用“你”" in instruction
    assert "不要当面叫他的名字或用第三人称" in instruction
    # addressedTo 必须与这句话的人称一致：对玩家说、只提到某人时留空
    assert "addressedTo 要和这句话的人称对上" in instruction
    assert "就留空数组" in instruction
    assert "addressedTo 只能填这条对白真正在回应或递给的人" in instruction


def test_multi_turn_scene_card_keeps_address_whitelist_rule() -> None:
    from stardew_ai_bridge.group_conversation import build_group_messages

    messages = build_group_messages(
        participants=[{"npcId": "Sophia"}, {"npcId": "Emily"}],
        active_npc_id="Sophia",
        participant_prompts={},
        strategy="multi_turn",
        turn_count=3,
        player_message="我昨天路过葡萄园。",
    )
    scene = next(item for item in messages if item.get("name") == "group_scene")
    instruction = json.loads(scene["content"])["instruction"]

    assert "只能填名单内的参与者 ID" in instruction
    assert "不能替 Emily 发言" not in instruction  # multi_turn 允许名单内互相接话


def test_multi_turn_reply_drops_addressed_to_targets_outside_the_roster() -> None:
    turns = parse_multi_turn_reply(
        json.dumps(
            {
                "turns": [
                    {
                        "speakerNpcId": "Sophia",
                        "content": "葡萄园的颜色确实让人停一下。",
                        "addressedTo": ["player", "you"],
                    },
                    {
                        "speakerNpcId": "Emily",
                        "content": "跟旧布上的紫调很搭。",
                        "addressedTo": ["sophia", "Sophia", "outsider"],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        participant_ids={"Sophia", "Emily"},
        expected_turn_count=3,
    )

    # 回应玩家时留空；名单内目标保留规范写法并去重。
    assert turns[0].addressed_to == []
    assert turns[1].addressed_to == ["Sophia"]


def test_multi_turn_scene_card_states_where_address_may_point() -> None:
    from stardew_ai_bridge.group_conversation import build_group_messages

    messages = build_group_messages(
        participants=[{"npcId": "Sophia"}, {"npcId": "Emily"}],
        active_npc_id="Sophia",
        participant_prompts={},
        strategy="multi_turn",
        turn_count=3,
        player_message="我昨天路过葡萄园。",
    )
    instruction = json.loads(
        next(item for item in messages if item.get("name") == "group_scene")["content"]
    )["instruction"]

    assert "回应玩家时留空数组" in instruction
    assert "不要写 player、you 之类的代称" in instruction


def test_group_prompt_marks_invitation_as_non_canonical_guidance() -> None:
    request = GroupDialogueRequest.model_validate(
        {
            "message": "你们怎么看？",
            "provider": "fake",
            "strategy": "turn_based",
            "channel": "remote",
            "participants": [
                {"npcId": "Abigail", "displayName": "Abigail"},
                {"npcId": "Emily", "displayName": "Emily"},
            ],
            "invitationTopic": "奇怪的矿石",
            "invitationGuidance": "这是玩家选择的话题方向，不是 NPC 已确认的事实。",
        }
    )

    prompt = build_group_prompt(
        active_npc_id="Abigail",
        participants=request.participants,
        shared_game_state=request.game_state,
        relationship_world=request.relationship_world,
        recent_facts=request.recent_facts,
        public_history=[item.model_dump(by_alias=True) for item in request.history],
        player_message=request.message,
        strategy=request.strategy,
        invitation_topic=request.invitation_topic,
        invitation_guidance=request.invitation_guidance,
    )
    rendered = json.dumps(prompt, ensure_ascii=False)

    assert "奇怪的矿石" in rendered
    assert "不是 NPC 已确认的事实" in rendered


def test_group_response_parser_rejects_unknown_speaker() -> None:
    with pytest.raises(GroupResponseError, match="未知发言人"):
        parse_multi_turn_reply(
            '{"turns":[{"speakerNpcId":"Lewis","content":"不在名单里"}]}',
            participant_ids={"Abigail", "Emily"},
            expected_turn_count=2,
        )


def test_fanout_calls_each_participant_once_and_returns_all_public_turns() -> None:
    provider = RecordingProvider(["Abigail 的回复", "Emily 的回复"])

    result = _service(provider).generate(_group_request("fanout"))

    assert result.provider_calls == 2
    assert [turn.speaker_npc_id for turn in result.turns] == ["Abigail", "Emily"]
    assert [request.npc_id for request, _ in provider.requests] == ["Abigail", "Emily"]


def test_turn_based_calls_only_active_speaker_once() -> None:
    provider = RecordingProvider(["Abigail 的回复"])

    result = _service(provider).generate(_group_request("turn_based"))

    assert result.provider_calls == 1
    assert [turn.speaker_npc_id for turn in result.turns] == ["Abigail"]
    assert provider.requests[0][0].npc_id == "Abigail"


def test_turn_based_preserves_active_speaker_completed_event_ids() -> None:
    provider = RecordingProvider(["Abigail 的回复"])

    result = _service(provider).generate(
        _group_request(
            "turn_based",
            gameState={
                "npcId": "Abigail",
                "completedEventIds": ["384882"],
            },
        )
    )

    assert result.fallback is False
    state = provider.requests[0][0].game_state
    assert state is not None
    assert state.completed_event_ids == ["384882"]


def test_multi_turn_uses_one_call_and_validates_each_returned_speaker() -> None:
    provider = RecordingProvider(
        [
            json.dumps(
                {
                    "turns": [
                        {"speakerNpcId": "Abigail", "content": "我最近在练琴。"},
                        {"speakerNpcId": "Emily", "content": "我在整理布料。"},
                    ]
                },
                ensure_ascii=False,
            )
        ]
    )

    result = _service(provider).generate(_group_request("multi_turn"))

    assert result.provider_calls == 1
    assert [turn.speaker_npc_id for turn in result.turns] == ["Abigail", "Emily"]
    assert provider.requests[0][0].npc_id == "Abigail"


def test_provider_fallback_returns_group_error_without_partial_fake_success() -> None:
    class FailingProvider:
        name = "recording"

        def generate(self, request, *, messages=None):  # type: ignore[no-untyped-def]
            raise RuntimeError("simulated provider failure")

    result = _service(FailingProvider()).generate(_group_request("turn_based"))

    assert result.provider_calls == 1
    assert result.fallback is True
    assert result.fallback_count == 1
    assert result.turns == []
    assert result.provider_errors


def test_fake_provider_emits_valid_multi_turn_demo_payload() -> None:
    request = DialogueTestRequest.model_validate(
        {
            "npcId": "Abigail",
            "message": "你们最近都在忙什么？",
            "provider": "fake",
            "groupStrategy": "multi_turn",
            "groupParticipantIds": ["Abigail", "Emily"],
        }
    )

    result = FakeProvider().generate(request)
    turns = parse_multi_turn_reply(
        result.reply,
        participant_ids={"Abigail", "Emily"},
        expected_turn_count=2,
    )

    assert [turn.speaker_npc_id for turn in turns] == ["Abigail", "Emily"]


def test_fake_provider_does_not_echo_unknown_group_identity() -> None:
    request = DialogueTestRequest.model_validate(
        {
            "npcId": "UnknownNpc",
            "message": "测试",
            "provider": "fake",
            "groupStrategy": "multi_turn",
            "groupParticipantIds": ["UnknownNpc", "Emily"],
        }
    )

    result = FakeProvider().generate(request)

    assert "UnknownNpc" not in result.reply
    assert '"speakerNpcId": "Emily"' in result.reply


def test_group_case_catalog_builds_same_request_for_all_three_strategies() -> None:
    cases = group_case_catalog()

    assert len(cases) >= 4
    assert {case["caseId"] for case in cases} >= {
        "group-abigail-emily-daily",
        "group-alex-sebastian-relationship",
        "group-wizard-sophia-research",
    }

    for case in cases:
        payloads = [
            comparable_group_payload(case, strategy)
            for strategy in ("fanout", "turn_based", "multi_turn")
        ]
        requests = [GroupDialogueRequest.model_validate(payload) for payload in payloads]
        assert {request.strategy for request in requests} == {
            "fanout",
            "turn_based",
            "multi_turn",
        }
        assert all(request.channel == "remote" for request in requests)
        assert all(len(request.participants) in {2, 3} for request in requests)
        assert [request.message for request in requests] == [case["message"]] * 3

        base = {key: value for key, value in payloads[0].items() if key != "strategy"}
        assert all(
            {key: value for key, value in payload.items() if key != "strategy"}
            == base
            for payload in payloads[1:]
        )


def test_group_case_catalog_includes_addressed_and_unaddressed_public_history() -> None:
    cases = group_case_catalog()
    history = next(
        case["history"]
        for case in cases
        if case["caseId"] == "group-abigail-emily-daily"
    )

    assert any(item["addressedTo"] for item in history)
    assert any(not item["addressedTo"] for item in history)


def _multi_turn_reply_with_memory(memory: object, *, turns: object | None = None) -> str:
    payload: dict[str, object] = {
        "turns": turns
        if turns is not None
        else [
            {
                "speakerNpcId": "Abigail",
                "content": "我最近在鼓捣游戏里那个新 boss。",
                "addressedTo": ["Emily"],
            }
        ],
        "memory": memory,
    }
    return json.dumps(payload, ensure_ascii=False)


def test_parse_multi_turn_payload_returns_turns_and_memory_highlights() -> None:
    turns, memory = parse_multi_turn_payload(
        _multi_turn_reply_with_memory(["玩家下周要交一份报告。"]),
        participant_ids={"Abigail", "Emily"},
        expected_turn_count=2,
    )

    assert [turn.speaker_npc_id for turn in turns] == ["Abigail"]
    assert turns[0].addressed_to == ["Emily"]
    assert memory == ["玩家下周要交一份报告。"]


def test_parse_multi_turn_payload_without_memory_field_returns_no_highlights() -> None:
    reply = json.dumps(
        {
            "turns": [
                {
                    "speakerNpcId": "Abigail",
                    "content": "我们仨凑一张还挺乱的。",
                }
            ]
        },
        ensure_ascii=False,
    )

    turns, memory = parse_multi_turn_payload(
        reply,
        participant_ids={"Abigail", "Emily"},
        expected_turn_count=2,
    )

    assert len(turns) == 1
    assert memory == []


@pytest.mark.parametrize("memory", ["玩家下周要交一份报告。", {"fact": "报告"}, 42, None])
def test_parse_multi_turn_payload_ignores_non_list_memory(memory: object) -> None:
    _, highlights = parse_multi_turn_payload(
        _multi_turn_reply_with_memory(memory),
        participant_ids={"Abigail", "Emily"},
        expected_turn_count=2,
    )

    assert highlights == []


def test_parse_multi_turn_payload_drops_unusable_memory_entries() -> None:
    _, highlights = parse_multi_turn_payload(
        _multi_turn_reply_with_memory(
            [
                "  ",
                123,
                None,
                "超" * 200,
                " 玩家下周要交一份报告。 ",
                "玩家下周要交一份报告。",
            ]
        ),
        participant_ids={"Abigail", "Emily"},
        expected_turn_count=2,
    )

    # 空串、非字符串、超过 160 字与去空白后的重复项都不进长期记忆。
    assert highlights == ["玩家下周要交一份报告。"]


def test_parse_multi_turn_payload_caps_memory_highlights_at_three() -> None:
    _, highlights = parse_multi_turn_payload(
        _multi_turn_reply_with_memory(
            ["第一条约定。", "第二条约定。", "第三条约定。", "第四条约定。"]
        ),
        participant_ids={"Abigail", "Emily"},
        expected_turn_count=2,
    )

    assert highlights == ["第一条约定。", "第二条约定。", "第三条约定。"]


def test_parse_multi_turn_payload_still_rejects_invalid_turns_when_memory_present() -> None:
    with pytest.raises(GroupResponseError):
        parse_multi_turn_payload(
            _multi_turn_reply_with_memory(
                ["玩家下周要交一份报告。"],
                turns=[
                    {
                        "speakerNpcId": "Sebastian",
                        "content": "不在名单里的人不该出现。",
                    }
                ],
            ),
            participant_ids={"Abigail", "Emily"},
            expected_turn_count=2,
        )


def test_parse_multi_turn_reply_stays_a_turns_only_entry_point() -> None:
    turns = parse_multi_turn_reply(
        _multi_turn_reply_with_memory(["玩家下周要交一份报告。"]),
        participant_ids={"Abigail", "Emily"},
        expected_turn_count=2,
    )

    # 兼容入口只回回合，长期记忆候选走 parse_multi_turn_payload。
    assert isinstance(turns, list)
    assert [turn.speaker_npc_id for turn in turns] == ["Abigail"]


def test_multi_turn_service_exposes_memory_highlights_on_the_response() -> None:
    provider = RecordingProvider(
        [_multi_turn_reply_with_memory(["玩家下周要交一份报告。"])]
    )

    response = _service(provider).generate(_group_request("multi_turn"))

    assert response.fallback is False
    assert [turn.speaker_npc_id for turn in response.turns] == ["Abigail"]
    assert response.memory_highlights == ["玩家下周要交一份报告。"]


def test_multi_turn_service_keeps_memory_from_the_retry_that_succeeded() -> None:
    provider = RecordingProvider(
        [
            "我最近在鼓捣游戏里那个新 boss。",  # 不是 JSON，触发一次重试
            _multi_turn_reply_with_memory(["玩家答应周末去葡萄园。"]),
        ]
    )

    response = _service(provider).generate(_group_request("multi_turn"))

    assert [turn.speaker_npc_id for turn in response.turns] == ["Abigail"]
    assert response.memory_highlights == ["玩家答应周末去葡萄园。"]


def test_multi_turn_service_without_memory_returns_empty_highlights() -> None:
    provider = RecordingProvider(
        [
            json.dumps(
                {
                    "turns": [
                        {
                            "speakerNpcId": "Abigail",
                            "content": "哪一部分？",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        ]
    )

    response = _service(provider).generate(_group_request("multi_turn"))

    # 闲聊不该被写进长期记忆。
    assert response.memory_highlights == []


def test_non_multi_turn_strategies_never_report_memory_highlights() -> None:
    provider = RecordingProvider(
        [
            _multi_turn_reply_with_memory(["玩家下周要交一份报告。"]),
            _multi_turn_reply_with_memory(["玩家下周要交一份报告。"]),
        ]
    )

    response = _service(provider).generate(_group_request("fanout"))

    assert response.memory_highlights == []


def _three_participant_reply() -> str:
    return json.dumps(
        {
            "turns": [
                {"speakerNpcId": "Abigail", "content": "我会放点吵的。"},
                {"speakerNpcId": "Sebastian", "content": "那我挑安静的。"},
                {"speakerNpcId": "Sophia", "content": "我可以两边都听一点。"},
            ]
        },
        ensure_ascii=False,
    )


_THREE_PARTICIPANTS = [
    {"npcId": "Abigail", "displayName": "Abigail"},
    {"npcId": "Sebastian", "displayName": "Sebastian"},
    {"npcId": "Sophia", "displayName": "Sophia"},
]


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
def test_turn_budget_falls_back_to_the_roster_size(
    turn_count: int | None, participant_count: int, expected: int
) -> None:
    assert turn_budget(turn_count, participant_count) == expected


def test_multi_turn_without_explicit_turn_count_covers_every_participant() -> None:
    provider = RecordingProvider([_three_participant_reply()])

    response = _service(provider).generate(
        _group_request(
            "multi_turn",
            participants=_THREE_PARTICIPANTS,
            turnCount=None,
        )
    )

    # 3 人场不给满 3 个回合就必然有人整场不开口。
    assert [turn.speaker_npc_id for turn in response.turns] == [
        "Abigail",
        "Sebastian",
        "Sophia",
    ]
    _, messages = provider.requests[0]
    prompt = json.dumps(messages, ensure_ascii=False)
    assert "最多输出 3 个公开回合" in prompt


def test_explicit_turn_count_still_wins_over_the_roster_size() -> None:
    provider = RecordingProvider(
        [
            json.dumps(
                {
                    "turns": [
                        {"speakerNpcId": "Abigail", "content": "我会放点吵的。"},
                        {"speakerNpcId": "Sebastian", "content": "那我挑安静的。"},
                    ]
                },
                ensure_ascii=False,
            )
        ]
    )

    response = _service(provider).generate(
        _group_request("multi_turn", participants=_THREE_PARTICIPANTS, turnCount=2)
    )

    assert len(response.turns) == 2
    _, messages = provider.requests[0]
    assert "最多输出 2 个公开回合" in json.dumps(messages, ensure_ascii=False)
