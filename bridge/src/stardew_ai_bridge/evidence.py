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
# 季节前缀 + 星期键（`summer_Mon` / `winter_Fri4`）是**日常独白**，不是特殊触发台词。
#
# 2026-09-27：这类键此前被上面的 `_SEASON_DIALOGUE_KEY` 一律拒掉，后果是
# **整批素材没进过索引**。零请求探针（`.tmp/season-key-probe.py`）实测：
# 语料 14063 条里这种形状有 **1283 条（9%）**，`is_model_evidence_record`
# 放行 **0/1283**；把季节前缀剥掉再判，1224 条立刻放行 —— 挡路的就是季节判据本身。
# 涉及 22 个以上角色（Victor 83 / Olivia 70 / Sophia 68 / Haley 48 / Sebastian 43…），
# 其中 Linus 的 `summer_Mon`「今早有些起雾，我看见一只鹭鸟…」这类句正是
# 用户说的"文艺哲理那一批"。
#
# 判据收三种形状（2026-09-27 扩了后两种）：
#   ① 季节前缀 + 星期键（可带心级数字）：`summer_Mon4` —— 日常对白换季
#   ② 季节前缀 + 纯数字：`spring_1`、`winter_25` —— 婚后对白的季节句（序号）
#   ③ 季节前缀 + 人名：`spring_Olivia`、`winter_Lance` —— SVE 婚后对白的季节句
# `winterstar`（冬日星节）、`summer_Mon_dance`（复合分支键）、`summer_festival`
# 仍由上面的判据拒掉。
#
# ⚠ 初版只收 ①，理由是「`spring_13` 是节日日期，不是季节句」。**实测推翻了它**：
# 索引里未识别的季节键有 340 条样本 / 118 个去重键，**全部**来自
# `MarriageDialogue*.json`（Claire 86、Krobus 25、Abigail/Alex/Elliott/Harvey/
# Leah/Maru/Penny/Sam/Sebastian/Shane 各 8~13）与 4 条 `data/compatibility/`，
# **没有一条来自 Festivals/Events**。`spring_13` 的实际身份是 Abigail 婚后
# 春季第 13 句（「嘿，明天就是复活节了，我不会因为我们结婚了而手下留情」），
# 仍是"对玩家说的日常口吻"。代价是婚后阶段的季节句完全拿不到季节优先
# （`speech.select_stage_voice_anchors` 里的 `season_rank` 恒为 1）。
# 探针：`.tmp/season-key-shape-probe.py`、`.tmp/season-key-source-probe.py`。
#
# ③ 用**大小写敏感**的人名形状（首字母大写），这样 `summer_festival` 这类
# 小写节日键不会被顺手收进来 —— 两个正则没法合成一个，正是这个原因。
#
# 季节键**不进**全局静态锚点（那张卡没有季节参数，见 `is_stable_voice_evidence_record`），
# 只进带条件的检索，并在 `speech.select_stage_voice_anchors` 里按当前季节优先。
_SEASON_DAILY_DIALOGUE_KEY = re.compile(
    r"^(?P<season>spring|summer|fall|winter)_"
    r"(?:(?:mon|tue|wed|thu|fri|sat|sun)\d*|\d+)$",
    re.IGNORECASE,
)
_SEASON_NAMED_DIALOGUE_KEY = re.compile(
    r"^(?P<season>(?i:spring|summer|fall|winter))_[A-Z][a-z]+\d*$"
)


def _season_daily_dialogue_match(source_key: object):
    """季节日常键的形状匹配；不是这类键时返回 None。

    两个正则都要试：星期/数字形状允许大小写混写（`WINTER_fri`），
    人名形状必须首字母大写（`spring_Olivia`），合并不了。
    """

    key = str(source_key).strip()
    return _SEASON_DAILY_DIALOGUE_KEY.fullmatch(
        key
    ) or _SEASON_NAMED_DIALOGUE_KEY.fullmatch(key)
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
# `extra_dialogue` 专用的"挖空"词表：**只**含礼物与节日两个语义簇，
# 见 `_is_special_dialogue_key` 的 `relax_scene_context`。
_SCENE_CONTEXT_KEY_WORDS = re.compile(
    r"gift|(?:festival|flowerdance|eggfestival|luau|moonlightjellies|"
    r"stardewvalleyfair|spiritseve|winterstar)",
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


def _is_special_dialogue_path(record: Mapping[str, Any]) -> bool:
    """路径判据：事件脚本目录与节日脚本里的文案不是无条件日常口吻。"""

    path = str(record.get("sourcePath", "")).replace("\\", "/").casefold()
    return bool(
        path == "ucr.json"
        or path.endswith("/ucr.json")
        or "/events/" in path
        or path.startswith("events/")
        or "/code/" in path
        or path.startswith("code/")
        or path.endswith("/festivaldialogue.json")
    )


def _is_special_dialogue_key(
    record: Mapping[str, Any],
    *,
    relax_scene_context: bool = False,
) -> bool:
    """键名判据：键里编码了季节、事件、礼物、地点等触发条件的，都不是日常口吻。

    `relax_scene_context=True` 只给 `Data/ExtraDialogue`（`extra_dialogue`）用，
    它把"**礼物类**"与"**节日类**"两个语义簇从键名里挖掉再判 —— 理由与代价：

    * `Data/ExtraDialogue` 的条目**按定义就是"某个情境下说的话"**，键名里的
      `Gift` / `Festival` 说的是**什么时候说**，而不是"这不是他平时的口吻"。
      `Birdie_NoGift`（「我不需要任何礼物，孩子。你留着就好。」）与
      `Robin_*_Festival`（「好吧，后天，我就着手造你的新{0}。」）都是**本人真说的话**，
      且正好体现性格，因此收下。
    * **只对这一个来源开口，不外溢**：其它来源的 `*Gift*` / `*Festival*` 键**大量是
      模板化台词**（生日、花束、美人鱼吊坠…），放行会稀释语料池，所以照旧排除。
    * **只挖这两个簇**：季节、事件、特殊场景、地点、记忆、关系、触发等其余判据
      **照旧生效** —— 例如 `ArchaeologyHouse_Gunther_Room` 仍因 `archaeologyhouse`
      命中触发词而被排除。
    """

    key = str(record.get("sourceKey", "")).strip()
    if relax_scene_context:
        key = _SCENE_CONTEXT_KEY_WORDS.sub(" ", key)
    # 季节前缀的**日常**键（`summer_Mon4`、`spring_1`、`spring_Olivia`）不属于
    # "特殊触发"：季节说的是这个角色的日常对白按季节换一批，而不是
    # "只有满足某些条件才会说的话"。`winterstar`（节日）等其余季节键照旧被拒。
    seasonal_daily = _season_daily_dialogue_match(key) is not None
    return bool(
        (_SEASON_DIALOGUE_KEY.match(key) and not seasonal_daily)
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


def _is_special_dialogue_record(record: Mapping[str, Any]) -> bool:
    return _is_special_dialogue_path(record) or _is_special_dialogue_key(record)


def dialogue_key_season(source_key: object) -> str:
    """季节专属日常键的季节；不是这类键时返回空串。

    承认的形状与 `_is_special_dialogue_key` 放行的**完全一致**（见
    `_SEASON_DAILY_DIALOGUE_KEY` 的注释）：`summer_Mon4`（日常换季）、
    `spring_1`（婚后对白的季节序号）、`spring_Olivia`（SVE 婚后对白）。
    返回值是小写英文（`spring` / `summer` / `fall` / `winter`），
    与 C# 侧 `gameState.season` 的闭集一致，调用方据此做季节优先
    （`speech.select_stage_voice_anchors`、`ProfileIndexStore` 的两条检索）。
    """

    match = _season_daily_dialogue_match(source_key)
    return match.group("season").casefold() if match else ""


# `gameState.season` 在 C# 侧是小写英文闭集，但评测页/夹具里出现过中文季节字，
# 所以两边都认。认不出来的值按"没给季节"处理（返回空串），而不是静默当成某个季节。
_SEASON_ALIASES: dict[str, str] = {
    "spring": "spring",
    "春": "spring",
    "summer": "summer",
    "夏": "summer",
    "fall": "fall",
    "秋": "fall",
    "autumn": "fall",
    "winter": "winter",
    "冬": "winter",
}


def normalise_season(value: object) -> str:
    """把季节取值归一成小写英文闭集；认不出来返回空串。"""

    if not isinstance(value, str):
        return ""
    return _SEASON_ALIASES.get(value.strip().casefold(), "")


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
    if evidence_kind == "extra_dialogue":
        # `Data/ExtraDialogue` 是**对白表**：里面的条目按定义就是"角色在某个
        # 情境下说的话"（Joja 会员推销、被从矿洞救回、大结局发言……）。
        # CP mod 常把这张表的 patch 写在 `code/` 目录下（SVE 的 Summit 台词
        # 就在 `code/Locations/Summit.json`），那只是 mod 的文件组织方式，
        # **不代表这些条目是事件脚本** —— 路径判据对它们属于误伤，所以只按键名
        # 判断触发条件，并把"礼物类/节日类"两个簇也放开（理由与边界见
        # `_is_special_dialogue_key`）。
        return not _is_special_dialogue_key(record, relax_scene_context=True)
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
