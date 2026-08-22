from __future__ import annotations

from abc import ABC, abstractmethod

from .models import DialogueTestRequest, ProviderResult


class Provider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """返回 Provider 的稳定标识。"""

    @abstractmethod
    def generate(self, request: DialogueTestRequest) -> ProviderResult:
        """根据一次测试请求生成结构化回复。"""


class FakeProvider(Provider):
    REPLY = "Rasmodia：你好，这是一条固定的 Fake Provider 测试回复。"

    @property
    def name(self) -> str:
        return "fake"

    def generate(self, request: DialogueTestRequest) -> ProviderResult:
        return ProviderResult(
            reply=self.REPLY,
            provider=self.name,
            fallback=False,
            latencyMs=0,
            warnings=[],
        )
