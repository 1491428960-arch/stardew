from __future__ import annotations

from .models import DialogueTestRequest, ProviderResult


class FallbackProvider:
    """所有上游 Provider 都不可用时返回的预设回复。"""

    def __init__(self, reply: str = "Rasmodia：暂时没有合适的回复，请稍后再试。") -> None:
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
