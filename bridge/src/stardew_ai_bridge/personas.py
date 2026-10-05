from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .npc_relations import NON_RELATIVE_TERM
from .source_aliases import normalize_source_marker, source_family, source_matches


_STAGE_KEYS = (
    "stranger",
    "acquaintance",
    "friend",
    "close",
    "dating",
    "married",
    "parent",
)

_DEFAULT_VOICE_STYLE = {
    "tone": "保持核心性格的一致性；资料不足时谨慎、简短，不用夸张语气填空",
    "sentencePattern": [
        "先回应玩家当前问题，再决定是否展开",
        "不确定时明确说明不确定",
        "关系变近后更具体；描写当轮真实发生的身体和感官细节，不编造过去没有发生过的事",
    ],
    "responseRules": [
        "先直接回应玩家当前问题",
        "一次只处理一个话题，不用反问强行延长",
        "没有证据时保留不确定性",
    ],
    "preferredTopics": ["当前地点和日常活动", "已确认的近期事件"],
    "openers": ["嗯，怎么了？"],
    "closers": ["先这样吧。"],
    "avoid": ["把未触发剧情说成事实", "替 NPC 或玩家做决定"],
    "emotionRange": ["平静", "好奇", "谨慎", "亲近时更坦率"],
}

_DEFAULT_STAGE_PROFILES = {
    "stranger": {
        "addressing": "沿用原版或资料中已确认的称谓",
        "openness": "低",
        "topicPool": ["天气", "当前地点", "日常工作"],
        "boundaries": ["不主动谈未确认的私人经历"],
    },
    "acquaintance": {
        "addressing": "称谓保持自然、不过度亲密",
        "openness": "试探",
        "topicPool": ["小镇日常", "已确认的兴趣", "近期见闻"],
        "boundaries": ["被追问时可以结束话题"],
    },
    "friend": {
        "addressing": "可自然使用名字",
        "openness": "愿意分享已确认的近况",
        "topicPool": ["共同经历", "日常压力", "兴趣和计划"],
        "boundaries": ["不替对方承诺或下结论"],
    },
    "close": {
        "addressing": "自然使用名字，语气更放松",
        "openness": "能讨论脆弱或犹豫，但仍保留边界",
        "topicPool": ["长期目标", "彼此的边界", "共同记忆"],
        "boundaries": ["冲突后先确认对方是否愿意继续"],
    },
    "dating": {
        "addressing": "亲密但保持平等",
        "openness": "主动表达在意和顾虑",
        "topicPool": ["共同安排", "约会和兴趣", "对未来的想象"],
        "boundaries": ["亲密不等于控制或共享全部秘密"],
        "intimacyPolicy": {
            "style": "按这个角色一贯的语气表达在意，亲密程度跟着关系走，不突然改用通用的甜言模板",
            "pace": "一次推进一层，先看对方接不接得住",
            "avoidWhen": ["对方没有继续的意思", "当前场合不适合"],
        },
    },
    "married": {
        "addressing": "亲密而平等",
        "openness": "愿意共同讨论生活决定",
        "topicPool": ["共同生活", "家庭分工", "彼此的压力"],
        "boundaries": ["重要决定需要双方确认"],
        "intimacyPolicy": {
            "style": "像过日子的伴侣那样自然，允许直接表达欲望和身体接触，具体方式保持这个角色自己的说话习惯",
            "pace": "可以直接回应，不必层层铺垫，但仍跟着对方的节奏",
            "avoidWhen": ["对方明确拒绝或已经很疲惫", "当前场合不适合"],
        },
    },
    "parent": {
        "addressing": "亲密而平等",
        "openness": "更重视安全、解释和耐心",
        "topicPool": ["家庭日常", "孩子的安全感", "如何保留个人空间"],
        "boundaries": ["不把孩子置于成人冲突或秘密中"],
    },
}

_DEFAULT_KNOWLEDGE_RULES = {
    "canDiscuss": [
        "自己已确认的日常活动",
        "玩家明确告诉 NPC 的近况",
        "运行时已确认且有来源的原版或 Mod 事件",
    ],
    "cannotAssume": [
        "未触发的事件结果",
        "其他人的秘密、感情和家庭决定",
        "没有来源证据的传闻",
    ],
    "secrecy": "资料不足时保留不确定性，不把猜测说成记忆或剧情事实",
}


def _normalise_marker(value: object) -> str:
    return normalize_source_marker(value)


#: 游戏/Mod 里同一个人的**全名写法** → 人设表用的短名。
#:
#: 不归一就会让同一个人拥有**两份 profile**：特质挂一份、语料挂另一份，谁也见不到谁。
#: 2026-09-26 实测（索引 `profiles` 139 条）：`Morris` 与 `MorrisTod`、
#: `Marlon` 与 `MarlonFay`、`Gunther` 与 `GuntherSilvian` 各自并存，而
#: **`MorrisTod` 名下的 165 条日常对白从未出现在 `Morris` 的任何卡里**。
#:
#: 证据不是猜的：这些 npcId 的日常对白 `sourcePath` 目录名就是短名
#: （`assets/CharacterFiles/Dialogue/Morris/Dialogue.json`），且 `MorrisTod`
#: 的初见台词自报「我叫**莫里斯**，是鹈鹕镇 Joja 超市的经理」—— 与
#: `data/personas/sve.json` 的 `Morris` 是同一个人。`scripts/mine_voice_fingerprint.py`
#: 会**逐条复验**这个证据（`_alias_evidence()`），对不上直接报错。
NPC_ID_ALIASES = {
    "MorrisTod": "Morris",
    "MarlonFay": "Marlon",
    "GuntherSilvian": "Gunther",
}

_ALIAS_LOOKUP = {alias.casefold(): target for alias, target in NPC_ID_ALIASES.items()}


def canonical_npc_id(npc_id: object) -> str:
    """将游戏中的别名归并到唯一 NPC ID。"""

    value = str(npc_id).strip()
    lowered = value.casefold()
    for prefix in ("marriagedialogue", "roommatedialogue"):
        if lowered.startswith(prefix) and len(value) > len(prefix):
            value = value[len(prefix) :].strip()
            break
    if value.casefold() in {"wizard", "rasmodia"}:
        return "Wizard"
    return _ALIAS_LOOKUP.get(value.casefold(), value)


# 这是“女性化表达 overlay”的资格集合，不等同于全部可恋爱角色。
# Sophia 等原本就是女性的角色仍可进入恋爱评测，但不能套用本层。
FEMALE_BACHELOR_NPC_IDS = frozenset(
    {
        "Wizard",
        "Shane",
        "Sebastian",
        "Alex",
        "Elliott",
        "Harvey",
        "Sam",
    }
)


def is_female_bachelor_eligible(npc_id: object) -> bool:
    """判断 NPC 是否允许应用 female-bachelors 表达层。"""

    canonical_id = canonical_npc_id(npc_id)
    return any(
        candidate.casefold() == canonical_id.casefold()
        for candidate in FEMALE_BACHELOR_NPC_IDS
    )


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in overlay.items():
        if (
            isinstance(merged.get(key), Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _marker_matches(marker: object, source_mods: set[str]) -> bool:
    return source_matches(marker, source_mods)


def merge_persona(
    persona: Mapping[str, Any],
    source_mods: Iterable[str] = (),
) -> dict[str, Any]:
    """合并已声明的 Mod 覆盖层，并保证未启用的覆盖层不生效。"""

    source_mod_list = list(source_mods)
    overlays = persona.get("modOverlay", {})
    if not isinstance(overlays, Mapping):
        overlays = {}

    merged = copy.deepcopy(dict(persona))
    merged["modOverlay"] = {}
    applied_markers: set[str] = set()
    for source_mod in source_mod_list:
        for marker, overlay in overlays.items():
            marker_key = str(marker)
            # 去重身份用**归一化**标记：`"SVE"` 与 `"  SVE  "` 是同一份覆盖层。
            # 否则它会被 `_deep_merge` 应用两次（嵌套字典会把两处内容都并进来）。
            marker_identity = normalize_source_marker(marker_key)
            if (
                source_family(marker_key) == "femalebachelors"
                and not is_female_bachelor_eligible(persona.get("npcId", ""))
            ):
                continue
            if (
                marker_identity in applied_markers
                or not _marker_matches(marker, {_normalise_marker(source_mod)})
                or not isinstance(overlay, Mapping)
            ):
                continue
            merged = _deep_merge(merged, overlay)
            merged["modOverlay"][marker_key] = copy.deepcopy(dict(overlay))
            applied_markers.add(marker_identity)
    return merged


def _ensure_profile_layers(persona: Mapping[str, Any]) -> dict[str, Any]:
    """为尚未手工细化的角色补充保守默认层，定制字段优先。"""

    enriched = copy.deepcopy(dict(persona))
    voice_style = enriched.get("voiceStyle")
    enriched["voiceStyle"] = _deep_merge(
        _DEFAULT_VOICE_STYLE,
        voice_style if isinstance(voice_style, Mapping) else {},
    )

    stage_profiles = enriched.get("stageProfiles")
    stage_profiles = stage_profiles if isinstance(stage_profiles, Mapping) else {}
    enriched["stageProfiles"] = {
        stage: _deep_merge(
            _DEFAULT_STAGE_PROFILES[stage],
            stage_profiles.get(stage)
            if isinstance(stage_profiles.get(stage), Mapping)
            else {},
        )
        for stage in _STAGE_KEYS
    }

    knowledge_rules = enriched.get("knowledgeRules")
    enriched["knowledgeRules"] = _deep_merge(
        _DEFAULT_KNOWLEDGE_RULES,
        knowledge_rules if isinstance(knowledge_rules, Mapping) else {},
    )
    return enriched


def _mod_markers(payload: Mapping[str, Any], path: Path) -> list[str]:
    markers: list[str] = []
    primary_marker = payload.get("mod", path.stem)
    if isinstance(primary_marker, str) and primary_marker.strip():
        markers.append(primary_marker)

    raw_markers = payload.get("sourceMods", ())
    if isinstance(raw_markers, str):
        raw_markers = [raw_markers]
    if isinstance(raw_markers, Iterable):
        markers.extend(
            str(marker)
            for marker in raw_markers
            if str(marker).strip()
        )
    return list(dict.fromkeys(markers)) or [path.stem]


def _load_npc_relations(path: Path) -> dict[str, list[dict[str, str]]]:
    """读 NPC↔NPC 关系表（`data/npc-relations.json`）。

    文件不存在、读不动、格式不对一律返回空表 —— 关系是增强信息，缺了不该
    影响聊天本身。条目只保留 Mapping，值统一转成字符串。
    """

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

    if not isinstance(payload, Mapping):
        return {}

    relations = payload.get("relations")
    if not isinstance(relations, Mapping):
        return {}

    table: dict[str, list[dict[str, str]]] = {}
    for npc_id, entries in relations.items():
        if not isinstance(entries, list):
            continue
        cleaned = [
            {str(key): str(value) for key, value in entry.items()}
            for entry in entries
            if isinstance(entry, Mapping)
        ]
        if cleaned:
            table[str(npc_id)] = cleaned

    return table

# 「全镇公共常识」的过滤口径：哪些 term 属于**人人都知道**的关系事实。
#
# 2026-10-04 实机问题：索菲亚被问到阿比盖尔时答「阿比……是艾米丽的妹妹吗？」——
# 阿比盖尔是卡罗琳和皮埃尔的女儿，艾米丽的妹妹是海莉。`npc-relations.json` 里
# `Abigail → Caroline/Pierre` 这条记录一直存在，但 `get_persona` 只投影**当前
# 角色自己认识的人**，索菲亚对「阿比盖尔」这个名字零信息，于是她在缺口处编了。
#
# 用户口径（2026-10-04）：「在这种小镇上谁和谁是什么关系，这种基本的应该人人
# 都知道」。所以亲属和公开身份是**公共常识**，不再当作私人记忆。
#
# 排除项是**私人评价**或**信息量为零**的边：
#   · `熟人` / `认识` —— 原版 `FriendsAndFamily` 的空串语义，等于没说什么；
#   · `合不来` —— Olivia↔Pam，这是私人感受不是公共事实；
#   · `接近朋友的人` —— Morris→Andy，措辞本身就说明拿不准。
_TOWN_RELATION_EXCLUDED_TERMS = frozenset({
    NON_RELATIVE_TERM,
    "认识",
    "合不来",
    "接近朋友的人",
})


def _build_town_relations(
    relations: Mapping[str, list[dict[str, str]]],
) -> list[str]:
    """把整张关系表压成「全镇公共常识」的一行行文字。

    输出形如 ``Abigail：Caroline妈妈、Pierre爸爸``。按 NPC 名排序保证顺序稳定
    （同样的输入永远渲染出同样的 prompt，否则缓存和评测口径都会漂）。

    体积实测（2026-10-04）：31 行 / 875 字符。这个量级可以发给每个角色。
    """

    lines: list[str] = []
    for name in sorted(relations):
        parts: list[str] = []
        seen: set[tuple[str, str]] = set()
        for entry in relations[name]:
            other = str(entry.get("npc", "")).strip()
            term = str(entry.get("term", "")).strip()
            if not other or term in _TOWN_RELATION_EXCLUDED_TERMS:
                continue
            key = (other, term)
            if key in seen:
                continue
            seen.add(key)
            parts.append(f"{other}{term}")
        if parts:
            lines.append(f"{name}：{'、'.join(parts)}")
    return lines


class PersonaStore:
    """从 data/personas 下的 JSON 资料加载 NPC 基础资料和 Mod 覆盖层。"""

    def __init__(
        self,
        data_dir: str | Path | None = None,
        relations_path: str | Path | None = None,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else (
            Path(__file__).resolve().parents[3] / "data" / "personas"
        )
        # NPC↔NPC 关系表跟 persona 资料同父目录，但**不能**放进 `data_dir` 里面：
        # `_load()` 把该目录下每个 JSON 的顶层当条目表，关系表的顶层键
        # （`relations`）会凭空变成一个叫 "relations" 的 NPC。
        self._relations = _load_npc_relations(
            Path(relations_path)
            if relations_path is not None
            else self.data_dir.parent / "npc-relations.json"
        )
        # 全镇公共常识：从同一张表派生，和 `_relations` 一起在构造期算一次。
        # 它不随当前角色变化 —— 这是「村里人人都知道的」那一层。
        self._town_relations = _build_town_relations(self._relations)
        self._personas = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        personas: dict[str, dict[str, Any]] = {}
        paths = sorted(
            self.data_dir.glob("*.json"),
            key=lambda path: (path.stem.casefold() != "vanilla", path.name.casefold()),
        )
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entries = payload.get("personas", payload)
            if not isinstance(entries, Mapping):
                continue
            markers = _mod_markers(payload, path)
            is_vanilla = any(
                _normalise_marker(marker) == "vanilla" for marker in markers
            )
            for npc_id, raw_persona in entries.items():
                if not isinstance(raw_persona, Mapping):
                    continue
                npc_key = canonical_npc_id(npc_id)
                if is_vanilla:
                    personas[npc_key] = copy.deepcopy(dict(raw_persona))
                    personas[npc_key].setdefault("npcId", npc_key)
                    personas[npc_key].setdefault("modOverlay", {})
                    continue
                base = personas.setdefault(
                    npc_key,
                    {
                        "npcId": npc_key,
                        "displayName": npc_key,
                        "pronouns": {},
                        "coreTraits": [],
                        "addressing": {},
                        "modOverlay": {},
                    },
                )
                for marker in markers:
                    base.setdefault("modOverlay", {})[marker] = copy.deepcopy(
                        dict(raw_persona)
                    )
        return personas

    def get_persona(
        self,
        npc_id: str,
        source_mods: Iterable[str] = (),
    ) -> dict[str, Any]:
        canonical_id = canonical_npc_id(npc_id)
        key = next(
            (
                candidate
                for candidate in self._personas
                if candidate.casefold() == canonical_id.casefold()
            ),
            canonical_id,
        )
        base = self._personas.get(
            key,
            {
                "npcId": canonical_id,
                "displayName": canonical_id,
                "pronouns": {},
                "coreTraits": [],
                "addressing": {},
                "modOverlay": {},
            },
        )
        merged = _ensure_profile_layers(merge_persona(base, source_mods))
        merged["npcId"] = canonical_id
        # 关系表在这一层挂，而不是在 `_load()` 里 —— 那样得先过 `merge_persona`，
        # 一旦它只挑固定字段，关系就会被静默丢掉（本项目栽过多次的「静默闸门」）。
        relations = self._relations.get(key) or self._relations.get(canonical_id)
        if relations:
            merged["npcRelations"] = relations
        # 全镇公共常识与「我认识谁」是两层：
        # `npcRelations` = 这个角色**自己**的关系（含 note，第一人称知识）；
        # `townRelations` = 谁是谁的谁，**所有角色共用**，用来堵住「没听说过
        # 这个人的角色在缺口处自己编」那个洞（2026-10-04 阿比盖尔事故）。
        if self._town_relations:
            merged["townRelations"] = list(self._town_relations)
        return merged

    def load(self, npc_id: str, source_mods: Iterable[str] = ()) -> dict[str, Any]:
        return self.get_persona(npc_id, source_mods)

    def get(self, npc_id: str, source_mods: Iterable[str] = ()) -> dict[str, Any]:
        return self.get_persona(npc_id, source_mods)
