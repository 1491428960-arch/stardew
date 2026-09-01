from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import Iterable
from typing import Any

from .models import DialogueTestRequest
from .profile_index import ProfileIndexStore
from .prompts import ContextBuilder, PromptBuilder


# 同时保留人类可读别名和 SMAPI UniqueID，确保与运行时采集的索引来源匹配。
_SOURCE_MODS = [
    "SVE",
    "FlashShifter.SVECode",
    "FlashShifter.StardewValleyExpandedCP",
    "Romanceable Rasmodius",
    "Parrot.RomRas",
]
_FORBIDDEN_TERMS = (
    "作为 AI",
    "作为ai",
    "语言模型",
    "<think>",
    "</think>",
    "修改好感",
    "系统提示",
)


@dataclass(frozen=True)
class RasmodiaBenchmarkCase:
    """一个固定上下文的 Rasmodia 模型评测用例。"""

    case_id: str
    label: str
    message: str
    relationship_stage: str
    payload: dict[str, Any]
    expected_terms: tuple[str, ...] = ()
    min_expected_hits: int = 0
    forbidden_terms: tuple[str, ...] = ()

    def request(self) -> DialogueTestRequest:
        return DialogueTestRequest.model_validate(self.payload)


def _case(
    case_id: str,
    label: str,
    message: str,
    relationship_stage: str,
    *,
    friendship_hearts: int,
    season: str = "spring",
    weather: str = "sunny",
    time: int = 830,
    location: str = "WizardHouse",
    marriage_status: str | None = None,
    recent_facts: list[str] | None = None,
    history: list[dict[str, str]] | None = None,
    completed_event_ids: list[str] | None = None,
    expected_terms: tuple[str, ...] = (),
    min_expected_hits: int | None = None,
    forbidden_terms: tuple[str, ...] = (),
) -> RasmodiaBenchmarkCase:
    payload: dict[str, Any] = {
        "npcId": "Wizard",
        "displayName": "Rasmodia",
        "sourceMods": list(_SOURCE_MODS),
        "recentFacts": recent_facts or [],
        "history": history or [],
        "message": message,
        "gameState": {
            "season": season,
            "weather": weather,
            "time": time,
            "location": location,
            "friendshipHearts": friendship_hearts,
            "marriageStatus": marriage_status,
            "completedEventIds": completed_event_ids or [],
            "sourceMods": list(_SOURCE_MODS),
        },
    }
    # 只要用例声明了期望词，默认就要求至少命中一项；调用方仍可显式传
    # ``min_expected_hits=0``，用于仅记录关键词而不把它作为通过条件的场景。
    required_hits = (
        1 if expected_terms and min_expected_hits is None else (min_expected_hits or 0)
    )
    return RasmodiaBenchmarkCase(
        case_id=case_id,
        label=label,
        message=message,
        relationship_stage=relationship_stage,
        payload=payload,
        expected_terms=expected_terms,
        min_expected_hits=required_hits,
        forbidden_terms=forbidden_terms,
    )


DEFAULT_CASES: tuple[RasmodiaBenchmarkCase, ...] = (
    _case(
        "stranger_opening",
        "初识：自然回应日常问候",
        "早上好，今天过得怎么样？",
        "stranger",
        friendship_hearts=0,
        expected_terms=("早上", "今天", "今日", "早"),
    ),
    _case(
        "sve_context",
        "SVE：只使用已确认的近期事实",
        "我听说你最近在研究什么？",
        "acquaintance",
        friendship_hearts=4,
        recent_facts=["玩家刚刚在法师塔外与她打过招呼"],
        expected_terms=("研究", "魔法", "法师塔", "观测", "数据", "星界", "塔"),
    ),
    _case(
        "friend_voice",
        "朋友：回答研究进展而不过度亲密",
        "最近的研究有什么进展吗？",
        "friend",
        friendship_hearts=6,
        expected_terms=(
            "研究",
            "进展",
            "观测",
            "数据",
            "结论",
            "实验",
            "频率",
            "波动",
        ),
    ),
    _case(
        "close_voice",
        "亲近：可以具体但保留边界",
        "你最近是不是有些烦恼？可以和我说说。",
        "close",
        friendship_hearts=8,
        expected_terms=(
            "不确定",
            "研究",
            "谢谢",
            "未知",
            "烦恼",
            "困扰",
            "异常",
            "数据",
            "边界",
            "担心",
        ),
    ),
    _case(
        "roommate_stage",
        "Roommate：按婚后同居阶段处理",
        "今晚回农场一起吃饭吗？",
        "married",
        friendship_hearts=10,
        marriage_status="roommate",
        location="FarmHouse",
        time=1830,
        expected_terms=("一起", "农场", "晚", "晚餐", "晚饭", "约定"),
    ),
    _case(
        "same_day_follow_up",
        "同日多轮：保留上一轮记忆",
        "那杯咖啡后来怎么样了？",
        "close",
        friendship_hearts=8,
        history=[
            {"role": "user", "content": "同一天早些时候我给你带了一杯咖啡。"},
            {"role": "assistant", "content": "我会在整理完药剂后慢慢喝，谢谢你。"},
        ],
        # 允许模型用“香气/味道/托盘”等自然改写表达对上一轮咖啡的记忆，
        # 避免把不重复原词误判成丢失上下文。
        expected_terms=(
            "咖啡",
            "同一天",
            "药剂",
            "香气",
            "味道",
            "托盘",
            "一口",
            "很苦",
            "提神",
            "配方",
            "研究台",
            "液体",
            "温热",
            "加热",
            "玻璃瓶",
            "饮用",
            "礼物",
            "封存",
        ),
    ),
    _case(
        "unknown_event_boundary",
        "未触发事件：不得把猜测说成事实",
        "你是不是已经完成了深夜仪式？",
        "friend",
        friendship_hearts=6,
        completed_event_ids=[],
        # 拒答边界也允许“未完成/猜测/没有确凿证据”等等价的谨慎表述。
        expected_terms=(
            "不确定",
            "不知道",
            "不能确定",
            "没有记录",
            "尚未",
            "未完成",
            "猜测",
            "没有确凿证据",
            "无定论",
            "未曾确认",
            "未曾公开确认",
            "未确认",
            "无法确认",
            "不明确",
            "还没",
            "未经验证",
            "没有结果",
            "没有做出",
            "不具备",
            "不会",
            "并非",
            "不是",
            "例行检查",
            "传统意义",
        ),
        min_expected_hits=1,
        forbidden_terms=(
            "深夜仪式已经完成",
            "完成了深夜仪式",
            "仪式已经完成",
            "我已经完成了这个仪式",
            "仪式确实在预定时间结束",
        ),
    ),
)


def build_case_messages(
    case: RasmodiaBenchmarkCase,
    *,
    profile_index: ProfileIndexStore | None = None,
) -> list[dict[str, str]]:
    """用项目实际的 ContextBuilder/PromptBuilder 生成固定评测输入。"""

    context = ContextBuilder(profile_index=profile_index).build(case.payload)
    return PromptBuilder().build(context, case.message)


def parse_ollama_stream_lines(lines: Iterable[str]) -> list[dict[str, Any]]:
    """解析 Ollama ``stream=true`` 返回的 NDJSON 事件。"""

    events: list[dict[str, Any]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            event = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid Ollama stream event") from exc
        if not isinstance(event, dict):
            raise ValueError("invalid Ollama stream event")
        events.append(event)
    return events


def summarize_ollama_stream(
    events: Iterable[dict[str, Any]],
    *,
    total_latency_ms: int,
    first_content_latency_ms: int | None,
) -> dict[str, Any]:
    """合并流式回复，并换算 Ollama 完成事件中的耗时指标。"""

    reply_parts: list[str] = []
    done_event: dict[str, Any] = {}
    for event in events:
        message = event.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                reply_parts.append(content)
        if event.get("done") is True:
            done_event = event

    eval_count = _nonnegative_int(done_event.get("eval_count"))
    eval_duration_ns = _nonnegative_number(done_event.get("eval_duration"))
    tokens_per_second = None
    if eval_count is not None and eval_duration_ns and eval_duration_ns > 0:
        tokens_per_second = round(eval_count / (eval_duration_ns / 1_000_000_000), 2)

    return {
        "reply": "".join(reply_parts).strip(),
        "firstContentLatencyMs": first_content_latency_ms,
        "totalLatencyMs": total_latency_ms,
        "evalCount": eval_count,
        "evalDurationMs": _duration_ms(eval_duration_ns),
        "tokensPerSecond": tokens_per_second,
        "loadDurationMs": _duration_ms(
            _nonnegative_number(done_event.get("load_duration"))
        ),
        "promptEvalCount": _nonnegative_int(done_event.get("prompt_eval_count")),
        "promptEvalDurationMs": _duration_ms(
            _nonnegative_number(done_event.get("prompt_eval_duration"))
        ),
    }


def _nonnegative_number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


def _nonnegative_int(value: object) -> int | None:
    number = _nonnegative_number(value)
    return int(number) if number is not None and number.is_integer() else None


def _duration_ms(nanoseconds: float | None) -> float | None:
    return round(nanoseconds / 1_000_000, 1) if nanoseconds is not None else None


def score_reply(case: RasmodiaBenchmarkCase, reply: str) -> dict[str, object]:
    """计算可复核的轻量分数，原文仍需人工检查。"""

    text = reply.strip()
    lowered = text.casefold()
    expected_hits = sum(
        1 for term in case.expected_terms if term.casefold() in lowered
    )
    forbidden_hits = sum(
        1
        for term in (*_FORBIDDEN_TERMS, *case.forbidden_terms)
        if term.casefold() in lowered
    )
    passed = (
        bool(text)
        and forbidden_hits == 0
        and expected_hits >= case.min_expected_hits
    )
    return {
        "expectedHits": expected_hits,
        "forbiddenHits": forbidden_hits,
        "replyLength": len(text),
        "passed": passed,
    }
