from __future__ import annotations

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

    _strip_item_id = field_validator("item_id", mode="before")(_strip_text)
    _strip_display_name = field_validator("display_name", mode="before")(
        _strip_text
    )
    _strip_category = field_validator("category", mode="before")(_strip_text)


class ProviderUsage(ApiModel):
    """Provider 返回的标准化 token 用量；字段缺失时保留为 None。"""

    input_tokens: int | None = Field(default=None, alias="inputTokens", ge=0)
    output_tokens: int | None = Field(default=None, alias="outputTokens", ge=0)
    total_tokens: int | None = Field(default=None, alias="totalTokens", ge=0)


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
    channel: Literal["remote", "face_to_face"] | None = None
    item_context: ItemConversationContext | None = Field(
        default=None,
        alias="itemContext",
    )

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

    _strip_reply = field_validator("reply", mode="before")(_strip_text)
    _strip_provider = field_validator("provider", mode="before")(_strip_text)


class DialogueResponse(ApiModel):
    reply: str = Field(min_length=1, max_length=4000)
    provider: str = Field(min_length=1, max_length=50)
    fallback: bool = False
    latency_ms: int = Field(alias="latencyMs", ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    usage: ProviderUsage | None = None

    _strip_reply = field_validator("reply", mode="before")(_strip_text)
    _strip_provider = field_validator("provider", mode="before")(_strip_text)


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    provider: str = Field(min_length=1, max_length=50)

    _strip_provider = field_validator("provider", mode="before")(_strip_text)
