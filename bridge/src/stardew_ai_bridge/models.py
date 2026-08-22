from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    relationship: str | None = Field(default=None, max_length=100)
    source_mods: list[str] = Field(
        default_factory=list,
        alias="sourceMods",
        max_length=50,
    )
    warnings: list[str] = Field(default_factory=list, max_length=50)

    _strip_display_name = field_validator("display_name", mode="before")(
        _strip_text
    )


class DialogueTestRequest(ApiModel):
    npc_id: str = Field(alias="npcId", min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    provider: Literal["fake"] = "fake"
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

    _strip_npc_id = field_validator("npc_id", mode="before")(_strip_text)
    _strip_message = field_validator("message", mode="before")(_strip_text)
    _strip_display_name = field_validator("display_name", mode="before")(
        _strip_text
    )

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

    _strip_reply = field_validator("reply", mode="before")(_strip_text)
    _strip_provider = field_validator("provider", mode="before")(_strip_text)


class DialogueResponse(ApiModel):
    reply: str = Field(min_length=1, max_length=4000)
    provider: str = Field(min_length=1, max_length=50)
    fallback: bool = False
    latency_ms: int = Field(alias="latencyMs", ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=20)

    _strip_reply = field_validator("reply", mode="before")(_strip_text)
    _strip_provider = field_validator("provider", mode="before")(_strip_text)


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    provider: str = Field(min_length=1, max_length=50)

    _strip_provider = field_validator("provider", mode="before")(_strip_text)
