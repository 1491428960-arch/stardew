from __future__ import annotations

import asyncio
from collections.abc import Mapping
import inspect
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from time import perf_counter
from typing import Protocol, runtime_checkable

import httpx
from pydantic import ValidationError

from .config import BridgeSettings, ProviderSettings
from .models import DialogueTestRequest, OpenLoopSignal, ProviderResult, ProviderUsage
from .vertex_auth import AccessTokenSource, AdcAccessTokenSource, VertexAuthError
from .relationship_gating import relationship_stage_from_state
from .scene import season_label, time_of_day_label, weather_label


log = logging.getLogger(__name__)

# 日志里常见的密钥形态。httpx 的异常消息常带完整 URL，而 URL 的查询串、
# userinfo 段与 Authorization 头都可能含 key——诊断信息要留下，密钥不能进日志。
_SECRET_KEY_VALUE = re.compile(
    r"(?i)\b(api[_-]?key|apikey|access[_-]?token|token|password|secret|key)=([^&\s\"']+)"
)
_SECRET_BEARER = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9._\-]+)")
_SECRET_USERINFO = re.compile(r"(?i)(//)([^/\s:@]+):([^/\s@]+)@")


def _redact_secrets(text: str) -> str:
    """把文本里的密钥形态打码，其余上下文原样保留——诊断要看的正是这些上下文。"""

    text = _SECRET_KEY_VALUE.sub(lambda match: f"{match.group(1)}=***", text)
    text = _SECRET_BEARER.sub(lambda match: f"{match.group(1)} ***", text)
    return _SECRET_USERINFO.sub(lambda match: f"{match.group(1)}***:***@", text)


class ProviderError(RuntimeError):
    """Provider 调用失败，消息不包含请求凭据。"""


_KNOWN_GROUP_NPC_IDS = frozenset(
    {
        "Abigail",
        "Alex",
        "Andy",
        "Birdie",
        "Caroline",
        "Claire",
        "Clint",
        "Demetrius",
        "Dwarf",
        "Emily",
        "Evelyn",
        "George",
        "Gunther",
        "Gus",
        "Haley",
        "Jas",
        "Jodi",
        "Kent",
        "Krobus",
        "Lance",
        "Leah",
        "Leo",
        "Lewis",
        "Linus",
        "Marlon",
        "Marnie",
        "Maru",
        "Morris",
        "Olivia",
        "Pam",
        "Penny",
        "Pierre",
        "Robin",
        "Sandy",
        "Sebastian",
        "Shane",
        "Sophia",
        "Victor",
        "Vincent",
        "Willy",
        "Wizard",
    }
)


def _non_negative_count(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _usage_from_mapping(value: object) -> ProviderUsage | None:
    if not isinstance(value, Mapping):
        return None
    input_tokens = next(
        (
            count
            for key in ("input_tokens", "prompt_tokens", "prompt_eval_count")
            if (count := _non_negative_count(value.get(key))) is not None
        ),
        None,
    )
    output_tokens = next(
        (
            count
            for key in ("output_tokens", "completion_tokens", "eval_count")
            if (count := _non_negative_count(value.get(key))) is not None
        ),
        None,
    )
    total_tokens = _non_negative_count(value.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    return ProviderUsage(
        inputTokens=input_tokens,
        outputTokens=output_tokens,
        totalTokens=total_tokens,
    )


def _open_loop_from_mapping(value: object) -> tuple[OpenLoopSignal | None, str | None]:
    if value is None:
        return None, None
    try:
        return OpenLoopSignal.model_validate(value), None
    except (TypeError, ValueError, ValidationError):
        return None, "openLoop: invalid metadata"


def _default_provider_messages(request: DialogueTestRequest) -> list[dict[str, str]]:
    messages = [
        {
            "role": "system",
            "content": (
                f"你正在扮演 {request.display_name or request.npc_id}。"
                "请用简洁、自然的中文回复。"
            ),
        },
    ]
    if request.intent == "topic":
        messages.append(
            {
                "role": "user",
                "name": "topic_trigger",
                "content": "",
            }
        )
    else:
        messages.append({"role": "user", "content": request.message})
    return messages


#: 单轮输出预算。中文 240 token 约 160 字，够她把「物品 + 反应 + 动作」一口气
#: 写完；原先的 160 是**为 DeepSeek 系定的**（reasoning 会先吃掉一大截预算），
#: 而现行云端是不带推理的 Kimi-K2.5 —— 那个额度在物品场景偏紧：
#: 2026-09-23 实机一个晚上撞线两次（finish_reason=length）。
_SINGLE_TURN_MAX_TOKENS = 240
_MULTI_TURN_MAX_TOKENS = 900


def _max_tokens_for(request: DialogueTestRequest) -> int:
    """群聊自然接话流一次要写多条对白，沿用单条上限会被截断成一条。

    单 NPC 对话按 `_SINGLE_TURN_MAX_TOKENS` 给；多人自然接话流按回合数给足
    预算，否则模型写到一半就被截断，JSON 也不完整。
    """

    if request.group_strategy == "multi_turn":
        return _MULTI_TURN_MAX_TOKENS
    return _SINGLE_TURN_MAX_TOKENS


#: 句末标点：整体以此收尾才算「话说完了」。逗号和顿号**不算** ——
#: 那正是半句话的样子。
_SENTENCE_TERMINATORS = "。！？…～!?.~"
#: 收尾的成对符号：她说「……我想画下来。」时，最后一个字符是 `」`。
_TRAILING_WRAPPERS = "\"'”’」』）)]】"


def _ends_like_a_whole_sentence(text: str) -> bool:
    """截断之后，判断到手的部分是不是一句完整的话。

    只看最后一个字符（先剥掉收尾的引号／括号）：句末标点算完整，
    逗号、顿号或者半截词都算没说完。

    `finish_reason=length` 只说明她说得比预算长，不说明这一轮不能用 ——
    2026-09-23 实机里它被升级成了「暂时联系不上她」。
    """

    stripped = text.strip()
    while stripped and stripped[-1] in _TRAILING_WRAPPERS:
        stripped = stripped[:-1].rstrip()
    return bool(stripped) and stripped[-1] in _SENTENCE_TERMINATORS


#: 空 content 的替代文本。只用于**出网请求的最后一步**，不进入 prompt 构造。
_EMPTY_MESSAGE_PLACEHOLDER = "（无）"


def _fill_empty_message_content(
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """把 content 为空的消息填上占位符，**不能删掉那一条**。

    `persona_core` / `topic_trigger` 这类卡片在"玩家还没开口"的回合本来就是空的，
    而 DeepSeek 官方端点容忍空 content，所以这个缺陷长期没暴露。

    2026-09-23 切到 Command Code 后上游会直接拒绝，实测两种错法都是 400：

    * 原样发空 content → `user message must have content`（param 指向那一条）；
    * **删掉那一条** → `A conversation must start with a user message`
      （`topic_trigger` 恰好是唯一的 user 消息，删了就只剩 system）。

    所以只能填不能删。占位符取「（无）」而非空串或空格：空串是同一个错误，
    而空格过不了 `strip()` 类的上游校验。
    """

    out: list[dict[str, str]] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            message = {**message, "content": _EMPTY_MESSAGE_PLACEHOLDER}
        out.append(message)
    return out


@runtime_checkable
class Provider(Protocol):
    @property
    def name(self) -> str:
        """返回 Provider 的稳定标识。"""

    def generate(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        """根据一次测试请求生成结构化回复。"""


class FakeProvider(Provider):
    """不联网的确定性演示 Provider；它不是语言模型。"""

    DEMO_MARKER = "【本地演示·非真实 AI】"

    _NPC_LABELS = {
        "rasmodia": "Rasmodia",
        "wizard": "Rasmodia",
        "stardewai_npc_test": "Rasmodia（测试）",
    }
    _GROUP_LABELS = {
        item.casefold(): item for item in _KNOWN_GROUP_NPC_IDS
    }
    _GROUP_LABELS.update({"wizard": "Rasmodia", "rasmodia": "Rasmodia"})

    _RELATIONSHIP_LABELS = {
        "stranger": "初识",
        "acquaintance": "熟悉",
        "friend": "朋友",
        "close": "亲近",
        "dating": "恋爱",
        "married": "婚后",
        "parent": "育儿",
    }

    @property
    def name(self) -> str:
        return "fake"

    def generate(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        del messages
        return ProviderResult(
            reply=self._build_demo_reply(request),
            provider=self.name,
            fallback=False,
            latencyMs=0,
            warnings=[],
        )

    def _build_demo_reply(self, request: DialogueTestRequest) -> str:
        # Fake mode is reachable without an upstream model, so never reflect
        # request-controlled identity, message, fact, or item text. Only exact
        # known IDs are mapped to fixed labels.
        if request.group_strategy == "multi_turn":
            return self._build_multi_turn_demo_reply(request)

        display_name = self._NPC_LABELS.get(request.npc_id.strip().lower(), "NPC")
        state = request.game_state
        context_parts: list[str] = []
        if state is not None:
            season = season_label(state.season)
            weather = weather_label(state.weather)
            if season:
                context_parts.append(season)
            if weather:
                context_parts.append(weather)
            # 演示文案是给人读的一句通顺话，所以只取时段词（「清晨」），
            # 不带场景卡那种括号时刻（`清晨（6:00）`）。
            time_label = time_of_day_label(state.time, include_clock=False)
            if time_label:
                context_parts.append(time_label)

        context_text = "、".join(context_parts)
        relationship_stage = self._relationship_stage(state)
        relationship_label = self._RELATIONSHIP_LABELS[relationship_stage]
        history_count = self._history_count(request.history)
        history_text = (
            f"我们已经聊过 {history_count} 条消息"
            if history_count
            else "这是本次对话的开场"
        )
        if request.intent == "topic":
            body = (
                f"我来主动找话题：现在是{context_text or '今天'}，"
                f"我们处在{relationship_label}阶段。"
                "你最近有什么想聊的日常吗？"
            )
        elif request.intent == "item" and request.item_context is not None:
            action = {
                "display": "拿出来给我看",
                "share": "和我分享",
                "gift": "准备送给我",
            }[request.item_context.action]
            body = (
                f"我们处在{relationship_label}阶段，我看到你把这件物品{action}了。"
                "这个版本只按物品字段选择预设话术。"
            )
        elif "天气" in request.message or "下雨" in request.message:
            body = (
                f"{context_text or '当前天气'}确实会改变一天的安排。"
                f"我们处在{relationship_label}阶段，"
                "这句回复来自游戏时间与天气字段。"
            )
        elif any(word in request.message for word in ("关系", "好感", "心")):
            hearts = state.friendship_hearts if state is not None else None
            body = (
                f"当前关系记录是 {hearts} 颗心，阶段是{relationship_label}。"
                if hearts is not None
                else f"当前请求里没有可用的关系心级，暂按{relationship_label}阶段演示。"
            )
        elif request.recent_facts:
            body = (
                f"我们处在{relationship_label}阶段，收到了最近 "
                f"{len(request.recent_facts)} 条事实记录，"
                "但演示模式不会自行补写剧情。"
            )
        else:
            prefix = f"现在是{context_text}。" if context_text else ""
            body = (
                f"{prefix}我们处在{relationship_label}阶段，{history_text}。"
                "我收到了你的话，"
                "这里只会按少量游戏字段选择预设回复。"
            )

        return f"{self.DEMO_MARKER}{display_name}：{body}"

    def _build_multi_turn_demo_reply(self, request: DialogueTestRequest) -> str:
        candidate_ids = [
            item.strip()
            for item in request.group_participant_ids
            if isinstance(item, str) and item.strip()
        ]
        if not candidate_ids:
            candidate_ids = [request.npc_id.strip()]
        # Fake mode must not reflect an arbitrary request-controlled identity.
        # Unknown IDs are omitted instead of being turned into fabricated NPC
        # dialogue; the real group service will report an empty/invalid demo
        # result rather than displaying untrusted identity text.
        participant_ids = [
            item
            for item in candidate_ids
            if item.casefold() in self._GROUP_LABELS
        ][: request.group_turn_count]

        turns = []
        for participant_id in participant_ids:
            label = self._GROUP_LABELS.get(participant_id.casefold(), "NPC")
            turns.append(
                {
                    "speakerNpcId": participant_id,
                    "content": (
                        f"{self.DEMO_MARKER}{label}：这是多人线上演示中的一条公开回复。"
                    ),
                    "addressedTo": [],
                }
            )
        return json.dumps({"turns": turns}, ensure_ascii=False)


    @classmethod
    def _relationship_stage(cls, state: NpcGameState | None) -> str:
        # 统一到 relationship_gating（2026-09-20 系统性排查）：此前这里自己推导一遍，
        # ①  忽略请求里显式给的 relationshipStage，② 心数边界用 3 而其它三处用 2。
        if state is None:
            return "stranger"
        return relationship_stage_from_state(
            # NpcGameState 里没有 relationshipStage 字段（C# 也不在 gameState 里发它，
            # 只发在 history item 上），所以这里显式传 None。
            explicit_stage=None,
            children_count=state.children_count,
            marriage_status=state.marriage_status,
            relationship=state.relationship,
            friendship_hearts=state.friendship_hearts,
        )

    @staticmethod
    def _history_count(history: list[dict[str, object]]) -> int:
        return sum(
            1
            for item in history
            if isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
            and bool(item["content"].strip())
        )


class OpenAICompatibleProvider:
    """调用 OpenAI-compatible chat completions 接口的同步 Provider。"""

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    @property
    def name(self) -> str:
        return self.settings.name

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"content-type": "application/json"}
        if self.settings.api_key:
            headers["authorization"] = f"Bearer {self.settings.api_key}"
        return headers

    def generate(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        started_at = perf_counter()
        response = _run_async(self._generate_async(request, messages=messages))
        return response.model_copy(
            update={
                "latency_ms": max(
                    response.latency_ms,
                    int((perf_counter() - started_at) * 1000),
                )
            }
        )

    async def _generate_async(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        if not self.settings.enabled or not self.settings.url:
            raise ProviderError(f"{self.name} provider is disabled")
        if not self.settings.model:
            raise ProviderError(f"{self.name} provider model is not configured")

        headers: dict[str, str] = self._headers()
        payload = {
            "model": self.settings.model,
            # 出网前填掉空 content：Command Code 上游会 400 拒收，而删掉那一条
            # 又会被判"会话必须以 user 消息开头"。见 _fill_empty_message_content。
            "messages": _fill_empty_message_content(
                messages if messages is not None else _default_provider_messages(request)
            ),
            # 中转站对非流式收尾不稳定；流式响应能先返回 token，并在 Bridge
            # 内部拼成一次完整对白，避免游戏端把正常生成误判为超时。
            "stream": True,
            "max_tokens": _max_tokens_for(request),
        }
        # 只在显式配置时才发 temperature。不设就走上游默认，与加这个字段之前
        # 逐字节一致 —— 免得顺手改变了所有既有 A/B 的可比性。
        # 实测噪音底噪见 `config.ProviderSettings.temperature`。
        if self.settings.temperature is not None:
            payload["temperature"] = self.settings.temperature
        started_at = perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.timeout,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST",
                    self.settings.url,
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.is_error:
                        raise ProviderError(
                            f"{self.name} returned HTTP {response.status_code}"
                        )

                    reply_parts: list[str] = []
                    usage: ProviderUsage | None = None
                    open_loop_value: object = None
                    truncated = False
                    is_event_stream = "text/event-stream" in response.headers.get(
                        "content-type", ""
                    ).lower()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line == "[DONE]":
                            break
                        if not is_event_stream and not line.startswith("{"):
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ProviderError(
                                f"{self.name} returned an invalid response"
                            ) from exc
                        if not isinstance(chunk, Mapping):
                            continue
                        if isinstance(chunk.get("error"), Mapping):
                            raise ProviderError(
                                f"{self.name} returned embedded provider error"
                            )
                        choices = chunk.get("choices")
                        if isinstance(choices, list) and choices:
                            choice = choices[0]
                            if isinstance(choice, Mapping):
                                finish_reason = choice.get("finish_reason")
                                if finish_reason == "length":
                                    # 先别急着丢掉整轮：到手的部分可能已经是一句
                                    # 完整的话。真正的判定放在拼完之后。
                                    truncated = True
                                    break
                                delta = choice.get("delta")
                                if isinstance(delta, Mapping):
                                    content = delta.get("content")
                                else:
                                    message = choice.get("message")
                                    content = (
                                        message.get("content")
                                        if isinstance(message, Mapping)
                                        else None
                                    )
                                if isinstance(content, str):
                                    reply_parts.append(content)
                        chunk_usage = _usage_from_mapping(chunk.get("usage"))
                        if chunk_usage is not None:
                            usage = chunk_usage
                        if "openLoop" in chunk:
                            open_loop_value = chunk.get("openLoop")
                    reply = "".join(reply_parts)
                    if truncated and not _ends_like_a_whole_sentence(reply):
                        raise ProviderError(
                            f"{self.name} returned truncated stream "
                            "(finish_reason=length)"
                        )
        except ProviderError:
            raise
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            raise ProviderError(f"{self.name} request failed") from exc

        try:
            if not reply.strip():
                raise ValueError("empty content")
            open_loop, open_loop_warning = _open_loop_from_mapping(open_loop_value)
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("empty content")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"{self.name} returned an invalid response") from exc

        return ProviderResult(
            reply=reply.strip(),
            provider=self.name,
            fallback=False,
            latencyMs=int((perf_counter() - started_at) * 1000),
            warnings=[open_loop_warning] if open_loop_warning else [],
            usage=usage,
            openLoop=open_loop,
        )


class VertexOpenAICompatibleProvider(OpenAICompatibleProvider):
    """用 ADC 短期 access token 调用 Vertex AI OpenAI-compatible 端点。

    与 API-key 模式的区别只有鉴权来源和 TLS 要求：请求体、流式解析、
    usage 和 openLoop 处理全部复用 `OpenAICompatibleProvider`。凭据不可用
    时抛出不含 token 的 `ProviderError`，让路由器走安全兜底。
    """

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        token_source: AccessTokenSource | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(settings, transport=transport)
        self._token_source = token_source

    @property
    def token_source(self) -> AccessTokenSource:
        if self._token_source is None:
            self._token_source = AdcAccessTokenSource()
        return self._token_source

    def _headers(self) -> dict[str, str]:
        url = self.settings.url or ""
        if not url.startswith("https://"):
            raise ProviderError(f"{self.name} vertex endpoint must use https")
        try:
            token = self.token_source.access_token()
        except VertexAuthError as exc:
            raise ProviderError(str(exc)) from exc
        return {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
        }


class OllamaNativeProvider:
    """调用 Ollama 原生 /api/chat，显式关闭 thinking 和流式响应。"""

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    @property
    def name(self) -> str:
        return self.settings.name

    def generate(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        started_at = perf_counter()
        response = _run_async(self._generate_async(request, messages=messages))
        return response.model_copy(
            update={
                "latency_ms": max(
                    response.latency_ms,
                    int((perf_counter() - started_at) * 1000),
                )
            }
        )

    async def _generate_async(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        if not self.settings.enabled or not self.settings.url:
            raise ProviderError(f"{self.name} provider is disabled")
        if not self.settings.model:
            raise ProviderError(f"{self.name} provider model is not configured")

        headers = {"content-type": "application/json"}
        # Ollama 把采样参数放在 options 里，而不是顶层。
        options: dict[str, object] = {"num_predict": _max_tokens_for(request)}
        if self.settings.temperature is not None:
            options["temperature"] = self.settings.temperature
        payload = {
            "model": self.settings.model,
            "messages": (
                messages if messages is not None else _default_provider_messages(request)
            ),
            "stream": False,
            "think": False,
            "options": options,
        }
        started_at = perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.timeout,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    self.settings.url,
                    headers=headers,
                    json=payload,
                )
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            raise ProviderError(f"{self.name} request failed") from exc

        if response.is_error:
            raise ProviderError(f"{self.name} returned HTTP {response.status_code}")

        try:
            body = response.json()
            reply = body["message"]["content"]
            usage = _usage_from_mapping(body.get("usage"))
            if usage is None:
                usage = _usage_from_mapping(body)
            open_loop, open_loop_warning = _open_loop_from_mapping(body.get("openLoop"))
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("empty content")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"{self.name} returned an invalid response") from exc

        return ProviderResult(
            reply=reply.strip(),
            provider=self.name,
            fallback=False,
            latencyMs=int((perf_counter() - started_at) * 1000),
            warnings=[open_loop_warning] if open_loop_warning else [],
            usage=usage,
            openLoop=open_loop,
        )


def _run_async(coroutine):  # type: ignore[no-untyped-def]
    """在同步接口中运行协程；若调用方已有事件循环则隔离到线程。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


class ProviderRouter:
    """支持正式云端锁定、显式本地 A/B 和安全回复兜底的 Provider 路由器。"""

    def __init__(
        self,
        local_provider: Provider | None = None,
        cloud_provider: Provider | None = None,
        fallback_provider: Provider | None = None,
        *,
        fake_provider: Provider | None = None,
        cloud_enabled: bool = False,
        cloud_only: bool = False,
        default_provider: str = "auto",
    ) -> None:
        if fallback_provider is None:
            from .fallback import FallbackProvider

            fallback_provider = FallbackProvider()
        self.local_provider = local_provider
        self.cloud_provider = cloud_provider
        self.fallback_provider = fallback_provider
        self.fake_provider = fake_provider or FakeProvider()
        self.cloud_enabled = cloud_enabled
        self.cloud_only = cloud_only
        self.default_provider = (
            default_provider
            if default_provider in {"auto", "local", "cloud"}
            else "auto"
        )

    @classmethod
    def from_settings(
        cls,
        settings: BridgeSettings,
        *,
        fake_provider: Provider | None = None,
        fallback_provider: Provider | None = None,
    ) -> "ProviderRouter":
        local = (
            cls._provider_from_settings(settings.local)
            if settings.local.enabled and settings.local.url
            else None
        )
        # `cloud_enabled` controls whether automatic routing may spend cloud
        # credits. An explicitly requested cloud provider must still be
        # constructible when a URL is configured, even if auto routing is off.
        cloud_settings = (
            replace(settings.cloud, enabled=True)
            if settings.cloud.url
            else settings.cloud
        )
        cloud = (
            cls._provider_from_settings(cloud_settings)
            if cloud_settings.url
            else None
        )
        if fallback_provider is None:
            from .fallback import FallbackProvider

            fallback_provider = FallbackProvider(settings.fallback_reply)
        return cls(
            local_provider=local,
            cloud_provider=cloud,
            fallback_provider=fallback_provider,
            fake_provider=fake_provider,
            cloud_enabled=settings.cloud_enabled,
            cloud_only=settings.cloud_only,
            default_provider="cloud" if cloud is not None else "auto",
        )

    @staticmethod
    def _provider_from_settings(settings: ProviderSettings) -> Provider:
        if settings.api_mode == "vertex":
            return VertexOpenAICompatibleProvider(settings)
        if settings.api_mode == "ollama":
            return OllamaNativeProvider(settings)
        return OpenAICompatibleProvider(settings)

    @classmethod
    def from_env(
        cls,
        *,
        fake_provider: Provider | None = None,
        fallback_provider: Provider | None = None,
    ) -> "ProviderRouter":
        return cls.from_settings(
            BridgeSettings.from_env(),
            fake_provider=fake_provider,
            fallback_provider=fallback_provider,
        )

    def has_configured_upstream(self) -> bool:
        if self.cloud_only:
            return self.cloud_provider is not None
        return self.local_provider is not None or (
            self.cloud_provider is not None
            and (self.cloud_enabled or self.default_provider == "cloud")
        )

    def generate(
        self,
        request: DialogueTestRequest,
        provider: str | None = None,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        explicit_provider = provider or self._explicit_request_provider(request)
        selected_provider = explicit_provider or self.default_provider
        if selected_provider == "fake":
            return self.fake_provider.generate(request)

        warnings: list[str] = []
        started_at = perf_counter()
        for candidate in self._candidates(selected_provider):
            try:
                result = self._generate_candidate(candidate, request, messages)
            except Exception as exc:  # noqa: BLE001 - 路由必须隔离单个上游故障
                warnings.append(self._warning(candidate, exc))
                continue
            return self._with_metadata(
                result,
                warnings=warnings,
                elapsed_ms=int((perf_counter() - started_at) * 1000),
            )

        result = self.fallback_provider.generate(request)
        return self._with_metadata(
            result,
            fallback=True,
            warnings=warnings,
            elapsed_ms=int((perf_counter() - started_at) * 1000),
        )

    @staticmethod
    def _generate_candidate(
        candidate: Provider,
        request: DialogueTestRequest,
        messages: list[dict[str, str]] | None,
    ) -> ProviderResult:
        if messages is None:
            return candidate.generate(request)

        parameters = inspect.signature(candidate.generate).parameters
        accepts_messages = "messages" in parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        if accepts_messages:
            return candidate.generate(request, messages=messages)
        return candidate.generate(request)

    def _candidates(self, provider: str | None = None) -> list[Provider]:
        candidates: list[Provider] = []
        if provider in {"local", "cloud"}:
            if provider == "local" and self.local_provider is not None:
                candidates.append(self.local_provider)
            if provider == "cloud" and self.cloud_provider is not None:
                candidates.append(self.cloud_provider)
            return candidates
        if self.cloud_only:
            if self.cloud_provider is not None:
                candidates.append(self.cloud_provider)
            return candidates
        if self.local_provider is not None:
            candidates.append(self.local_provider)
        if self.cloud_enabled and self.cloud_provider is not None:
            candidates.append(self.cloud_provider)
        return candidates

    @staticmethod
    def _explicit_request_provider(request: DialogueTestRequest) -> str | None:
        fields_set = getattr(request, "model_fields_set", set())
        return request.provider if "provider" in fields_set else None

    @staticmethod
    def _warning(provider: Provider, error: Exception) -> str:
        """候选失败时的一致处理：**响应泛化，日志可诊断**。

        响应里只回 ``<name> provider failed``——上游细节不进游戏端；
        但服务端日志必须留下候选名、异常类型与消息，否则一旦上游开始不稳定，
        只能看到“延迟变高 + warningCount 上升”而无法定位
        （2026-09-20 真机验证时遇到过一次 ``latencyMs=3976; warningCount=2``，
        当时因为这里 `del error` 而查不出是哪两个候选失败）。
        """
        log.warning(
            "provider 候选失败：name=%s type=%s message=%s",
            provider.name,
            type(error).__name__,
            _redact_secrets(str(error)),
        )
        return f"{provider.name} provider failed"

    @staticmethod
    def _with_metadata(
        result: ProviderResult,
        *,
        warnings: list[str],
        elapsed_ms: int,
        fallback: bool | None = None,
    ) -> ProviderResult:
        return result.model_copy(
            update={
                "fallback": result.fallback if fallback is None else fallback,
                "latency_ms": max(result.latency_ms, elapsed_ms),
                "warnings": [*warnings, *result.warnings],
            }
        )
