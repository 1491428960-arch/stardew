from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
import re


_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# 安全兜底文案的**唯一来源**（2026-09-20 语义层审计 P3 第 47 条）。
#
# 这条文案此前在四处逐字重复：这里（配置默认值）、`fallback.py` 的构造默认参数、
# `app.py` 的 `_SAFE_FALLBACK_REPLY`，以及 C# 侧 `BridgeClient.cs` 的离线兜底。
# 它们语义相同（上游全不可用时给玩家看的那句话）却各写一遍，改一处忘一处就会
# 出现「Bridge 兜底和游戏兜底不一样」的静默漂移。
#
# 跨语言那一份无法共享代码，只能靠测试锁住一致（见
# `bridge/tests/test_cross_language_constants.py`）。
# 2026-09-26：**不带任何角色名**。原值是「Rasmodia：暂时没有合适的回复，请稍后再试。」——
# 兜底不是任何一个角色的台词（哪个 NPC 都可能触发），署名一个具体角色会让玩家
# 以为那句话是法师在说话。改成括号形态，把它和角色台词在形状上分开。
DEFAULT_FALLBACK_REPLY = "（暂时没有合适的回复，请稍后再试。）"

_LOCAL_ENV_KEYS = frozenset(
    {
        "BRIDGE_DIALOGUE_SESSION_PATH",
        "BRIDGE_FALLBACK_REPLY",
        "BRIDGE_PROFILE_INDEX",
        "BRIDGE_CLOUD_ONLY",
        "BRIDGE_CLOUD_VERTEX_PROJECT",
        "BRIDGE_CLOUD_VERTEX_LOCATION",
        "BRIDGE_CLOUD_VERTEX_CREDENTIALS",
        *{
            f"BRIDGE_{provider}_{suffix}"
            for provider in ("LOCAL", "CLOUD")
            for suffix in (
                "URL",
                "BASE_URL",
                "MODEL",
                "API_KEY",
                "TIMEOUT",
                "ENABLED",
                "API_MODE",
                "TEMPERATURE",
            )
        },
    }
)
_ENV_ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")

_VERTEX_HOST = "https://aiplatform.googleapis.com"
_VERTEX_DEFAULT_LOCATION = "global"


def build_vertex_url(*, project: str, location: str = _VERTEX_DEFAULT_LOCATION) -> str:
    """构造 Vertex AI 的 OpenAI-compatible chat completions 端点。"""

    return (
        f"{_VERTEX_HOST}/v1/projects/{project}/locations/{location}"
        "/endpoints/openapi/chat/completions"
    )


def _parse_local_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_local_env(path: str | Path | None = None) -> None:
    """加载项目级本机配置，且不覆盖进程环境变量。"""

    env_path = Path(path) if path is not None else _PROJECT_ROOT / ".env.local"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_ASSIGNMENT.match(line)
        if match is None:
            continue
        name, raw_value = match.groups()
        if name not in _LOCAL_ENV_KEYS or name in os.environ:
            continue
        os.environ[name] = _parse_local_env_value(raw_value)


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


def _env_optional_float(*names: str) -> float | None:
    """读一个可选的浮点配置；**未设置返回 None**。

    ⚠ 不能复用 `_env_float` —— 它是 `parsed if parsed > 0 else default`，
    而 `temperature = 0` 恰恰是这里最有意义的取值（要求确定性采样），
    走那条路会被静默丢成默认值，配置看起来"设了"，实际等于没设。
    超出 OpenAI 兼容接口的合法区间 [0, 2] 也一律当未设置处理。
    """
    value = _first_env(*names)
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if parsed < 0 or parsed > 2:
        return None
    return parsed


@dataclass(frozen=True)
class ProviderSettings:
    """单个 OpenAI-compatible Provider 的本机配置。"""

    name: str = "provider"
    url: str | None = None
    model: str = ""
    api_key: str | None = None
    timeout: float = 10.0
    enabled: bool = True
    api_mode: str = "openai"
    vertex_project: str | None = None
    vertex_location: str | None = None
    #: 采样温度。**默认 None 表示"压根不发这个字段"**，与加它之前的行为逐字节一致。
    #: 2026-10-01 实测：同一 prompt 连发 5 次，默认温度下两两相似度中位数只有 0.222，
    #: 而 K=1/K=4 那次 198 轮对照的观测值是 0.203 —— **比纯噪音还小**，
    #: 所以那个 null 结果零信息量。设 0 能把一致性提到 0.403（+81%），
    #: 但仍远不到可复现 ⇒ 真正的降噪要靠多次采样取平均，不是靠这一项。
    temperature: float | None = None

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
        api_mode = (
            _first_env(f"{prefix}_API_MODE", default="openai") or "openai"
        ).lower()
        vertex_project = _first_env(f"{prefix}_VERTEX_PROJECT")
        vertex_location = _first_env(f"{prefix}_VERTEX_LOCATION")
        if url is None and api_mode == "vertex" and vertex_project:
            # Vertex 模式下 project/location 是唯一必需输入；显式 URL 仍然优先，
            # 便于临时指向本地网关做离线排查。
            url = build_vertex_url(
                project=vertex_project,
                location=vertex_location or _VERTEX_DEFAULT_LOCATION,
            )
        return cls(
            name=name,
            url=url,
            model=_first_env(f"{prefix}_MODEL", default="") or "",
            api_key=_first_env(f"{prefix}_API_KEY"),
            timeout=_env_float(f"{prefix}_TIMEOUT", default=default_timeout),
            enabled=_env_bool(f"{prefix}_ENABLED", default=url is not None),
            api_mode=api_mode,
            vertex_project=vertex_project,
            vertex_location=vertex_location,
            temperature=_env_optional_float(f"{prefix}_TEMPERATURE"),
        )


@dataclass(frozen=True)
class BridgeSettings:
    """Bridge 路由配置；cloud_only 用于正式运行时锁定云端自动路由。"""

    local: ProviderSettings = field(
        default_factory=lambda: ProviderSettings(name="local")
    )
    cloud: ProviderSettings = field(
        default_factory=lambda: ProviderSettings(name="cloud", enabled=False)
    )
    cloud_enabled: bool = False
    cloud_only: bool = False
    fallback_reply: str = DEFAULT_FALLBACK_REPLY
    profile_index_path: str | None = None

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
            default_timeout=45.0,
        )
        cloud = ProviderSettings.from_env(
            "BRIDGE_CLOUD",
            name="cloud",
            default_timeout=45.0,
        )
        return cls(
            local=local,
            cloud=cloud,
            cloud_enabled=_env_bool("BRIDGE_CLOUD_ENABLED", default=False),
            cloud_only=_env_bool("BRIDGE_CLOUD_ONLY", default=False),
            fallback_reply=(
                _first_env("BRIDGE_FALLBACK_REPLY", default=cls.fallback_reply)
                or cls.fallback_reply
            ),
            profile_index_path=_first_env("BRIDGE_PROFILE_INDEX"),
        )
