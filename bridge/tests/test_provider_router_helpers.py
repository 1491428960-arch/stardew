"""`providers` 的四个小函数 + `speech` 的一个判定函数。

用**函数级覆盖率排序**挑出来的。其中两个值得单独说：

- **`_run_async`**：同步接口里跑协程。关键在于它**先探测有没有运行中的事件循环**——
  有的话把协程丢到单线程 executor 里跑，**而不是直接 `asyncio.run`**（那样会抛
  `RuntimeError: asyncio.run() cannot be called from a running event loop`）。
  这个隔离很容易在重构时被“简化”掉，所以下面专门有一条**在事件循环内调用**的测试。
- **`has_configured_upstream`**：决定路由器是否对外声称“有可用的上游”。它的布尔组合
  有四层（`cloud_only` → local → cloud_enabled → default_provider），值得穷举。
"""

from __future__ import annotations

import asyncio

import pytest

from stardew_ai_bridge.config import ProviderSettings
from stardew_ai_bridge.providers import (
    AdcAccessTokenSource,
    ProviderRouter,
    VertexOpenAICompatibleProvider,
    _run_async,
)
from stardew_ai_bridge.speech import _stage_conditioned_voice_sample

_SETTINGS = ProviderSettings(
    name="vertex",
    url="https://vertex.invalid/v1/chat/completions",
    model="gemini-x",
    api_key="",
    timeout=2.0,
)


class _Stub:
    """最小的 Provider 替身：路由器只把它当“存在”与“不存在”来用。"""

    name = "stub"

    def generate(self, request, *, messages=None):  # type: ignore[no-untyped-def]
        raise AssertionError("这个替身不该被真的调用")


# --- _run_async -------------------------------------------------------------


async def _coro(value: str = "ok") -> str:
    return value


def test_run_async_works_without_a_running_loop() -> None:
    assert _run_async(_coro()) == "ok"


def test_run_async_works_inside_a_running_loop() -> None:
    # 这是这条实现的核心价值：不能直接 asyncio.run，否则会抛 RuntimeError。
    async def outer() -> str:
        return _run_async(_coro())

    assert asyncio.run(outer()) == "ok"


def test_run_async_survives_repeated_calls_inside_a_loop() -> None:
    # 线程池方案要能重复使用，不能第二次就卡住或抛错。
    async def outer() -> tuple[str, str]:
        return _run_async(_coro("a")), _run_async(_coro("b"))

    assert asyncio.run(outer()) == ("a", "b")


def test_run_async_propagates_exceptions() -> None:
    async def boom() -> str:
        raise ValueError("坏了")

    with pytest.raises(ValueError):
        _run_async(boom())


def test_run_async_propagates_exceptions_inside_a_loop() -> None:
    async def outer() -> str:
        return _run_async(boom())

    async def boom() -> str:
        raise ValueError("坏了")

    with pytest.raises(ValueError):
        asyncio.run(outer())


# --- has_configured_upstream ------------------------------------------------


def test_cloud_only_ignores_the_local_provider() -> None:
    router = ProviderRouter(local_provider=_Stub(), cloud_only=True)

    assert router.has_configured_upstream() is False
    assert ProviderRouter(cloud_provider=_Stub(), cloud_only=True).has_configured_upstream() is True


def test_a_local_provider_is_enough_when_not_cloud_only() -> None:
    assert ProviderRouter(local_provider=_Stub()).has_configured_upstream() is True


def test_cloud_counts_when_it_is_enabled() -> None:
    router = ProviderRouter(cloud_provider=_Stub(), cloud_enabled=True)

    assert router.has_configured_upstream() is True


def test_cloud_counts_when_it_is_the_default_provider() -> None:
    router = ProviderRouter(cloud_provider=_Stub(), default_provider="cloud")

    assert router.has_configured_upstream() is True


def test_cloud_alone_does_not_count_when_it_is_neither_enabled_nor_default() -> None:
    # 只配了 key 但没开、也不是默认路由时，不该对外声称有上游。
    router = ProviderRouter(cloud_provider=_Stub())

    assert router.has_configured_upstream() is False


def test_an_empty_router_has_no_upstream() -> None:
    assert ProviderRouter().has_configured_upstream() is False


# --- token_source -----------------------------------------------------------


def test_token_source_is_created_lazily_and_cached() -> None:
    # 注意这个属性属于 Vertex Provider，不是 ProviderRouter。
    provider = VertexOpenAICompatibleProvider(_SETTINGS)

    first = provider.token_source
    second = provider.token_source

    assert isinstance(first, AdcAccessTokenSource)
    assert first is second  # 同一个实例，不会每次新建


# --- from_env ---------------------------------------------------------------


def test_from_env_matches_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from stardew_ai_bridge.config import BridgeSettings

    monkeypatch.delenv("BRIDGE_LOCAL_URL", raising=False)
    monkeypatch.delenv("BRIDGE_CLOUD_URL", raising=False)

    router = ProviderRouter.from_env()
    expected = ProviderRouter.from_settings(BridgeSettings.from_env())

    assert router.has_configured_upstream() == expected.has_configured_upstream()


# --- speech._stage_conditioned_voice_sample ---------------------------------


def _sample(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sampleId": "s1",
        "npcId": "Shane",
        "sourceKey": "Mon1",
        "sourcePath": "characters.json",
        "evidenceKind": "dialogue",
        "text": "今天天气不错呢",
        "conditions": {"relationshipStage": "close"},
    }
    base.update(overrides)
    return base


def test_a_conditional_daily_sample_is_accepted() -> None:
    assert _stage_conditioned_voice_sample(_sample()) is True


@pytest.mark.parametrize("kind", ["marriage_dialogue", "roommate_dialogue"])
def test_marriage_and_roommate_samples_are_rejected(kind: str) -> None:
    # 婚后/室友对白不该被当成阶段锚点。
    assert _stage_conditioned_voice_sample(_sample(evidenceKind=kind)) is False


def test_samples_without_a_stage_are_rejected() -> None:
    assert _stage_conditioned_voice_sample(_sample(conditions={})) is False
    assert _stage_conditioned_voice_sample(_sample(conditions=None)) is False


@pytest.mark.parametrize(
    "path",
    ["assets/events/x.json", "/events/x.json", "chars/festivaldialogue.json"],
)
def test_event_and_festival_paths_are_rejected(path: str) -> None:
    assert _stage_conditioned_voice_sample(_sample(sourcePath=path)) is False


@pytest.mark.parametrize(
    "path",
    [
        "events/spring13.json",  # 裸 events/（索引里的 sourcePath 就是这种形态）
        "assets/events/x.json",
        "code/Festivals/winter25.json",  # 裸 code/（索引警告里真出现过）
        "assets/code/x.json",
        "festivaldialogue.json",
        "chars/festivaldialogue.json",
    ],
)
def test_event_code_and_festival_paths_are_all_rejected(path: str) -> None:
    # B18 已于第 135 项修复：这里改为与 `evidence._is_special_dialogue_record` 对齐。
    # 索引里的 sourcePath 是相对 Mod 根的、**不带前导斜杠**，所以只查 "/events/" 会漏掉
    # 顶层的 events/ 与 code/。实测真实索引里这两类路径的样本共 3525 个，但**没有一个**
    # 符合阶段锚点的其他条件——所以这次对齐不改变任何现有结果。
    assert _stage_conditioned_voice_sample(_sample(sourcePath=path)) is False


@pytest.mark.parametrize("key", ["MarriageDialogue", "spring_mon", "fall_Mon"])
def test_non_daily_keys_are_rejected(key: str) -> None:
    assert _stage_conditioned_voice_sample(_sample(sourceKey=key)) is False
