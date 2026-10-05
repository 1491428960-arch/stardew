from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .reply_scrub import scrub_reply


class ApiModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )


# `completedEventIds` 的权威上限，必须与 SMAPI 侧
# `GameStateCollector.MaxCompletedEventIds` 一致。
#
# 事件链门控（`relationship_gating.resolve_relationship_gate`）需要「已完成的**全部**
# 事件」才能正确判断事件链是否走完；一旦被截断，已完成的事件会被当成未完成，
# 已婚等既成关系就会被压回 `acquaintance`，prompt 里随之出现「不得使用爱称、
# 主动暧昧、事件后专属熟稔」（2026-09-21：用户存档 391 条被截到 128，
# 7 个配了事件门的角色里 6 个被压级）。
#
# `extra="forbid"` + 长度校验意味着**超限会直接 422**、退化成兜底回复，
# 所以这个数字两处必须同步改。
MAX_COMPLETED_EVENT_IDS = 512


def _strip_text(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("文本不能为空")
        return stripped
    return value


def _scrub_reply_text(value: object) -> object:
    """台词字段：先去空白，再清掉漏进来的拉丁／假名碎片。

    **只有"角色要说出口的话"才走这里** —— id、provider 名、mod 名这类字段
    不能清，它们本来就该是英文。

    成因已查实为**模型幻觉**（不是素材传染）：索菲亚的 310 条索引素材零污染，
    prompt 里也没有可照抄的英文台词。详见 `reply_scrub` 模块 docstring。
    在 8765 轮历史输出上只改动 0.57%，且没有碎片时**逐字返回**。
    """

    stripped = _strip_text(value)
    if isinstance(stripped, str):
        return scrub_reply(stripped)
    return stripped


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
    # 隐性知识（2026-10-04）：她在群聊里听别人说过的话，**不主动提就不唤醒**。
    # 走独立字段而不是并进 `recent_facts`——后者那张卡的指令会主动提，
    # 两个通道都送会让「不主动提」在「取最宽」下塌掉。
    # `prompts._build_context_core` 读的是这个键（`latentKnowledge` / `latent_knowledge`）。
    latent_knowledge: list[str] = Field(
        default_factory=list,
        alias="latentKnowledge",
        max_length=12,
    )

    _strip_npc_id = field_validator("npc_id", mode="before")(_strip_text)
    _strip_display_name = field_validator("display_name", mode="before")(
        _strip_text
    )


class ScheduleEntry(ApiModel):
    """当日日程里的一条（游戏端已本地化的地点名 + 原始时刻）。

    **刻意不做严格校验**：日程是可选增强，`ApiModel` 的 `extra="forbid"` 已经意味着
    「字段不认识就 422、整轮对话退化成兜底回复」。再把取值卡死，会让一条怪日程
    把一次正常对话打掉。所以这里只留防爆上限，合法性与范围判定交给
    `today_schedule.project_today_schedule`（它丢弃、不抛异常）。
    """

    time: int = 0
    location: str = Field(default="", max_length=200)


class NpcGameState(ApiModel):
    npc_id: str | None = Field(default=None, alias="npcId", max_length=100)
    display_name: str | None = Field(
        default=None,
        alias="displayName",
        max_length=100,
    )
    gender: str | None = Field(default=None, max_length=50)
    # ⚠ **本模型里唯一的玩家字段**（其余每个都是「关于这个 NPC 的」）。往这里继续堆
    # 玩家信息之前，先考虑是不是该另起一个容器。
    #
    # 唯一用途是**称呼**：`prompts.py` 把它渲染进 `mod_overlay` 卡、紧挨 `addressing`，
    # 让「按玩家性别：男「小伙子」，女「小姑娘」」这个条件有依据。它**不参与任何门控、
    # 分支或检索**。
    #
    # ⚠ **发布顺序**：`ApiModel` 是 `extra="forbid"`（本文件 :12）⇒ **新 DLL + 旧 Bridge
    # = 422 → 退化成兜底回复**。**必须先发 Bridge、再发 DLL**。反方向安全：旧 DLL 不发
    # 这个字段时这里是 `None`，与加这个字段之前的行为完全一致。
    player_gender: str | None = Field(
        default=None,
        alias="playerGender",
        max_length=50,
    )
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
    lives_with_player: bool | None = Field(
        default=None,
        alias="livesWithPlayer",
        description=(
            "该 NPC 是否与玩家同住（配偶或室友）。**只代表住处、不代表行踪**："
            "配偶 NPC 白天照样按日程外出；None 表示读不到（未知，不等于 False）。"
        ),
    )
    today_schedule: list[ScheduleEntry] = Field(
        default_factory=list,
        alias="todaySchedule",
        max_length=16,
        description=(
            "当日日程快照（游戏端 `NPC.Schedule` 的投影）。空列表 = 取不到日程，"
            "prompt 侧不发「今日安排」卡；失效方向是退化成没有日程，不是给错地点。"
        ),
    )
    completed_event_ids: list[str] = Field(
        default_factory=list,
        alias="completedEventIds",
        max_length=MAX_COMPLETED_EVENT_IDS,
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
    # 2026-10-04：关系的另一端。婚姻事实里就是 player。
    #
    # 没有它，`{"npcId": "Olivia", "relationType": "married"}` 是一句没有宾语的
    # 话：配偶的亲属（如 Olivia 的儿子 Victor）读到它，最多推出「我妈妈结婚了」，
    # 推不出新郎就是玩家。`_fold_relationship_edges` 负责从边的两端折叠出它。
    #
    # 可选：老存档 / 老 DLL 的 payload 不带这个键，不能因此 422。
    counterpart_npc_id: str | None = Field(
        default=None,
        alias="counterpartNpcId",
        max_length=100,
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




def _fold_relationship_edges(value: object) -> object:
    """把游戏端发来的**关系边**折叠成 Bridge 期望的**单对象事实**。

    2026-09-20 修（语义层审计）：C# 的 objectiveRelationships 发的是有向边
    （fromNpcId／toNpcId／strength／tension…），而 RelationshipFact 必填 npcId
    且 ApiModel 是 extra="forbid"——于是校验 422、请求退化成兜底回复。
    mediation／jealousy 有专门的形状转换，**唯独 objectiveRelationships 漏了**。
    """
    if not isinstance(value, Mapping):
        return value
    edges = value.get("objectiveRelationships")
    if not isinstance(edges, (list, tuple)) or not edges:
        return value
    folded: list[object] = []
    for edge in edges:
        if not isinstance(edge, Mapping):
            folded.append(edge)
            continue
        if "npcId" in edge:
            folded.append(edge)
            continue
        # 取边的“另一端”：玩家的边是 player→npc，所以优先 toNpcId。
        other = edge.get("toNpcId") or edge.get("fromNpcId")
        relation = edge.get("relationType")
        if not other or relation not in ("dating", "engaged", "married"):
            continue
        item = dict(edge)
        # 2026-10-04：**不要丢掉另一端**。原先这里无差别 pop 掉 fromNpcId/toNpcId，
        # 于是下游 `_public_marriage_views` 再也拿不到「和谁结的婚」，只能拿
        # `npcId` 单说「X 已婚」——一句没有宾语的话。
        #
        # 实机后果（用户原话：「维克托不知道他妈嫁给我了，这不对吧」）：Victor 知道
        # `Olivia 是我妈妈`，也知道 `Olivia 已婚`，但推不出新郎就是玩家。
        #
        # 保留成 `counterpartNpcId` 这个明确的领域名，而不是原样留着 from/to：
        # 下游只需要「另一端是谁」，留着方向反而容易读反。
        item.pop("fromNpcId", None)
        item.pop("toNpcId", None)
        item["npcId"] = other
        item["counterpartNpcId"] = (
            edge.get("fromNpcId") if other == edge.get("toNpcId") else edge.get("toNpcId")
        )
        folded.append(item)
    normalized = dict(value)
    normalized["objectiveRelationships"] = folded
    return normalized
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
        value = _fold_relationship_edges(value)

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
    # 2026-10-05：每位参与者**自己那份**私有上下文。
    #
    # 此前 `group_scene` 卡里只有无归属的单槽位 `recentFacts` / `relationshipWorld`，
    # 多人场里取谁的都是把别人的私事摊给全场看（见 `GroupDialogueMenu.cs` 里
    # 2026-09-22 写下的判据），所以生产端一直传 null。槽位下移到参与者身上后，
    # 归属由 Bridge 侧的 `participant_private_context` 卡声明，越界问题在卡内解决。
    #
    # 顶层同名字段保留，只为兼容还在发无归属那一份的旧版 DLL。
    relationship_world: RelationshipWorldContext | None = Field(
        default=None,
        alias="relationshipWorld",
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
    _strip_content = field_validator("content", mode="before")(_scrub_reply_text)


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
    # 跨窗口的"她最近说过什么"（2026-09-23）：Mod 端从**回看档案**取（比发送窗口长），
    # 只用于判定"这条素材整场谈过没有"与素材卡轮转去重，**不进模型看得到的消息**。
    #
    # 窗口：真机 `history` 被 `BridgeClient.MaxHistoryItems = 6` 封顶（约 3 轮），
    # 早期谈过的素材被挤出去就重新变回"没谈过"，于是池子前几条被反复建议 ——
    # 这正是用户说的「聊不长」。上限 40 与 `prompts` 侧的 `limit=40` 同源。
    #
    # ⚠️ **发布顺序**：`ApiModel` 是 `extra="forbid"` ⇒ 新 DLL + 旧 Bridge = 422
    # 退化成兜底回复。**必须先发 Bridge、再发 DLL**（反方向安全：旧 DLL 不发这个键
    # 时是空列表，与加字段之前的行为一致）。
    recent_replies: list[str] = Field(
        default_factory=list,
        alias="recentReplies",
        max_length=40,
    )
    game_state: NpcGameState | None = Field(default=None, alias="gameState")
    intent: Literal["chat", "topic", "item"] = "chat"
    # 隐性知识（2026-10-04）：她在**群聊里听别人说过**的话。需求原话
    # 「群聊记忆中别的 npc 说了什么能不能作为一个隐性的知识库这样的形式，
    # **我不主动提到就不唤醒**」。
    #
    # ⚠ 与 `recent_facts` 是**互斥的两条路**，不是包含关系：那张泛记忆卡带的是
    # 「把记忆自然用起来」的指令（会主动提），而这里的要求正好相反。两个通道都送
    # 会让模型同时收到两套打架的约束，项目实测过**「取最宽」**——同类约束有多个
    # 实例时跟最松的那个，「不主动提」会直接塌成「随便提」。
    #
    # 上限 12 与 C# 侧 `StoryStateStore.LatentKnowledge` 的封顶同源；
    # 卡片侧另有 `_MAX_LATENT_KNOWLEDGE_FACTS = 6` 做二次收口。
    #
    # ⚠️ **发布顺序**：`ApiModel` 是 `extra="forbid"` ⇒ 新 DLL + 旧 Bridge = 422
    # 退化成兜底回复。**必须先发 Bridge、再发 DLL**（反方向安全：旧 DLL 不发这个键
    # 时是空列表，与加字段之前的行为一致）。
    # 契约用例见 bridge/tests/test_latent_knowledge_contract.py。
    latent_knowledge: list[str] = Field(
        default_factory=list,
        alias="latentKnowledge",
        max_length=12,
    )
    # 2026-09-20（语义层审计 #46）：这里默认 False，而 C# 侧
    # `BridgeClient.CompactPrompt` 默认 true——**两处不同是刻意的，不要顺手统一**：
    #   · 游戏端（C#）默认走紧凑 prompt：线上往返省 token；
    #   · Bridge 侧默认完整 prompt：离线评测与脚本需要完整 gameState 才能评质量，
    #     而它们不传该字段时正好落到这个默认值。
    # 两个默认值服务不同调用方、从不同时生效（游戏端总是显式发送该字段）。
    # 改任一边前先确认「不传 compactPrompt 的调用方」会得到什么；
    # 护栏用例见 bridge/tests/test_cross_language_constants.py。
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
    # 2026-09-20（语义层审计 #29）：群聊回合上限此前有两个默认值，而且语义不同——
    # `GroupDialogueRequest.turn_count` 默认 None（「没指定，由服务按在场人数算」），
    # 这里默认 2（「就两个回合」）。同一个概念两个答案，谁也不知道该信谁。
    # 现在两处**统一为 None = 未指定**，具体额度只由
    # `group_conversation.turn_budget` 决定；群聊装配路径始终显式传值。
    group_turn_count: int | None = Field(default=None, alias="groupTurnCount", ge=1, le=4)

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

    @model_validator(mode="after")
    def _resolve_group_turn_count(self) -> "DialogueTestRequest":
        """把「未指定」在**构造期**折算成确定值，别让它以 `None` 漏到下游。

        2026-09-20（语义层审计 #29）：默认值由 2 改成 None 之后，
        `providers.py` 的 `[: request.group_turn_count]` 会变成
        `slice(stop=None)` —— Python **不报错**，而是切到末尾，是个静默的行为变更。
        这里按「演示回复跟随请求要的回合数」折算：没给名单（私聊请求）就没有
        隐式额度，保持 None；给了名单就取名单长度，仍然是 None 表示未指定。
        """

        if self.group_turn_count is None and self.group_participant_ids:
            self.group_turn_count = len(self.group_participant_ids)
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
            latentKnowledge=self.latent_knowledge,
        )


class ProviderResult(ApiModel):
    reply: str = Field(min_length=1, max_length=4000)
    provider: str = Field(min_length=1, max_length=50)
    fallback: bool = False
    latency_ms: int = Field(default=0, alias="latencyMs", ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    # 重试择优结果：重试版是否被采纳（`guard.retry_for_format_noise` 用
    # `_retry_quality_key` 比较过后设置）。`None` = 本次调用从未比较过
    # （没触发重试 / 重试抛异常 / 预算跳闸）。
    # ⚠ 为什么单独开字段而不塞进 `warnings`：`warnings` 是**诊断码**列表
    # （`_dedupe_warnings` 契约，且多处测试用 `==` 精确断言），
    # 混进统计量会让「这轮出了什么问题」与「补救有没有用」互相污染。
    # 动因：2026-09-28 审计发现全库 480 次 `response_affection_retry`
    # （占重试 54%）**无法判断是否白跑** —— 因为没有落盘择优结果。
    retry_improved: bool | None = Field(default=None, alias="retryImproved")

    # 2026-10-03：重试诊断量，与 `retry_improved` 同一动机（「补救有没有用」
    # 与「这轮出了什么问题」必须分开记），但回答的是另一个问题。
    #
    # `retry_kinds` = 本次调用**实际发起过**的重试类型，按时间顺序、保留重复。
    # `retry_issue`  = **最后一次判定出的** issue —— 它可能因为同类额度已用尽
    #                 或预算跳闸而**没有**真正发起重试。
    #
    # 两者存在的理由：`retry_for_format_noise` 的 `over_length` 分支排在
    # 判定链第 15 位（前 14 个都是 `issue is None and ...`），任一先命中就会被
    # 跳过，而 A2 每轮只处理一个问题。所以「这一轮回复超长」与「这一轮因长度重试」
    # 是两个不同的量，`retryCount` 单独存在时无法区分 —— 2026-10-03 的长度分析
    # 正是卡在这里。
    retry_kinds: list[str] | None = Field(default=None, alias="retryKinds")
    retry_issue: str | None = Field(default=None, alias="retryIssue")
    usage: ProviderUsage | None = None
    open_loop: OpenLoopSignal | None = Field(default=None, alias="openLoop")

    # ⚠ 这里**不清洗** —— `ProviderResult` 是 provider 的原样输出，
    # 中间还要过 `_retry_for_format_noise` 与 `response_guard`，
    # 让它们看到没被动过的文本更安全。清洗放在对外的 `DialogueResponse`。
    _strip_reply = field_validator("reply", mode="before")(_strip_text)
    _strip_provider = field_validator("provider", mode="before")(_strip_text)


class DialogueResponse(ApiModel):
    reply: str = Field(min_length=1, max_length=4000)
    provider: str = Field(min_length=1, max_length=50)
    fallback: bool = False
    latency_ms: int = Field(alias="latencyMs", ge=0)
    # `latencyMs` 是**端到端总耗时**（`app.test_dialogue` 用 `perf_counter` 量的），
    # 而这条路径上 `_retry_for_format_noise` 可能把同一个请求发两三次 ⇒
    # 同一个端点会出现 3s 和 21s 两种读数。把次数一起返回，慢才能归因：
    # 「3 次请求共 21s」和「1 次请求 21s」是两件完全不同的事。
    request_count: int = Field(default=1, alias="requestCount", ge=1)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    usage: ProviderUsage | None = None
    open_loop: OpenLoopSignal | None = Field(default=None, alias="openLoop")

    _strip_reply = field_validator("reply", mode="before")(_scrub_reply_text)
    _strip_provider = field_validator("provider", mode="before")(_strip_text)


class MorningMessagePlan(ApiModel):
    """一条「今天早上该由谁开口、说什么」。

    `opening` 是**已经写好的一句话**，游戏端拿到后直接写进聊天记录，
    **不经过模型**：预设内容的价值就在于它是人工定过的，
    让模型再复述一遍只会引入漂移。
    """

    npc_id: str = Field(alias="npcId", min_length=1, max_length=100)
    display_name: str = Field(alias="displayName", min_length=1, max_length=100)
    scenario_id: str = Field(alias="scenarioId", min_length=1, max_length=120)
    opening: str = Field(min_length=1, max_length=600)


class MorningPlanRequest(ApiModel):
    """游戏端在 `DayStarted` 时问「今天有没有人要主动开口」。

    ⚠ **本模型刻意保持极窄**：`ApiModel` 是 `extra="forbid"`，
    游戏端多送一个字段就是 422。所以**不要**往这里加「顺便带上
    gameState / 好感度 / 关系阶段」这类看起来很划算的东西——
    需要那些信息时另开端点，别把两个契约挤进一条请求。

    ## 2026-09-27 加 `recentEventIds` 的判据

    上面那条规矩没有变，`recentEventIds` 不是「顺便带上的上下文」：
    它和 `knownNpcIds` **同类** —— 都是这一个决策的直接输入
    （一个决定轮转候选池，一个决定今天有没有「事后」预设该发）。

    而且分端点做不到：游戏端得先问 A 拿事件信号、再问 B 拿计划，
    中间还可能跨天，两边看到的就不是同一个早上了。

    ⇒ 判据是：**只服务「今天该由谁开口」这一个决策的窄信号可以进；
    需要被 prompt 消费、或用于门控与检索的信息一律不进**（那些走
    `DialogueTestRequest.gameState`）。
    """

    day_index: int = Field(alias="dayIndex", ge=0, le=100000)
    known_npc_ids: list[str] = Field(
        default_factory=list,
        alias="knownNpcIds",
        max_length=80,
        description=(
            "玩家已经认识的角色（与 F8 名册同源：存档里有好感度记录的人）。"
            "**当前只用于轮转时的候选池**；节点预设不看它——"
            "节点是写死的调度，就算玩家还没见过那人也该照发。"
        ),
    )
    recent_event_ids: list[str] = Field(
        default_factory=list,
        alias="recentEventIds",
        max_length=32,
        description=(
            "**昨天**刚完成的剧情事件 ID，用于「事件后」预设。"
            "⚠ 游戏端负责只送昨天那一批：Bridge 无从判断新旧，"
            "`completedEventIds` 是累积全集且不含时间戳。"
            "事件 ID **大小写敏感**（与 NPC ID 忽略大小写的规则相反）。"
        ),
    )


class MorningPlanResponse(ApiModel):
    messages: list[MorningMessagePlan] = Field(default_factory=list, max_length=4)


class MorningScenarioView(ApiModel):
    """一条晨间预设的**完整文本**，给游戏外测试页审阅用（`/test/morning`）。

    与 `MorningMessagePlan` 的分工：那条是**发给游戏端**的（拿到就写进聊天记录，
    所以只需要 npcId / displayName / scenarioId / opening）；这条是**给人看的**，
    所以另外带上方向、边界、收尾与原话出处——审的就是这些措辞。

    ⚠ 它**不是**游戏端契约：改这里的字段不影响 DLL，也不受「Bridge 必须先于 DLL
    发布」那条约束（那条约束只针对 `DialogueTestRequest`）。
    """

    scenario_id: str = Field(alias="scenarioId", min_length=1, max_length=120)
    npc_id: str = Field(alias="npcId", min_length=1, max_length=100)
    display_name: str = Field(alias="displayName", min_length=1, max_length=100)
    # 绝对天数触发时的天数；其他触发方式下为 null（页面上显示「非按天」）。
    day_index: int | None = Field(default=None, alias="dayIndex")
    opening: str = Field(min_length=1, max_length=600)
    opening_source: str = Field(default="", alias="openingSource", max_length=1000)
    direction: str = Field(default="", max_length=2000)
    boundaries: list[str] = Field(default_factory=list, max_length=50)
    closing_hook: str = Field(default="", alias="closingHook", max_length=1000)
    allowed_kinds: list[str] = Field(default_factory=list, alias="allowedKinds", max_length=20)


class MorningScenarioListResponse(ApiModel):
    scenarios: list[MorningScenarioView] = Field(default_factory=list, max_length=200)


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    provider: str = Field(min_length=1, max_length=50)

    _strip_provider = field_validator("provider", mode="before")(_strip_text)
