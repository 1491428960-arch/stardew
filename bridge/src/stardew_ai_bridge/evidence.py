"""对白证据的稳定性判定。

模型生成窗口只应使用可以脱离特殊触发条件理解的对白；原始参照页仍可
保留所有已解析对白。这里集中维护判定，避免索引构建和运行时检索各自
产生一套不一致的过滤规则。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_EVENT_DIALOGUE_KEY = re.compile(
    r"^(?:event|festival|flowerdance|eggfestival|luau|moonlightjellies|"
    r"stardewvalleyfair|spiritseve|winterstar|wedding|married|roommate|divorced)",
    re.IGNORECASE,
)
_SEASON_DIALOGUE_KEY = re.compile(
    r"^(?:spring|summer|fall|winter)(?:_|$)",
    re.IGNORECASE,
)
_SPECIAL_SCENE_DIALOGUE_KEY = re.compile(
    r"^(?:breakup|dumped|secondchance|movieinvitation|dumpster|fair_|"
    r"hitbyslingshot|spouse|wipedmemory|funleave|funreturn|makeup)",
    re.IGNORECASE,
)
_CONDITIONAL_DIALOGUE_KEY = re.compile(
    # 这些键把地点、时间、事件参与者或分支结果编码进键名；即使文件在
    # Dialogue 目录中，也不能把它们当成角色无条件的日常口吻。
    r"(?:^|_)(?:event|festival|flowerdance|eggfestival|luau|"
    r"moonlightjellies|stardewvalleyfair|spiritseve|winterstar|wedding|"
    r"inlaw)(?:_|\d|$)|"
    r"^(?:[a-z][a-z0-9]*)_\d+_\d+(?:_|$)",
    re.IGNORECASE,
)
_SITUATIONAL_DIALOGUE_KEY = re.compile(
    r"^(?:indoor|outdoor|rainy|sunny|patio|spouseroom|"
    r"hospital|town|saloon|haleyhouse|joj amart|jojamart)(?:_|\d|$)",
    re.IGNORECASE | re.VERBOSE,
)
_GIFT_DIALOGUE_KEY = re.compile(
    r"(?:accept(?:_|$)|gift|birthday|bouquet|mermaid|stardrop|spousegift|give_flowers)",
    re.IGNORECASE,
)
_TRIGGERED_DIALOGUE_KEY = re.compile(
    r"^(?:greenrain|resort|desertfestival|firstvisit(?:_|$)|"
    r"fishcaught(?:_|$)|cropmatured(?:_|$)|purchasedanimal(?:_|$)|"
    r"achievement(?:_|$)|animalshop(?:_|$)|communitycenter(?:_|$)|"
    r"busstop(?:_|$)|cc_|city_|apples_|"
    r"claire_event(?:_|$)|custom_|bluemoonvineyard(?:_|$)|"
    r"archaeologyhouse(?:_|$)|forest(?:west)?(?:_|$)|mountain(?:_|$)|"
    r"beach(?:_|$)|pamhouseupgrade|"
    r"wonegghunt(?:_|$)|wongrange(?:_|$)|structurebuilt(?:_|$))",
    re.IGNORECASE,
)
_MEMORY_DIALOGUE_KEY = re.compile(r"(?:^|_)memory(?:_|$)", re.IGNORECASE)
_RELATIONSHIP_ONLY_DIALOGUE_KEY = re.compile(
    r"^(?:dating|engage|engaged|give_pendant|reject|refusal|dance(?:_|)rejection)",
    re.IGNORECASE,
)
_RELATION_RESPONSE_KEY = re.compile(
    r"^(?:neutral|good|bad)(?:_\d+)?$",
    re.IGNORECASE,
)
_OLD_DIALOGUE_ARTIFACT = re.compile(r"(?:^|[_-])old(?:$|[_-])", re.IGNORECASE)
_NUMERIC_DIALOGUE_PREFIX = re.compile(r"^\s*\d+\s+")
_NPC_ID_DIALOGUE_PREFIX = re.compile(r"^\s*[A-Za-z]{3,}\d+\s+")
_DIALOGUE_ACTION_MARKER = re.compile(r"\*[^*\r\n]*\*")
_DIALOGUE_NARRATION_PREFIX = re.compile(r"^\s*%")
_DIALOGUE_INLINE_NARRATION = re.compile(r"(?<!\S)%[\u4e00-\u9fffA-Za-z]")
_DIALOGUE_PARENTHETICAL_ACTION = re.compile(
    r"(?:\([^()\r\n]{1,24}\)|（[^（）\r\n]{1,24}）)"
)
_DIALOGUE_CONTROL_RESIDUE = re.compile(
    r"\{\{|\}\}|inputSeparator\s*=|\$\{|#?\$[A-Za-z0-9]+#?|"
    r"(?<![A-Za-z0-9])\$(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def has_dialogue_control_residue(value: object) -> bool:
    """判断文本是否仍含 Stardew 控制标记、动作标记或叙述分支。"""

    if not isinstance(value, str) or not value.strip():
        return False
    return bool(
        _DIALOGUE_ACTION_MARKER.search(value)
        or _DIALOGUE_NARRATION_PREFIX.match(value)
        or _DIALOGUE_INLINE_NARRATION.search(value)
        or _DIALOGUE_PARENTHETICAL_ACTION.search(value)
        or _DIALOGUE_CONTROL_RESIDUE.search(value)
    )


def has_dialogue_source_residue(record: Mapping[str, Any]) -> bool:
    """判断对白是否带有旧键或解包时混入的角色/编号前缀。"""

    source_key = str(record.get("sourceKey", "")).strip()
    source_path = str(record.get("sourcePath", "")).replace("\\", "/").strip()
    text = record.get("text")
    if not isinstance(text, str):
        return bool(
            _OLD_DIALOGUE_ARTIFACT.search(source_key)
            or _OLD_DIALOGUE_ARTIFACT.search(source_path)
        )
    npc_id_prefix = _NPC_ID_DIALOGUE_PREFIX.match(text)
    has_npc_id_prefix = bool(
        npc_id_prefix
        and text[npc_id_prefix.start() : npc_id_prefix.end() - 1].casefold()
        != source_key.casefold()
    )
    return bool(
        _OLD_DIALOGUE_ARTIFACT.search(source_key)
        or _OLD_DIALOGUE_ARTIFACT.search(source_path)
        or _NUMERIC_DIALOGUE_PREFIX.match(text)
        or has_npc_id_prefix
    )


def _is_special_dialogue_record(record: Mapping[str, Any]) -> bool:
    path = str(record.get("sourcePath", "")).replace("\\", "/").casefold()
    if (
        path == "ucr.json"
        or path.endswith("/ucr.json")
        or "/events/" in path
        or path.startswith("events/")
        or "/code/" in path
        or path.startswith("code/")
        or path.endswith("/festivaldialogue.json")
    ):
        return True

    key = str(record.get("sourceKey", "")).strip()
    return bool(
        _SEASON_DIALOGUE_KEY.match(key)
        or _EVENT_DIALOGUE_KEY.match(key)
        or _SPECIAL_SCENE_DIALOGUE_KEY.match(key)
        or _CONDITIONAL_DIALOGUE_KEY.search(key)
        or _SITUATIONAL_DIALOGUE_KEY.match(key)
        or _GIFT_DIALOGUE_KEY.search(key)
        or _TRIGGERED_DIALOGUE_KEY.match(key)
        or _MEMORY_DIALOGUE_KEY.search(key)
        or _RELATIONSHIP_ONLY_DIALOGUE_KEY.match(key)
        or _RELATION_RESPONSE_KEY.fullmatch(key)
    )


def is_model_evidence_record(record: Mapping[str, Any]) -> bool:
    """判断记录能否进入带条件的模型证据窗口。"""

    if has_dialogue_source_residue(record):
        return False
    evidence_kind = str(record.get("evidenceKind", "dialogue")).strip().casefold()
    if evidence_kind in {
        "runtime_dialogue",
        "marriage_dialogue",
        "roommate_dialogue",
        "event_dialogue",
    }:
        # 实际运行时样本和婚后样本有额外条件，分别由运行时归属或关系阶段
        # 检索处理；事件样本还要经过 completedEventIds 门控，不能在索引
        # 构建时无条件丢弃。
        return True
    return not _is_special_dialogue_record(record)


def is_stable_voice_evidence_record(record: Mapping[str, Any]) -> bool:
    """判断记录能否作为不带当前阶段的稳定语气锚点。"""

    if has_dialogue_source_residue(record):
        return False
    evidence_kind = str(record.get("evidenceKind", "dialogue")).strip().casefold()
    if evidence_kind in {"marriage_dialogue", "roommate_dialogue"}:
        return False
    key = str(record.get("sourceKey", "")).strip().casefold()
    # 全局 voice card 没有关系阶段参数，只能使用无条件的介绍和日常键。
    # Mon4/Mon8 等高好感对白应留在带阶段的 style/speech 检索中，不能泄漏
    # 到陌生阶段；其他带下划线的复合键同样通常是地点、事件或分支对白。
    if key:
        if key == "introduction":
            return not _is_special_dialogue_record(record)
        weekday = re.fullmatch(r"(?:mon|tue|wed|thu|fri|sat|sun)(\d+)?", key)
        if weekday:
            return not weekday.group(1) and not _is_special_dialogue_record(record)
        if "_" in key:
            return False
    return not _is_special_dialogue_record(record) and not has_dialogue_control_residue(
        record.get("text")
    )
