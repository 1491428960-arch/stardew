from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )


def _strip_text(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("文本不能为空")
        return stripped
    return value


def _strip_dialogue_message(value: object) -> object:
    """消息允许在 topic 意图下为空，普通消息由模型级校验拒绝空值。"""

    return value.strip() if isinstance(value, str) else value


def _strip_mapping_keys(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key.strip() if isinstance(key, str) else key: item
            for key, item in value.items()
        }
    return value


class NpcContext(ApiModel):
    npc_id: str = Field(alias="npcId", min_length=1, max_length=100)
    display_name: str | None = Field(
        default=None,
        alias="displayName",
        min_length=1,
        max_length=100,
    )
    source_mods: list[str] = Field(
        default_factory=list,
        alias="sourceMods",
        max_length=50,
    )
    recent_facts: list[str] = Field(
        default_factory=list,
        alias="recentFacts",
        max_length=50,
    )

    _strip_npc_id = field_validator("npc_id", mode="before")(_strip_text)
    _strip_display_name = field_validator("display_name", mode="before")(
        _strip_text
    )


class NpcGameState(ApiModel):
    npc_id: str | None = Field(default=None, alias="npcId", max_length=100)
    display_name: str | None = Field(
        default=None,
        alias="displayName",
        max_length=100,
    )
    gender: str | None = Field(default=None, max_length=50)
    season: str | None = Field(default=None, max_length=50)
    date: str | None = Field(default=None, max_length=100)
    weather: str | None = Field(default=None, max_length=100)
    time: int | None = None
    location: str | None = Field(default=None, max_length=200)
    friendship: int | None = None
    friendship_hearts: int | None = Field(
        default=None,
        alias="friendshipHearts",
        ge=0,
        le=14,
    )
    relationship: str | None = Field(default=None, max_length=100)
    marriage_status: str | None = Field(
        default=None,
        alias="marriageStatus",
        max_length=100,
    )
    children_count: int | None = Field(
        default=None,
        alias="childrenCount",
        ge=0,
        le=20,
    )
    completed_event_ids: list[str] = Field(
        default_factory=list,
        alias="completedEventIds",
        max_length=128,
    )
    source_mods: list[str] = Field(
        default_factory=list,
        alias="sourceMods",
        max_length=50,
    )
    warnings: list[str] = Field(default_factory=list, max_length=50)

    _strip_display_name = field_validator("display_name", mode="before")(
        _strip_text
    )


class ItemConversationContext(ApiModel):
    item_id: str = Field(alias="itemId", min_length=1, max_length=100)
    display_name: str = Field(
        alias="displayName",
        min_length=1,
        max_length=100,
    )
    category: str = Field(min_length=1, max_length=100)
    quality: int = Field(ge=0, le=4)
    action: Literal["display", "share", "gift"]
    gift_taste: int = Field(alias="giftTaste", ge=-10, le=10)
    item_kind: Literal["other", "food", "mineral", "artifact"] = Field(
        default="other",
        alias="itemKind",
    )
    consumes_item: bool = Field(default=False, alias="consumesItem")
    friendship_awarded: int = Field(
        default=0,
        alias="friendshipAwarded",
        ge=0,
        le=5,
    )
    special_interaction: Literal["none", "mineral_tasting"] = Field(
        default="none",
        alias="specialInteraction",
    )

    _strip_item_id = field_validator("item_id", mode="before")(_strip_text)
    _strip_display_name = field_validator("display_name", mode="before")(
        _strip_text
    )
    _strip_category = field_validator("category", mode="before")(_strip_text)


class RelationshipFact(ApiModel):
    npc_id: str = Field(alias="npcId", min_length=1, max_length=100)
    relation_type: Literal["dating", "engaged", "married"] = Field(
        alias="relationType"
    )
    started_on: str | None = Field(
        default=None,
        alias="startedOn",
        max_length=100,
    )
    public_event_id: str | None = Field(
        default=None,
        alias="publicEventId",
        max_length=160,
    )
    public_on: str | None = Field(
        default=None,
        alias="publicOn",
        max_length=100,
    )

    _strip_npc_id = field_validator("npc_id", mode="before")(_strip_text)


class RelationshipView(ApiModel):
    owner_npc_id: str = Field(alias="ownerNpcId", min_length=1, max_length=100)
    subject_npc_id: str = Field(alias="subjectNpcId", min_length=1, max_length=100)
    relation_type: Literal["dating", "engaged", "married"] = Field(
        alias="relationType"
    )
    visibility: Literal["known", "suspected", "unknown"]
    source: Literal[
        "none",
        "observation",
        "rumor",
        "direct_question",
        "player_statement",
        "wedding",
    ]
    observed_on: str | None = Field(
        default=None,
        alias="observedOn",
        max_length=100,
    )
    evidence: str | None = Field(default=None, max_length=240)

    _strip_owner_npc_id = field_validator("owner_npc_id", mode="before")(_strip_text)
    _strip_subject_npc_id = field_validator("subject_npc_id", mode="before")(
        _strip_text
    )


class MediationState(ApiModel):
    status: Literal["none", "offered", "active", "resolved"] = "none"
    outcome: Literal["accepted", "conditional", "not_ready"] | None = None
    next_step: str | None = Field(
        default=None,
        alias="nextStep",
        max_length=240,
    )


class JealousyState(ApiModel):
    active: bool = False
    trigger: Literal[
        "time",
        "companionship",
        "broken_promise",
        "comparison",
        "affection_imbalance",
    ] | None = None
    intensity: Literal["light", "moderate", "high"] | None = None
    need: str | None = Field(default=None, max_length=240)
    last_resolved_trigger: str | None = Field(
        default=None,
        alias="lastResolvedTrigger",
        max_length=80,
    )


class OpenLoop(ApiModel):
    loop_id: str = Field(alias="loopId", min_length=1, max_length=160)
    npc_id: str = Field(alias="npcId", min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=100)
    origin_channel: Literal["remote"] = Field(alias="originChannel")
    next_channel: Literal["face_to_face"] = Field(alias="nextChannel")
    status: Literal["open", "in_progress", "resolved", "cancelled"] = "open"
    short_summary: str = Field(alias="shortSummary", min_length=1, max_length=240)
    created_on: str = Field(alias="createdOn", min_length=1, max_length=100)

    _strip_loop_id = field_validator("loop_id", mode="before")(_strip_text)
    _strip_npc_id = field_validator("npc_id", mode="before")(_strip_text)
    _strip_topic = field_validator("topic", mode="before")(_strip_text)
    _strip_short_summary = field_validator("short_summary", mode="before")(
        _strip_text
    )
    _strip_created_on = field_validator("created_on", mode="before")(_strip_text)


class OpenLoopSignal(ApiModel):
    action: Literal["open", "continue", "resolve"]
    loop_id: str = Field(alias="loopId", min_length=1, max_length=160)
    topic: str | None = Field(default=None, max_length=100)
    short_summary: str | None = Field(
        default=None,
        alias="shortSummary",
        max_length=240,
    )

    _strip_loop_id = field_validator("loop_id", mode="before")(_strip_text)
    _strip_topic = field_validator("topic", mode="before")(_strip_text)
    _strip_short_summary = field_validator("short_summary", mode="before")(
        _strip_text
    )

    @model_validator(mode="after")
    def _validate_open_fields(self) -> "OpenLoopSignal":
        if self.action == "open" and (not self.topic or not self.short_summary):
            raise ValueError("open action requires topic and shortSummary")
        return self


class RelationshipWorldContext(ApiModel):
    objective_relationships: list[RelationshipFact] = Field(
        default_factory=list,
        alias="objectiveRelationships",
        max_length=20,
        description="玩家与 NPC 的客观关系；npcId 是玩家的关系对象，不是当前 NPC 的恋爱对象。",
    )
    views: list[RelationshipView] = Field(default_factory=list, max_length=80)
    acceptance_by_npc: dict[
        str, Literal["accepted", "conditional", "not_ready"]
    ] = Field(
        default_factory=dict,
        alias="acceptanceByNpc",
        max_length=20,
    )
    mediation_by_npc: dict[str, MediationState] = Field(
        default_factory=dict,
        alias="mediationByNpc",
        max_length=20,
    )
    jealousy_by_npc: dict[str, JealousyState] = Field(
        default_factory=dict,
        alias="jealousyByNpc",
        max_length=20,
    )
    open_loops: list[OpenLoop] = Field(
        default_factory=list,
        alias="openLoops",
        max_length=20,
    )

    _strip_acceptance_keys = field_validator(
        "acceptance_by_npc",
        mode="before",
    )(_strip_mapping_keys)

    @field_validator("mediation_by_npc", "jealousy_by_npc", mode="before")
    @classmethod
    def _strip_state_keys(cls, value: object) -> object:
        return _strip_mapping_keys(value)

    @model_validator(mode="before")
    @classmethod
    def _normalize_csharp_snapshot_shape(cls, value: object) -> object:
        """兼容游戏端按当前 NPC 发送的单对象关系快照。"""

        if not isinstance(value, Mapping):
            return value

        normalized = dict(value)
        for singular_key, plural_key in (
            ("mediation", "mediationByNpc"),
            ("jealousy", "jealousyByNpc"),
        ):
            if singular_key not in normalized:
                continue

            snapshot = normalized.pop(singular_key)
            if snapshot is None:
                continue
            if not isinstance(snapshot, Mapping):
                normalized[singular_key] = snapshot
                continue

            npc_id = snapshot.get("npcId")
            if not isinstance(npc_id, str) or not npc_id.strip():
                normalized[singular_key] = snapshot
                continue

            if plural_key not in normalized:
                normalized[plural_key] = {
                    npc_id.strip(): {
                        key: item
                        for key, item in snapshot.items()
                        if key != "npcId"
                    },
                }

        return normalized


class ProviderUsage(ApiModel):
    """Provider 返回的标准化 token 用量；字段缺失时保留为 None。"""

    input_tokens: int | None = Field(default=None, alias="inputTokens", ge=0)
    output_tokens: int | None = Field(default=None, alias="outputTokens", ge=0)
    total_tokens: int | None = Field(default=None, alias="totalTokens", ge=0)


class GroupParticipant(ApiModel):
    npc_id: str = Field(alias="npcId", min_length=1, max_length=100)
    display_name: str | None = Field(
        default=None,
        alias="displayName",
        min_length=1,
        max_length=100,
    )
    source_mods: list[str] = Field(
        default_factory=list,
        alias="sourceMods",
        max_length=50,
    )
    game_state: NpcGameState | None = Field(default=None, alias="gameState")

    _strip_npc_id = field_validator("npc_id", mode="before")(_strip_text)
    _strip_display_name = field_validator("display_name", mode="before")(
        _strip_text
    )


class GroupHistoryItem(ApiModel):
    speaker_type: Literal["player", "npc"] = Field(alias="speakerType")
    speaker_id: str = Field(alias="speakerId", min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=2000)
    addressed_to: list[str] = Field(
        default_factory=list,
        alias="addressedTo",
        max_length=3,
    )
    visibility: Literal["public"] = "public"

    _strip_speaker_id = field_validator("speaker_id", mode="before")(_strip_text)
    _strip_content = field_validator("content", mode="before")(_strip_text)


class GroupDialogueRequest(ApiModel):
    message: str = Field(default="", max_length=2000)
    provider: Literal["fake", "auto", "local", "cloud"] = "fake"
    strategy: Literal["fanout", "turn_based", "multi_turn"]
    channel: Literal["remote"] = "remote"
    participants: list[GroupParticipant] = Field(min_length=2, max_length=3)
    active_speaker_npc_id: str | None = Field(
        default=None,
        alias="activeSpeakerNpcId",
        max_length=100,
    )
    history: list[GroupHistoryItem] = Field(default_factory=list, max_length=40)
    turn_count: int | None = Field(default=None, alias="turnCount", ge=1, le=4)
    game_state: NpcGameState | None = Field(default=None, alias="gameState")
    recent_facts: list[str] = Field(
        default_factory=list,
        alias="recentFacts",
        max_length=50,
    )
    relationship_world: RelationshipWorldContext | None = Field(
        default=None,
        alias="relationshipWorld",
    )
    invitation_topic: str | None = Field(
        default=None,
        alias="invitationTopic",
        max_length=240,
    )
    invitation_guidance: str | None = Field(
        default=None,
        alias="invitationGuidance",
        max_length=500,
    )

    _strip_message = field_validator("message", mode="before")(
        _strip_dialogue_message
    )
    _strip_active_speaker = field_validator(
        "active_speaker_npc_id",
        mode="before",
    )(_strip_text)
    _strip_invitation_topic = field_validator(
        "invitation_topic",
        mode="before",
    )(_strip_text)
    _strip_invitation_guidance = field_validator(
        "invitation_guidance",
        mode="before",
    )(_strip_text)

    @model_validator(mode="after")
    def _validate_group_shape(self) -> "GroupDialogueRequest":
        participant_ids = [item.npc_id.casefold() for item in self.participants]
        if len(set(participant_ids)) != len(participant_ids):
            raise ValueError("参与者 NPC ID 不能重复")

        if self.active_speaker_npc_id and (
            self.active_speaker_npc_id.casefold() not in set(participant_ids)
        ):
            raise ValueError("activeSpeakerNpcId 必须属于参与者")

        participant_set = set(participant_ids)
        for item in self.history:
            if item.speaker_type == "npc" and item.speaker_id.casefold() not in participant_set:
                raise ValueError("历史中的 NPC 发言人必须属于参与者")

        # 消息为空**只有在历史也为空时**才是合法的「开场」：刚开一场群聊、
        # 玩家一句话都没说，由 NPC 自己起头（2026-09-20 用户反馈：
        # “预设的群聊由 NPC 开始话题吧，不然起不到引导玩家的作用”）。
        # 已经聊过还发空消息依然拒绝——那是无意义的请求，不是开场。
        if not self.message and self.history:
            raise ValueError("多人对话消息不能为空")
        return self


class GroupTurn(ApiModel):
    speaker_npc_id: str = Field(alias="speakerNpcId", min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=4000)
    addressed_to: list[str] = Field(
        default_factory=list,
        alias="addressedTo",
        max_length=3,
    )

    _strip_speaker_npc_id = field_validator("speaker_npc_id", mode="before")(
        _strip_text
    )
    _strip_content = field_validator("content", mode="before")(_strip_text)


class GroupDialogueResponse(ApiModel):
    strategy: Literal["fanout", "turn_based", "multi_turn"]
    channel: Literal["remote"] = "remote"
    provider: str = Field(min_length=1, max_length=50)
    fallback: bool = False
    turns: list[GroupTurn] = Field(default_factory=list, max_length=4)
    provider_calls: int = Field(alias="providerCalls", ge=0)
    provider_errors: list[str] = Field(
        default_factory=list,
        alias="providerErrors",
        max_length=20,
    )
    fallback_count: int = Field(default=0, alias="fallbackCount", ge=0)
    latency_ms: int = Field(default=0, alias="latencyMs", ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    usage: ProviderUsage | None = None
    # 群聊里“值得长期记住”的候选（事实、约定、承诺），由模型标出，闲聊不进这里。
    memory_highlights: list[str] = Field(
        default_factory=list,
        alias="memoryHighlights",
        max_length=3,
    )


class DialogueTestRequest(ApiModel):
    npc_id: str = Field(alias="npcId", min_length=1, max_length=100)
    message: str = Field(default="", max_length=2000)
    provider: Literal["fake", "auto", "local", "cloud"] = "fake"
    display_name: str | None = Field(
        default=None,
        alias="displayName",
        min_length=1,
        max_length=100,
    )
    source_mods: list[str] = Field(
        default_factory=list,
        alias="sourceMods",
        max_length=50,
    )
    recent_facts: list[str] = Field(
        default_factory=list,
        alias="recentFacts",
        max_length=50,
    )
    history: list[dict[str, object]] = Field(default_factory=list, max_length=50)
    game_state: NpcGameState | None = Field(default=None, alias="gameState")
    intent: Literal["chat", "topic", "item"] = "chat"
    compact_prompt: bool = Field(default=False, alias="compactPrompt")
    channel: Literal["remote", "face_to_face"] | None = None
    item_context: ItemConversationContext | None = Field(
        default=None,
        alias="itemContext",
    )
    relationship_world: RelationshipWorldContext | None = Field(
        default=None,
        alias="relationshipWorld",
    )
    group_strategy: Literal["fanout", "turn_based", "multi_turn"] | None = Field(
        default=None,
        alias="groupStrategy",
    )
    group_participant_ids: list[str] = Field(
        default_factory=list,
        alias="groupParticipantIds",
        max_length=3,
    )
    group_turn_count: int = Field(default=2, alias="groupTurnCount", ge=1, le=4)

    _strip_npc_id = field_validator("npc_id", mode="before")(_strip_text)
    _strip_message = field_validator("message", mode="before")(_strip_dialogue_message)
    _strip_display_name = field_validator("display_name", mode="before")(
        _strip_text
    )

    @model_validator(mode="after")
    def _validate_message_for_intent(self) -> "DialogueTestRequest":
        if self.intent != "topic" and not self.message:
            raise ValueError("消息不能为空")
        return self

    def context(self) -> NpcContext:
        return NpcContext(
            npcId=self.npc_id,
            displayName=self.display_name or (
                self.game_state.display_name if self.game_state else None
            ),
            sourceMods=self.source_mods or (
                self.game_state.source_mods if self.game_state else []
            ),
            recentFacts=self.recent_facts,
        )


class ProviderResult(ApiModel):
    reply: str = Field(min_length=1, max_length=4000)
    provider: str = Field(min_length=1, max_length=50)
    fallback: bool = False
    latency_ms: int = Field(default=0, alias="latencyMs", ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    usage: ProviderUsage | None = None
    open_loop: OpenLoopSignal | None = Field(default=None, alias="openLoop")

    _strip_reply = field_validator("reply", mode="before")(_strip_text)
    _strip_provider = field_validator("provider", mode="before")(_strip_text)


class DialogueResponse(ApiModel):
    reply: str = Field(min_length=1, max_length=4000)
    provider: str = Field(min_length=1, max_length=50)
    fallback: bool = False
    latency_ms: int = Field(alias="latencyMs", ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    usage: ProviderUsage | None = None
    open_loop: OpenLoopSignal | None = Field(default=None, alias="openLoop")

    _strip_reply = field_validator("reply", mode="before")(_strip_text)
    _strip_provider = field_validator("provider", mode="before")(_strip_text)


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    provider: str = Field(min_length=1, max_length=50)

    _strip_provider = field_validator("provider", mode="before")(_strip_text)
