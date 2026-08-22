from __future__ import annotations

import os
from dataclasses import dataclass, field


def _first_env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _env_float(*names: str, default: float) -> float:
    value = _first_env(*names)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _env_bool(*names: str, default: bool) -> bool:
    value = _first_env(*names)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProviderSettings:
    """单个 OpenAI-compatible Provider 的本机配置。"""

    name: str = "provider"
    url: str | None = None
    model: str = ""
    api_key: str | None = None
    timeout: float = 10.0
    enabled: bool = True

    @property
    def base_url(self) -> str | None:
        """兼容常见的 base_url 命名。"""
        return self.url

    @classmethod
    def from_env(
        cls,
        prefix: str,
        *,
        name: str,
        default_timeout: float = 10.0,
    ) -> "ProviderSettings":
        url = _first_env(
            f"{prefix}_URL",
            f"{prefix}_BASE_URL",
        )
        return cls(
            name=name,
            url=url,
            model=_first_env(f"{prefix}_MODEL", default="") or "",
            api_key=_first_env(f"{prefix}_API_KEY"),
            timeout=_env_float(f"{prefix}_TIMEOUT", default=default_timeout),
            enabled=_env_bool(f"{prefix}_ENABLED", default=url is not None),
        )


@dataclass(frozen=True)
class BridgeSettings:
    """Bridge 路由配置，默认不启用云端 Provider。"""

    local: ProviderSettings = field(
        default_factory=lambda: ProviderSettings(name="local")
    )
    cloud: ProviderSettings = field(
        default_factory=lambda: ProviderSettings(name="cloud", enabled=False)
    )
    cloud_enabled: bool = False
    fallback_reply: str = "Rasmodia：暂时没有合适的回复，请稍后再试。"

    @property
    def local_provider(self) -> ProviderSettings:
        return self.local

    @property
    def cloud_provider(self) -> ProviderSettings:
        return self.cloud

    @classmethod
    def from_env(cls) -> "BridgeSettings":
        local = ProviderSettings.from_env(
            "BRIDGE_LOCAL",
            name="local",
            default_timeout=5.0,
        )
        cloud = ProviderSettings.from_env(
            "BRIDGE_CLOUD",
            name="cloud",
            default_timeout=15.0,
        )
        return cls(
            local=local,
            cloud=cloud,
            cloud_enabled=_env_bool("BRIDGE_CLOUD_ENABLED", default=False),
            fallback_reply=(
                _first_env("BRIDGE_FALLBACK_REPLY", default=cls.fallback_reply)
                or cls.fallback_reply
            ),
        )
