from __future__ import annotations

from .config import DEFAULT_FALLBACK_REPLY
from .models import DialogueTestRequest, ProviderResult


class FallbackProvider:
    """所有上游 Provider 都不可用时返回的预设回复。"""

    # 默认文案来自 config 的单一来源，别在这里再写一份字面量
    # （2026-09-20 语义层审计 P3 第 47 条）。
    def __init__(self, reply: str = DEFAULT_FALLBACK_REPLY) -> None:
        self.reply = reply

    @property
    def name(self) -> str:
        return "fallback"

    def generate(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        del messages
        return ProviderResult(
            reply=self.reply,
            provider=self.name,
            fallback=True,
            latencyMs=0,
            warnings=[],
        )
