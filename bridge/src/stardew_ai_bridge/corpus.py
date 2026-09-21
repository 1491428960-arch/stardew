"""对白语料的统一提取与离线导出。

这个模块只负责把可追溯的对白证据整理成稳定 JSON，不负责调用模型，也不做向量化。
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .profile_index import _load_json
from .source_aliases import normalize_source_marker


_DIALOGUE_PREFIX = "characters/dialogue/"
_LOCALE_SUFFIX = re.compile(r"\.[a-z]{2}(?:-[a-z]{2})?$", re.IGNORECASE)
_I18N_TOKEN = re.compile(
    r"\{\{\s*i18n\s*:\s*([^{}|]+?)"
    r"(?:\s+\{\{[^{}]*\}\})?(?:\s*\|[^{}]*)?\s*\}\}",
    re.IGNORECASE,
)
_I18N_DYNAMIC_PREFIX = re.compile(
    r"\{\{\s*i18n\s*:\s*([^{}|]*?)(?P<delimiter>\{\{|\||\}\})",
    re.IGNORECASE,
)
_I18N_REFERENCE = re.compile(r"\{\{\s*i18n\s*:", re.IGNORECASE)
_DEFAULT_I18N_CANDIDATE_LIMIT = 24
_WEEKDAY_DIALOGUE_KEY = re.compile(
    r"^(?:(?:spring|summer|fall|winter)_)?"
    r"(?:mon|tue|wed|thu|fri|sat|sun)(?P<hearts>\d+)?$",
    re.IGNORECASE,
)
_DIALOGUE_MARKER = re.compile(r"#?\$[A-Za-z0-9]+#?", re.IGNORECASE)
_DIALOGUE_QUERY = re.compile(r"#?\$(?:q|d)[^#|]*#?", re.IGNORECASE)
_DIALOGUE_EXPRESSION = re.compile(r"\$\{([^{}]*)\}")
_DIALOGUE_TOKEN = re.compile(r"\{\{[^{}]*\}\}")
_DIALOGUE_DIRECTIVE = re.compile(r"%[A-Za-z0-9_]+")
_DIALOGUE_INPUT_SEPARATOR = re.compile(r"\binputSeparator\s*=.*$", re.IGNORECASE)
_DIALOGUE_ACTION = re.compile(r"\*[^*\r\n]*\*")
_DIALOGUE_NARRATION = re.compile(r"^\s*%")
_DIALOGUE_LONE_DOLLAR = re.compile(r"(?<![A-Za-z0-9])\$(?![A-Za-z0-9])")
_SINGLE_LETTER_RESIDUE = re.compile(
    r"(?<=[。！？；：，、…])\s*[A-Za-z]\s*(?=[\u4e00-\u9fff])"
)
_STARDEW_BRANCH_HEADER = re.compile(
    r"(?<![A-Za-z0-9_])\d+\s+-?\d+\s+[A-Za-z][A-Za-z0-9_]*\b"
)
_STARDEW_BRANCH_SEPARATOR = "\x00"
_EVENT_TARGET_PREFIX = "data/events/"
_EVENT_COMMAND = re.compile(
    r'(?:^|/)(?P<command>speak|end\s+dialogue|textAboveHead)\s+'
    r'(?P<speaker>[A-Za-z][A-Za-z0-9_]*)\s+"(?P<text>(?:\\.|[^"\\])*)"',
    re.IGNORECASE,
)
_EVENT_ID_PREFIX = re.compile(r"^\s*(?P<event_id>\d+)(?:_|/|$)")
# 事件脚本指令（`/pause 500`、`/faceDirection Sophia 3`…）。用来判断
# `Data/ExtraDialogue` 的某个值是不是"台词 + 整段脚本"的混合体，
# 见 `_extra_dialogue_texts`。前导字符限定为空白/引号/行首，避免误伤
# 正文里的斜杠（`24/7`、`and/or` 都不会命中）。
_EVENT_SCRIPT_DIRECTIVE = re.compile(r'(?:^|[\s"/])/[A-Za-z][A-Za-z0-9_]*')
_EVENT_PARTICIPANT_CONDITION = re.compile(
    r"/(?P<condition>[fo])\s+(?P<npc>[A-Za-z][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_NON_PLAYER_EVENT_SPEAKERS = {"farmer", "player", "host"}

# --- 证据类型（evidenceKind）：三种来源，缺一不可 ---------------------------
#
# 2026-09-23（方案 A+B）把这里从两种来源补成三种。这三种是**说话人身份的
# 分类**，不是文件格式的分类，用途是：日后若发现"某条台词在低关系阶段说出来
# 违和"，能**按来源**把它筛出来（体检报告 §5.3 的 13 条 HIGH 素材全是婚后台词，
# 就是同一个问题的另一面）。
#
# | evidenceKind       | 中文名   | 来源                                              |
# |--------------------|----------|---------------------------------------------------|
# | `dialogue`         | 日常对白 | `Characters/Dialogue/*`（含 CP 覆盖）              |
# | `extra_dialogue`   | 场景台词 | `Data/ExtraDialogue`（vanilla 表 + CP 覆盖）       |
# | `event_dialogue`   | 事件台词 | `Data/Events/*` 的 `speak <NPC> "…"` 脚本          |
# | `marriage_dialogue`| 婚后对白 | `MarriageDialogue*`（另有关系阶段门控）            |
# | `roommate_dialogue`| 室友对白 | `RoommateDialogue*`（同上）                        |
#
# **为什么 `extra_dialogue` 值得单独一类**：它是**特定场景触发**的对白
# （买了你的东西、你被从矿洞救回来、大结局发言……），语义与"他平时怎么说话"
# 不同；但它确实是**角色本人在说话**，而且常常是塑造角色的关键语料
# （Birdie 的身世、Morris 的 Joja 主业对白都只在这里）。
_EXTRA_DIALOGUE_EVIDENCE_KIND = "extra_dialogue"
_EXTRA_DIALOGUE_TARGET_PREFIX = "data/extradialogue"
_EXTRA_DIALOGUE_FILENAME = re.compile(
    r"^extradialogue(?:\.[a-z]{2}(?:-[a-z]{2})?)?\.json$",
    re.IGNORECASE,
)
_CHARACTERS_TARGET = "data/characters"
_EXTRA_DIALOGUE_TRAILING_DIGITS = re.compile(r"\d+$")
# `rainy.json` 是原版的"雨天对白"伪 NPC，不是可称呼的角色（与
# `profile_index._is_catalog_npc_id` 保持同一口径）。
_EXTRA_DIALOGUE_NON_NPC_KEYS = frozenset({"rainy"})


def _normalise_source_path(source_path: str | Path) -> str:
    """把来源路径变成可提交的相对路径，避免泄露本机绝对路径。"""

    value = str(source_path).replace("\\", "/").strip()
    if not value:
        return "unknown.json"
    if value.startswith("/") or (len(value) >= 3 and value[1] == ":"):
        value = value.rsplit("/", 1)[-1]
    return value.lstrip("./") or "unknown.json"


def _locale_candidates(locale: str) -> list[str]:
    value = str(locale).strip().replace("_", "-")
    candidates: list[str] = []
    for candidate in (value, value.split("-", 1)[0], "default"):
        if candidate and candidate.casefold() not in {
            existing.casefold() for existing in candidates
        }:
            candidates.append(candidate)
    return candidates


def _ordered_i18n_catalogs(
    catalogs: Mapping[str, Mapping[str, Any]],
    locale: str,
) -> list[Mapping[str, Any]]:
    ordered_catalogs: list[Mapping[str, Any]] = []
    for candidate in _locale_candidates(locale):
        for catalog_name, catalog in catalogs.items():
            if str(catalog_name).casefold() == candidate.casefold():
                ordered_catalogs.append(catalog)
                break
    return ordered_catalogs


def _lookup_i18n_value(
    key: str,
    catalogs: Iterable[Mapping[str, Any]],
) -> str | None:
    folded_key = key.casefold()
    for catalog in catalogs:
        value = catalog.get(key)
        if isinstance(value, str):
            return value
        for raw_key, raw_value in catalog.items():
            if str(raw_key).casefold() == folded_key and isinstance(raw_value, str):
                return raw_value
    return None


def resolve_i18n_text(
    text: str,
    catalogs: Mapping[str, Mapping[str, Any]],
    *,
    locale: str = "zh-CN",
) -> str:
    """解析 Content Patcher 的 i18n 引用，未找到时保留原占位符。"""

    if not isinstance(text, str) or not text:
        return text
    ordered_catalogs = _ordered_i18n_catalogs(catalogs, locale)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = _lookup_i18n_value(key, ordered_catalogs)
        if value is not None:
            return value
        return match.group(0)

    return _I18N_TOKEN.sub(replace, text)


def resolve_i18n_candidates(
    text: str,
    catalogs: Mapping[str, Mapping[str, Any]],
    *,
    locale: str = "zh-CN",
    max_candidates: int = _DEFAULT_I18N_CANDIDATE_LIMIT,
) -> list[dict[str, str]]:
    """为依赖运行时表达式的 i18n 引用收集可审计候选，不猜测唯一结果。

    Content Patcher 会在游戏运行时展开 ``Random``、季节、日期和条件表达式，
    因此静态导出不能把其中一句伪装成最终台词。这里仅按动态键前缀枚举目录中
    已存在的键，并按键名稳定排序、限制数量；没有匹配项时返回空数组。
    """

    if not isinstance(text, str) or not text or max_candidates <= 0:
        return []
    ordered_catalogs = _ordered_i18n_catalogs(catalogs, locale)
    if not ordered_catalogs:
        return []

    prefixes: dict[str, str] = {}
    for match in _I18N_DYNAMIC_PREFIX.finditer(text):
        if match.group("delimiter") != "{{":
            continue
        prefix = match.group(1).strip()
        if not prefix:
            continue
        prefixes.setdefault(prefix.casefold(), prefix)

    candidates: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    # 每个动态键族单独限量，避免一条同时包含多个分支的对白只留下第一个族。
    for folded_prefix in sorted(prefixes):
        prefix = prefixes[folded_prefix]
        family: dict[tuple[str, str], str] = {}
        for catalog in ordered_catalogs:
            for raw_key in catalog:
                key = str(raw_key).strip()
                if not key or not key.casefold().startswith(folded_prefix):
                    continue
                value = _lookup_i18n_value(key, ordered_catalogs)
                if value is not None and not _I18N_REFERENCE.search(value):
                    family[(key.casefold(), key)] = value
        family_count = 0
        for (_, key), value in sorted(family.items(), key=lambda item: item[0]):
            folded_key = key.casefold()
            if folded_key in seen_keys:
                continue
            candidates.append({"key": key, "text": value})
            seen_keys.add(folded_key)
            family_count += 1
            if family_count >= max_candidates:
                break
    return candidates


def _split_dialogue_control_flow(text: str) -> list[str]:
    """在不拆开 ``${男^女}`` 和 ``{{...}}`` 表达式的前提下拆分分支。"""

    # 部分导出的 Stardew 原版对白把条件分支头直接串在同一个值里，
    # 例如 ``6 0 Wed_01_02``。它不是 NPC 台词，但必须作为边界处理，
    # 否则整个控制脚本会被当成一条可模仿的长句。
    text = _STARDEW_BRANCH_HEADER.sub(_STARDEW_BRANCH_SEPARATOR, text)
    branches: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("${", index):
            end = text.find("}", index + 2)
            if end >= 0:
                current.append(text[index : end + 1])
                index = end + 1
                continue
        if text.startswith("{{", index):
            end = text.find("}}", index + 2)
            if end >= 0:
                current.append(text[index : end + 2])
                index = end + 2
                continue
        if text[index] == _STARDEW_BRANCH_SEPARATOR:
            branches.append("".join(current))
            current = []
            index += 1
            continue
        if text.startswith("||", index):
            branches.append("".join(current))
            current = []
            index += 2
            continue
        if text[index] in {"^", "|"}:
            branches.append("".join(current))
            current = []
            index += 1
            continue
        current.append(text[index])
        index += 1
    branches.append("".join(current))
    return branches


def _clean_dialogue_branch(text: str) -> str:
    # 某些 Content Patcher 的随机表达式在静态展开时会留下
    # ``inputSeparator=...}}`` 控制残渣；这不是 NPC 台词，不能进入模仿样本。
    if _DIALOGUE_NARRATION.match(text):
        # ``%……`` 是“NPC 没有理你”或事件旁白分支，不是 NPC 的说话内容。
        return ""
    text = _DIALOGUE_INPUT_SEPARATOR.sub("", text)
    value = _DIALOGUE_EXPRESSION.sub(
        lambda match: match.group(1).split("^", 1)[0], text
    )
    value = _DIALOGUE_TOKEN.sub(" ", value)
    value = _DIALOGUE_QUERY.sub(" ", value)
    value = _DIALOGUE_MARKER.sub(" ", value)
    value = _DIALOGUE_DIRECTIVE.sub(" ", value)
    value = _DIALOGUE_ACTION.sub(" ", value)
    value = value.replace("*", " ")
    value = _DIALOGUE_LONE_DOLLAR.sub(" ", value)
    value = value.replace("@", "你")
    # 个别中文导出会在中文句间混入 OCR/编码残片（例如“…… e 你”）。
    # 只清理夹在中文标点与中文之间的单个拉丁字母，避免误删真正的英文术语。
    value = clean_dialogue_noise(value)
    value = re.sub(r"#+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_dialogue_noise(text: str) -> str:
    """清理已生成索引中夹在中文句间的单字母残片。"""

    if not isinstance(text, str):
        return text
    return _SINGLE_LETTER_RESIDUE.sub("", text)


def clean_dialogue_variants(text: str) -> list[str]:
    """提取可供模型模仿的对白变体，同时保留语料原文供审计。"""

    if not isinstance(text, str) or not text.strip():
        return []
    variants: list[str] = []
    seen: set[str] = set()
    for branch in _split_dialogue_control_flow(text):
        cleaned = _clean_dialogue_branch(branch)
        if cleaned and cleaned.casefold() not in seen:
            variants.append(cleaned)
            seen.add(cleaned.casefold())
    return variants


def _apply_i18n_resolution(
    record: dict[str, Any],
    raw_text: str,
    i18n_catalogs: Mapping[str, Mapping[str, Any]] | None,
    locale: str,
) -> None:
    """把 CP 的 i18n 模板就地解析进 record（解析不唯一时只留候选）。

    三处提取（事件台词、日常对白、场景台词）用的是同一套规则：能唯一解析就写
    `resolvedText`（并由它重算 `dialogueVariants`），只能枚举就写
    `dynamicCandidates`，绝不把未解析的模板当成最终台词。
    """

    if not i18n_catalogs:
        return
    resolved_text = resolve_i18n_text(raw_text, i18n_catalogs, locale=locale)
    if resolved_text != raw_text and not _I18N_REFERENCE.search(resolved_text):
        resolved_variants = clean_dialogue_variants(resolved_text)
        if resolved_variants:
            record["resolvedText"] = resolved_variants[0]
        if len(resolved_variants) > 1:
            record["dialogueVariants"] = resolved_variants
        return
    dynamic_candidates = resolve_i18n_candidates(raw_text, i18n_catalogs, locale=locale)
    if dynamic_candidates:
        record["dynamicCandidates"] = dynamic_candidates


def classify_dialogue_target(target: str) -> tuple[str, str]:
    """从 Content Patcher target 得到 NPC ID 和证据类型。

    `Characters/Dialogue` 用文件名（= target 的末段）当 npcId；
    `MarriageDialogue` / `RoommateDialogue` 还原成婚后 / 室友类型。

    `Data/ExtraDialogue` **在此返回空的 npcId**：那张表的 npcId 不存在于
    target 里，而要**逐键**从键名推断（`_extra_dialogue_owner`）。这里只负责
    声明它的证据类型（`extra_dialogue` = 场景台词），真正入库在
    `_extract_extra_dialogue_records`。

    2026-09-23 之前这里对 `Data/ExtraDialogue` 直接返回空值、由调用方
    `continue` 跳过，于是 vanilla 的 147 条与 SVE 写进去的 19 条**一条都没进索引**
    —— Birdie 的 15 条台词、Morris 的 Joja 主业对白都因此消失。方案 A（vanilla 表
    加第三个入口）与方案 B（本函数认识 CP 的 `Data/ExtraDialogue` target）
    同日落地，两者共用同一套键名归属规则。
    """

    normalised = str(target).replace("\\", "/").strip("/")
    if normalised.casefold().startswith(_EXTRA_DIALOGUE_TARGET_PREFIX):
        return "", _EXTRA_DIALOGUE_EVIDENCE_KIND
    if normalised.casefold().startswith(_DIALOGUE_PREFIX):
        dialogue_target = normalised[len(_DIALOGUE_PREFIX):]
    else:
        # 派生索引的 sourcePath 通常只保留文件名，例如
        # ``MarriageDialogueElliott.zh-CN.json``。旧索引没有保存
        # evidenceKind 时仍应能从这个路径恢复婚后来源，而不是把它当
        # 成普通日常对白。
        dialogue_target = normalised.rsplit("/", 1)[-1]
        if not dialogue_target.casefold().startswith(
            ("marriagedialogue", "roommatedialogue")
        ):
            return "", ""
    lowered = dialogue_target.casefold()
    if lowered.startswith("marriagedialogue"):
        return dialogue_target[len("MarriageDialogue"):], "marriage_dialogue"
    if lowered.startswith("roommatedialogue"):
        return dialogue_target[len("RoommateDialogue"):], "roommate_dialogue"
    return dialogue_target, "dialogue"


def _is_extra_dialogue_target(target: str) -> bool:
    normalised = str(target).replace("\\", "/").strip("/").casefold()
    return normalised.startswith(_EXTRA_DIALOGUE_TARGET_PREFIX)


# --- 场景台词（Data/ExtraDialogue）的键名归属 -------------------------------
#
# 那张表的键**不含 target 前缀信息**，只能逐键判断"这是谁在说"。实测（本机
# zh-CN，2026-09-23）147 个键分两类：
#
#   · **有主键**：`<NPC><数字>`（`Birdie0`…`Birdie14`）或 `<NPC>_<后缀>`
#     （`Morris_Greeting`）—— 键名直接写着说话人。
#   · **无主键**：`PurchasedItem_*`、`NewChild_*`、`Spouse_*`、`Town_*`、
#     `SummitEvent_*` 这类**场景键**，说话人由运行时上下文决定
#     （谁跟你说话、谁是你的配偶）。**不猜、不收** —— 猜错比漏收更坏，
#     它会把别人的话当成本人的口吻喂进语气库。
#
# 判"某一段是不是 NPC 名"必须有**名单**，而名单不能靠猜。三处权威来源：
#   1. `<游戏>/Content (unpacked)/Data/Characters.json` 的键（游戏自己的 NPC 定义，
#      写法与 `Characters/Dialogue/*.json` 的文件名一致 —— 所以 `Mister Qi`
#      能并回已有 profile，而不是多出一个 `MisterQi`）；
#   2. 同目录树 `Strings/NPCNames.<locale>.json` 的键 —— 它**补上了
#      `Data/Characters.json` 没有的 `ProfessorSnail`**；
#   3. CP mod 里 `Target: Data/Characters` 的 Entries 键 —— SVE 的
#      Sophia / Victor / Olivia / Claire / Lance / Apples / Scarlett 只在这里。
#
# 三处都读不到时**一条都不收**并出警告：没有名单就无法把"角色键"和"场景键"
# 分开，此时沉默地瞎收会污染整个语气库。
def _normalised_npc_key(value: object) -> str:
    """NPC 名的比较键：去掉空格与标点后再折叠大小写（`Mister Qi` ≡ `MisterQi`）。"""

    return normalize_source_marker(value)


def _register_npc_name(names: dict[str, str], raw_name: object) -> None:
    """登记一个 NPC 名；同一比较键只保留第一次出现的写法。"""

    name = str(raw_name).strip()
    if not name:
        return
    key = _normalised_npc_key(name)
    if not key or key in _EXTRA_DIALOGUE_NON_NPC_KEYS:
        return
    if name.casefold().startswith(("marriagedialogue", "roommatedialogue")):
        return
    names.setdefault(key, name)


def _load_vanilla_npc_names(
    root: Path,
    *,
    locale: str,
    warnings: list[str],
) -> dict[str, str]:
    """从已解包的游戏数据里读 NPC 名单（`Data/Characters` + `Strings/NPCNames`）。"""

    names: dict[str, str] = {}
    bases = [root]
    if root.parent != root:
        bases.append(root.parent)
    candidates: list[Path] = []
    for base in bases:
        candidates.append(base / "Data" / "Characters.json")
        candidates.append(base / "Characters.json")
    for base in bases:
        for candidate in _locale_candidates(locale):
            stem = (
                "NPCNames"
                if candidate == "default"
                else f"NPCNames.{candidate}"
            )
            candidates.append(base / "Strings" / f"{stem}.json")

    for path in candidates:
        if not path.is_file():
            continue
        payload = _read_payload(path, path.parent, warnings)
        if not isinstance(payload, Mapping):
            continue
        for raw_name in payload:
            _register_npc_name(names, raw_name)
    if not names:
        warnings.append(
            "Data/ExtraDialogue 缺少 NPC 名单（Data/Characters.json / "
            "Strings/NPCNames），这些场景台词一条都不会入库"
        )
    return names


def _collect_mod_npc_names(
    payload: Mapping[str, Any],
    names: dict[str, str],
) -> None:
    """收集 CP `Data/Characters` patch 声明的 NPC 名（SVE 原创角色只在这里）。"""

    changes = payload.get("Changes")
    if not isinstance(changes, list):
        return
    for change in changes:
        if not isinstance(change, Mapping):
            continue
        if str(change.get("Action", "")).casefold() != "editdata":
            continue
        if not any(
            str(target).replace("\\", "/").strip("/").casefold()
            == _CHARACTERS_TARGET
            for target in _iter_dialogue_targets(change.get("Target", ""))
        ):
            continue
        entries = change.get("Entries")
        if not isinstance(entries, Mapping):
            continue
        for raw_name in entries:
            _register_npc_name(names, raw_name)


def _extra_dialogue_owner(
    source_key: str,
    npc_names: Mapping[str, str],
    *,
    any_segment: bool,
) -> str:
    """从 `Data/ExtraDialogue` 的键名判断说话人；判不出时返回空串。

    `any_segment=False` 只认**第一段**（vanilla 表的口径：`Birdie0`、
    `Morris_Greeting` 是角色键，而 `PurchasedItem_1_QualityHigh`、
    `SummitEvent_Intro_Lewis` 是场景键 —— 后者虽然键里也出现角色名，
    但那是"大结局里 Lewis 的一段独白"，不是他平时的说话方式，本轮按
    任务口径不收）。

    `any_segment=True` 扫描**所有段**，给 CP 覆盖用：SVE 往这张表写的是
    `SummitEvent_Dialogue3_Sophia` / `ArchaeologyHouse_Gunther_Room` ——
    角色名在**尾部或中间**，第一段永远是事件名。
    """

    key = str(source_key).strip()
    if not key or not npc_names:
        return ""
    segments = [segment for segment in key.split("_") if segment]
    if not segments:
        return ""
    for segment in segments if any_segment else segments[:1]:
        for shape in (segment, _EXTRA_DIALOGUE_TRAILING_DIGITS.sub("", segment)):
            if not shape:
                continue
            owner = npc_names.get(_normalised_npc_key(shape))
            if owner:
                return owner
    return ""


def _is_event_target(target: str) -> bool:
    normalised = str(target).replace("\\", "/").strip("/").casefold()
    return normalised.startswith(_EVENT_TARGET_PREFIX)


def _event_id_from_source_key(source_key: str) -> str:
    match = _EVENT_ID_PREFIX.match(str(source_key))
    return match.group("event_id") if match else ""


def _unescape_event_text(text: str) -> str:
    # 事件脚本中的引号通常已经由 JSON 解码还原；这里只处理命令参数中
    # 仍残留的转义引号和反斜杠，不对中文做 unicode_escape 二次解码。
    return str(text).replace(r"\"", '"').replace(r"\\", "\\")


def _event_participants(source_key: str, raw_script: str) -> list[str]:
    """提取事件涉及的 NPC，而不把玩家或旁白误算成角色。"""

    participants: list[str] = []
    seen: set[str] = set()

    def append(value: str) -> None:
        npc_id = str(value).strip()
        if not npc_id or npc_id.casefold() in _NON_PLAYER_EVENT_SPEAKERS:
            return
        folded = npc_id.casefold()
        if folded in seen:
            return
        seen.add(folded)
        participants.append(npc_id)

    # /f 和 /o 是事件键中最常见的角色条件；即使角色没有发言，
    # 也必须保留为事件参与者，避免用“实际发言者”冒充完整事件阵容。
    for match in _EVENT_PARTICIPANT_CONDITION.finditer(str(source_key)):
        append(match.group("npc"))
    for match in _EVENT_COMMAND.finditer(str(raw_script)):
        append(match.group("speaker"))
    return participants


def _event_conditions(source_key: str) -> dict[str, str]:
    """保留原始事件键，供审计触发条件，不猜测游戏内部语义。"""

    value = str(source_key).strip()
    return {"raw": value} if value else {}


def _extract_event_dialogue_records(
    entries: Mapping[Any, Any],
    *,
    source_mod: str,
    source_path: str | Path,
    i18n_catalogs: Mapping[str, Mapping[str, Any]] | None = None,
    locale: str = "zh-CN",
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    safe_source_mod = str(source_mod).strip() or "unknown"
    safe_source_path = _normalise_source_path(source_path)
    for raw_key, raw_script in entries.items():
        source_key = str(raw_key).strip()
        if not source_key or not isinstance(raw_script, str) or not raw_script.strip():
            continue
        event_id = _event_id_from_source_key(source_key)
        participants = _event_participants(source_key, raw_script)
        for line_index, match in enumerate(_EVENT_COMMAND.finditer(raw_script), start=1):
            speaker = match.group("speaker").strip()
            if speaker.casefold() in _NON_PLAYER_EVENT_SPEAKERS:
                continue
            raw_text = _unescape_event_text(match.group("text")).strip()
            if not raw_text:
                continue
            record: dict[str, Any] = {
                "sampleId": (
                    f"{safe_source_mod}:{safe_source_path}:{source_key}:"
                    f"event-line-{line_index}"
                ),
                "npcId": speaker,
                "sourceMod": safe_source_mod,
                "sourcePath": safe_source_path,
                "sourceKey": source_key,
                "text": raw_text,
                "evidenceKind": "event_dialogue",
                "eventLineIndex": line_index,
                "conditions": {"eventId": event_id} if event_id else {},
                "eventConditions": _event_conditions(source_key),
                "participants": participants,
            }
            if event_id:
                record["eventId"] = event_id
            variants = clean_dialogue_variants(raw_text)
            if variants and (len(variants) > 1 or variants[0] != raw_text.strip()):
                record["dialogueVariants"] = variants
            _apply_i18n_resolution(record, raw_text, i18n_catalogs, locale)
            records.append(record)
    return records


def _iter_dialogue_targets(raw_target: object) -> Iterable[str]:
    if isinstance(raw_target, str):
        for target in raw_target.split(","):
            if target.strip():
                yield target.strip()
        return
    if isinstance(raw_target, (bytes, bytearray, Mapping)):
        return
    if isinstance(raw_target, Iterable):
        for target in raw_target:
            if isinstance(target, str):
                yield target


def infer_dialogue_conditions(target: str, source_key: str) -> dict[str, str]:
    """推断不会改变原文的最小条件标签。"""

    _, evidence_kind = classify_dialogue_target(target)
    if evidence_kind in {"marriage_dialogue", "roommate_dialogue"}:
        # Stardew 中 RoommateDialogue 仅用于婚后同居，因此仍属于 married 阶段。
        return {"relationshipStage": "married"}
    match = _WEEKDAY_DIALOGUE_KEY.fullmatch(str(source_key).strip())
    if match:
        hearts = int(match.group("hearts") or 0)
        if hearts >= 8:
            stage = "close"
        elif hearts >= 6:
            stage = "friend"
        elif hearts >= 2:
            stage = "acquaintance"
        else:
            stage = "stranger"
        return {"relationshipStage": stage}
    return {}


def extract_content_patcher_dialogue(
    payload: Mapping[str, Any],
    *,
    source_mod: str,
    source_path: str | Path,
    i18n_catalogs: Mapping[str, Mapping[str, Any]] | None = None,
    locale: str = "zh-CN",
    npc_names: Mapping[str, str] | None = None,
    extra_dialogue_sink: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """提取一个 Content Patcher JSON 中的 EditData 对白。

    `Data/ExtraDialogue` 的条目要**逐键**判断说话人，所以需要 `npc_names`
    （见 `_extra_dialogue_owner`）。`build_dialogue_corpus` 还会传
    `extra_dialogue_sink` 把它们**延后**到所有文件扫完之后再归属：SVE 的角色
    名单在 `code/NPCs/Sophia.json`，按字母序排在 `code/Locations/Summit.json`
    之后 —— 边扫边判会把那 8 条大结局台词整批丢掉。
    """

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    changes = payload.get("Changes", [])
    if not isinstance(changes, list):
        return [], [f"Changes 不是数组：{_normalise_source_path(source_path)}"]

    safe_source_mod = str(source_mod).strip() or "unknown"
    safe_source_path = _normalise_source_path(source_path)
    for change in changes:
        if not isinstance(change, Mapping):
            continue
        if str(change.get("Action", "")).casefold() != "editdata":
            continue
        entries = change.get("Entries", {})
        if not isinstance(entries, Mapping):
            warnings.append(f"对白 Entries 不是对象：{safe_source_path}")
            continue
        for target in _iter_dialogue_targets(change.get("Target", "")):
            if _is_event_target(target):
                records.extend(
                    _extract_event_dialogue_records(
                        entries,
                        source_mod=safe_source_mod,
                        source_path=safe_source_path,
                        i18n_catalogs=i18n_catalogs,
                        locale=locale,
                    )
                )
                continue
            if _is_extra_dialogue_target(target):
                if extra_dialogue_sink is not None:
                    extra_dialogue_sink.append(
                        {
                            "entries": entries,
                            "sourceMod": safe_source_mod,
                            "sourcePath": safe_source_path,
                            "i18nCatalogs": i18n_catalogs,
                            "locale": locale,
                        }
                    )
                    continue
                records.extend(
                    _extract_extra_dialogue_records(
                        entries,
                        npc_names=npc_names or {},
                        source_mod=safe_source_mod,
                        source_path=safe_source_path,
                        any_segment=True,
                        i18n_catalogs=i18n_catalogs,
                        locale=locale,
                    )
                )
                continue
            npc_id, evidence_kind = classify_dialogue_target(target)
            if not npc_id:
                continue
            for raw_key, raw_text in entries.items():
                source_key = str(raw_key).strip()
                if not source_key or not isinstance(raw_text, str) or not raw_text.strip():
                    continue
                record: dict[str, Any] = {
                    "sampleId": f"{safe_source_mod}:{safe_source_path}:{source_key}",
                    "npcId": npc_id,
                    "sourceMod": safe_source_mod,
                    "sourcePath": safe_source_path,
                    "sourceKey": source_key,
                    "text": raw_text,
                    "evidenceKind": evidence_kind,
                    "conditions": infer_dialogue_conditions(target, source_key),
                }
                variants = clean_dialogue_variants(raw_text)
                if variants and (len(variants) > 1 or variants[0] != raw_text.strip()):
                    record["dialogueVariants"] = variants
                _apply_i18n_resolution(record, raw_text, i18n_catalogs, locale)
                records.append(record)
    return _dedupe_records(records), warnings


def _extract_plain_dialogue(
    payload: Mapping[str, Any],
    *,
    npc_id: str,
    source_mod: str,
    source_path: str | Path,
) -> list[dict[str, Any]]:
    entries: Mapping[Any, Any]
    raw_entries = payload.get("Entries")
    if isinstance(raw_entries, Mapping):
        entries = raw_entries
    else:
        entries = payload

    safe_source_mod = str(source_mod).strip() or "unknown"
    raw_npc_id = _LOCALE_SUFFIX.sub("", str(npc_id).strip()) or "unknown"
    dialogue_target = f"Characters/Dialogue/{raw_npc_id}"
    canonical_id, evidence_kind = classify_dialogue_target(dialogue_target)
    if not canonical_id:
        canonical_id = raw_npc_id
        evidence_kind = "dialogue"
    safe_source_path = _normalise_source_path(source_path)
    records: list[dict[str, Any]] = []
    for raw_key, raw_text in entries.items():
        source_key = str(raw_key).strip()
        if not source_key or not isinstance(raw_text, str) or not raw_text.strip():
            continue
        records.append(
            {
                "sampleId": f"{safe_source_mod}:{safe_source_path}:{source_key}",
                "npcId": canonical_id,
                "sourceMod": safe_source_mod,
                "sourcePath": safe_source_path,
                "sourceKey": source_key,
                "text": raw_text,
                "evidenceKind": evidence_kind,
                "conditions": infer_dialogue_conditions(dialogue_target, source_key),
            }
        )
        variants = clean_dialogue_variants(raw_text)
        if variants and (len(variants) > 1 or variants[0] != raw_text.strip()):
            records[-1]["dialogueVariants"] = variants
    return records


def _extract_plain_events(
    payload: Mapping[str, Any],
    *,
    source_mod: str,
    source_path: str | Path,
) -> list[dict[str, Any]]:
    """提取已解包的 vanilla ``Data/Events/*.json``。"""

    if not isinstance(payload, Mapping):
        return []
    return _extract_event_dialogue_records(
        payload,
        source_mod=source_mod,
        source_path=source_path,
    )


def _extra_dialogue_texts(raw_text: str) -> list[str]:
    """把一个 `Data/ExtraDialogue` 值拆成"真正是台词"的若干段。

    绝大多数条目的值就是一句话，原样即可。但 CP mod 会把**整段事件脚本**塞进
    这张表 —— SVE 的 Summit 台词就是：

        {{i18n:Summit.Dialogue.Sophia.01}}"/pause 500/faceDirection farmer 1/
        speak Sophia "每当我情绪低落的时候…"/pause 350/speak Sophia "我喜欢…"

    如果整段照收，`/pause`、`/faceDirection` 会变成"这个角色平时这么说话"。
    两级处理：

    1. 值里有**成对的** `speak "…"` 就按事件脚本的行取台词（与 `Data/Events`
       共用 `_EVENT_COMMAND`），指令与朝向参数一并丢掉；
    2. 引号没闭合（SVE 的 i18n 值常在末尾断掉）时匹配不上，改取**第一个引号
       之前**的部分 —— 那正是脚本之前的那句台词。

    两条都不适用（值里找不到事件指令）时，整值就是那一句话 —— 普通条目走的
    就是这条路径，行为与 `Characters/Dialogue` 完全一致。
    """

    text = str(raw_text)
    if not _EVENT_SCRIPT_DIRECTIVE.search(text):
        return [text]
    lines: list[str] = []
    for match in _EVENT_COMMAND.finditer(text):
        speaker = match.group("speaker").strip()
        if speaker.casefold() in _NON_PLAYER_EVENT_SPEAKERS:
            continue
        line = _unescape_event_text(match.group("text")).strip()
        if line:
            lines.append(line)
    if lines:
        return lines
    head = text.split('"', 1)[0].strip()
    return [head] if head else [text]


def _extract_extra_dialogue_records(
    entries: Mapping[Any, Any],
    *,
    npc_names: Mapping[str, str],
    source_mod: str,
    source_path: str | Path,
    any_segment: bool,
    i18n_catalogs: Mapping[str, Mapping[str, Any]] | None = None,
    locale: str = "zh-CN",
) -> list[dict[str, Any]]:
    """提取 ``Data/ExtraDialogue`` 的**场景台词**（方案 A 与方案 B 共用）。

    与 `Characters/Dialogue` 的差别只在证据类型：那边是 NPC 的日常口吻，
    这边是**特定场景触发**的对白（买了你的东西、你被从矿洞救回来、
    大结局发言……）。两者都入库、都标 `evidenceKind`，因为**它们都是角色
    本人在说话**，而且场景台词往往是塑造角色最有力的那几句 —— Birdie 的
    身世、Morris 的 Joja 主业对白此前一条都不在库里。

    `any_segment` 决定键名归属规则（见 `_extra_dialogue_owner`）：
    vanilla 表用第一段，CP 覆盖要扫所有段（SVE 把角色名写在尾部）。
    """

    records: list[dict[str, Any]] = []
    safe_source_mod = str(source_mod).strip() or "unknown"
    safe_source_path = _normalise_source_path(source_path)
    for raw_key, raw_text in entries.items():
        source_key = str(raw_key).strip()
        if not source_key or not isinstance(raw_text, str) or not raw_text.strip():
            continue
        npc_id = _extra_dialogue_owner(
            source_key,
            npc_names,
            any_segment=any_segment,
        )
        if not npc_id:
            # 没有主人的场景键（`PurchasedItem_*`、`NewChild_*`、`Spouse_*`）：
            # 说话人由运行时上下文决定，不猜、不收。
            continue
        # 值里可能藏着事件脚本，所以先解析 i18n 再决定"这是几句话"。
        resolved_text: str | None = None
        if i18n_catalogs:
            candidate = resolve_i18n_text(raw_text, i18n_catalogs, locale=locale)
            if candidate != raw_text and not _I18N_REFERENCE.search(candidate):
                resolved_text = candidate
        lines = _extra_dialogue_texts(
            resolved_text if resolved_text is not None else raw_text
        )
        for line_index, line in enumerate(lines, start=1):
            sample_id = f"{safe_source_mod}:{safe_source_path}:{source_key}"
            if len(lines) > 1:
                sample_id = f"{sample_id}:line-{line_index}"
            record: dict[str, Any] = {
                "sampleId": sample_id,
                "npcId": npc_id,
                "sourceMod": safe_source_mod,
                "sourcePath": safe_source_path,
                "sourceKey": source_key,
                "text": line,
                "evidenceKind": _EXTRA_DIALOGUE_EVIDENCE_KIND,
                "conditions": infer_dialogue_conditions(safe_source_path, source_key),
            }
            variants = clean_dialogue_variants(line)
            if variants and (len(variants) > 1 or variants[0] != line.strip()):
                record["dialogueVariants"] = variants
            if resolved_text is None:
                # 已经按脚本拆过台词的条目，text 本身就是最终台词；
                # 其余条目仍走通用的 i18n 解析（写 resolvedText 或候选）。
                _apply_i18n_resolution(record, raw_text, i18n_catalogs, locale)
            records.append(record)
    return records


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _select_vanilla_dialogue_paths(
    paths: Iterable[Path],
    root: Path,
    locale: str | None,
) -> list[Path]:
    """按语言选择原版对白；没有目标语言时回退到无后缀文件。"""

    candidates = sorted(paths)
    if locale is None or not str(locale).strip():
        return candidates
    requested = str(locale).strip().replace("_", "-").casefold()
    groups: dict[str, list[Path]] = {}
    for path in candidates:
        relative = path.relative_to(root)
        base_name = _LOCALE_SUFFIX.sub("", path.stem) + path.suffix
        group_key = relative.with_name(base_name).as_posix().casefold()
        groups.setdefault(group_key, []).append(path)

    selected: list[Path] = []
    for group in groups.values():
        exact = [
            path
            for path in group
            if (
                (match := _LOCALE_SUFFIX.search(path.stem)) is not None
                and match.group(0)[1:].replace("_", "-").casefold() == requested
            )
        ]
        if exact:
            selected.extend(exact)
            continue
        selected.extend(path for path in group if not _LOCALE_SUFFIX.search(path.stem))
    return sorted(selected)


def _warn_for_unpacked_sources(root: Path, warnings: list[str]) -> None:
    """报告根下未解包的 ``.xnb`` 来源，**按目录合并成一条**。

    判据是「根下存在 ``.xnb``」，**与有没有同名 JSON 无关**——所以「把 xnb 解包」
    并不能消除这条警告（2026-09-20 核实时纠正过这个误解，它曾写在待办里）。

    像 SVE 的 ``assets/XNBs/`` 有 55 个室内地图 xnb，它们对**对话**索引没有用处，
    逐条报告只会把 55 行噪音灌进 warnings、**让真正的警告被淹没**（与审计工具的
    误报是同一类问题）。因此按目录合并，并保留目录名与数量，信息不丢。
    """
    by_directory: dict[Path, list[Path]] = {}
    for path in sorted(root.rglob("*.xnb")):
        by_directory.setdefault(path.parent, []).append(path)

    for directory, paths in sorted(by_directory.items()):
        relative = _relative_path(directory, root)
        where = "" if relative == "." else f"{relative}/"
        names = "、".join(path.name for path in paths[:3])
        suffix = f" 等 {len(paths)} 个" if len(paths) > 3 else ""
        warnings.append(f"xnb source requires unpacked JSON: {where}{names}{suffix}")


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按来源键去重，保留 Content Patcher 最后一次覆盖的文本。"""

    by_sample_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        sample_id = str(record.get("sampleId", "")).strip()
        if not sample_id:
            continue
        if sample_id not in by_sample_id:
            order.append(sample_id)
        by_sample_id[sample_id] = record
    return [by_sample_id[sample_id] for sample_id in order]


# --- 解析失败时"丢的到底是什么"（2026-09-22 第 6 批） -------------------------
#
# 起因：查 Birdie 为什么 0 条语料时发现，这个导出器的 warnings 只有一句
# `无法解析 JSON：xxx`，与"一个配方表读不出来"完全同级。而真正的情况是
# **`Data/ExtraDialogue` 谁都不扫**——她的 15 条台词一声不响地没了，
# 10 条失败警告混在一起，看不出哪条真的要命。
#
# 当时列了三个修法，**2026-09-23 三个都已落地**：
#
# * **A. vanilla `Data/ExtraDialogue` 入口** —— `build_dialogue_corpus` 的
#   `vanilla_extra_dialogue_root`，按 `<NPC><数字>` / `<NPC>_<后缀>` 归 npcId。
# * **B. Content Patcher 的 `Data/ExtraDialogue` Target** —— 见
#   `_is_extra_dialogue_target` 分支；键名归属要扫**所有段**（SVE 把角色名
#   写在尾部，如 `SummitEvent_Dialogue3_Sophia`）。
# * **C. 让解析失败看得见**（第 6 批先做）—— 失败时附一句"这文件里本来
#   有多少对白 Target"。零重建、零语义变更，只把已有的静默丢弃变成可读。
#
# ⚠ A 与 B 曾经被否掉的理由是"那些是**事件场景台词**，混进 `styleSamples`
# 会把场景台词当日常说话方式"。**这个理由被推翻了**：场景台词不是舞台指示，
# 而是**角色本人在特定情境下说的话**，往往还是塑造角色最有力的那几句 ——
# Birdie 的全部身世、Morris 的 Joja 主业对白都只存在于这里。正确的处理不是
# 不收，而是**收下来并标明来源类型**（`evidenceKind = extra_dialogue`，
# 与日常对白 `dialogue`、事件脚本 `event_dialogue` 三分），
# 这样日后发现"某条场景台词在低关系阶段违和"时能**按来源筛出来**。
#
# 下面两个判据只做**粗筛**：目的是把"丢台词"和"丢别的东西"分开，不复刻
# `classify_dialogue_target` 的精确规则（此刻 JSON 已经解析不了了）。两条口径：
#
# * **对白 Target** = 值里含 `dialogue`（`Characters/Dialogue/*`、`Data/ExtraDialogue`）。
#   事件 Target（`Data/Events/*`）**不计入这个数字**：它走的是另一条提取路径
#   （`_is_event_target` → `_extract_event_dialogue_records`），语义上是事件台词
#   而不是日常对白；混进同一个数字会把警告夸大（实测 SVE 的
#   `code/Other/Monsters.json` 会因此从 0 跳到 52）。
# * 计数按**去重后的不同 Target 值**，与第 5 批 `.tmp/facet-coverage/b5_json_scan.py`
#   的口径一致 —— 按出现次数数会把 Krobus.json 的 3 个对白 Target 报成 14 个，
#   而这条警告的全部意义就是让人一眼判断"要不要紧"，夸大比漏报更坏。
_DIALOGUE_FILE_MARKERS: tuple[str, ...] = (
    "characters/dialogue",
    "data/extradialogue",
    "data/events",
    "marriagedialogue",
    "roommatedialogue",
)
_DIALOGUE_TARGET_MARKERS: tuple[str, ...] = ("dialogue",)
_TARGET_VALUE_PATTERN = re.compile(r'"Target"\s*:\s*"([^"]*)"')


def _dialogue_loss_note(path: Path, relative: str) -> str:
    """解析失败时，从**原始文本**里估一句"这文件本来带多少台词"。

    任何异常都退化成空串：这里是在解释失败原因，不能反过来把导出器弄崩。
    """

    normalised = relative.replace("\\", "/").casefold()
    if any(marker in normalised for marker in _DIALOGUE_FILE_MARKERS):
        return "该文件本身就是对白/事件文件，里面的台词全部丢失"
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    targets = sorted(set(_TARGET_VALUE_PATTERN.findall(raw)))
    if not targets:
        return "该文件里没有对白 Target"
    hits = sum(
        1
        for target in targets
        if any(
            marker in target.replace("\\", "/").casefold()
            for marker in _DIALOGUE_TARGET_MARKERS
        )
    )
    return f"该文件里有 {hits} 个对白 Target（全文共 {len(targets)} 个不同 Target）"


def _read_payload(path: Path, root: Path, warnings: list[str]) -> Mapping[str, Any] | None:
    relative = _relative_path(path, root)
    try:
        return _load_json(path)
    except Exception as exc:  # noqa: BLE001 - exporter must continue past one bad asset
        note = _dialogue_loss_note(path, relative)
        suffix = f"—— {note}" if note else ""
        warnings.append(f"无法解析 JSON：{relative}（{type(exc).__name__}）{suffix}")
        return None


def _load_i18n_catalogs(
    root: Path,
    *,
    locale: str,
    warnings: list[str],
) -> dict[str, Mapping[str, Any]]:
    """读取 Content Patcher 根目录下的 default/语言覆盖字典。"""

    i18n_root = root / "i18n"
    if not i18n_root.is_dir():
        return {}
    catalogs: dict[str, Mapping[str, Any]] = {}
    for candidate in _locale_candidates(locale):
        path = i18n_root / f"{candidate}.json"
        if not path.is_file():
            continue
        payload = _read_payload(path, root, warnings)
        if isinstance(payload, Mapping):
            catalogs[candidate] = payload
    return catalogs


def _manifest_source_mod(root: Path, warnings: list[str]) -> str:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        warnings.append(f"缺少 manifest.json：{root.name}")
        return root.name
    payload = _read_payload(manifest_path, root, warnings)
    unique_id = payload.get("UniqueID") if payload else None
    if isinstance(unique_id, str) and unique_id.strip():
        return unique_id.strip()
    warnings.append(f"manifest.json 缺少 UniqueID：{root.name}")
    return root.name


def build_dialogue_corpus(
    *,
    vanilla_root: str | Path | None = None,
    vanilla_events_root: str | Path | None = None,
    vanilla_extra_dialogue_root: str | Path | None = None,
    mod_roots: Iterable[str | Path] = (),
    locale: str = "zh-CN",
    vanilla_locale: str | None = None,
) -> dict[str, Any]:
    """从已解包 vanilla 对白、事件、场景台词和 Content Patcher 根目录构建语料。

    vanilla 侧有**三个入口**：
      1. 解包的 `Characters/Dialogue/*.json`（用文件名 stem 当 npcId）→ 日常对白；
      2. 解包的 `Data/Events/*.json`（从事件脚本提 `speak <NPC>`）→ 事件台词；
      3. `vanilla_extra_dialogue_root` 下的 `Data/ExtraDialogue*.json`
         （按**键名**归 npcId）→ 场景台词。

    第 3 个入口是 2026-09-23 补的（方案 A）。此前它谁都不扫，于是 Birdie 的 15 条、
    Morris 的 18 条 Joja 主业对白一条都没进库，表现为"这些角色没有台词"。
    参数请指向 `Content (unpacked)/Data`（或更上层）：同目录树的
    `Data/Characters.json` 与 `Strings/NPCNames.<locale>.json` 是**判定
    "某个键说这话的是谁"的名单**，缺了名单就一条都不收。

    `Data/ExtraDialogue` 的**无主键**（`PurchasedItem_*` / `NewChild_*` /
    `Spouse_*`）由运行时上下文决定说话人，本轮不猜、不收。
    """

    corpus: dict[str, Any] = {
        "schemaVersion": 1,
        "records": [],
        "sources": [],
        "warnings": [],
    }
    records: list[dict[str, Any]] = corpus["records"]
    warnings: list[str] = corpus["warnings"]
    sources: list[dict[str, str]] = corpus["sources"]

    if vanilla_root is not None:
        root = Path(vanilla_root)
        if not root.is_dir():
            warnings.append(f"vanilla 根目录不存在：{root.name}")
        else:
            sources.append({"sourceMod": "vanilla", "root": root.name})
            _warn_for_unpacked_sources(root, warnings)
            vanilla_paths = _select_vanilla_dialogue_paths(
                root.rglob("*.json"),
                root,
                vanilla_locale,
            )
            for path in vanilla_paths:
                relative = _relative_path(path, root)
                payload = _read_payload(path, root, warnings)
                if payload is None:
                    continue
                records.extend(
                    _extract_plain_dialogue(
                        payload,
                        npc_id=path.stem,
                        source_mod="vanilla",
                        source_path=relative,
                    )
                )

    if vanilla_events_root is not None:
        root = Path(vanilla_events_root)
        if not root.is_dir():
            warnings.append(f"vanilla 事件根目录不存在：{root.name}")
        else:
            sources.append({"sourceMod": "vanilla", "root": root.name})
            _warn_for_unpacked_sources(root, warnings)
            event_paths = _select_vanilla_dialogue_paths(
                root.rglob("*.json"),
                root,
                vanilla_locale,
            )
            for path in event_paths:
                relative = _relative_path(path, root)
                payload = _read_payload(path, root, warnings)
                if payload is None or not isinstance(payload, Mapping):
                    continue
                records.extend(
                    _extract_plain_events(
                        payload,
                        source_mod="vanilla",
                        source_path=Path("Data") / "Events" / relative,
                    )
                )

    # 场景台词的 NPC 名单在 vanilla 侧先建好，CP 侧的 `Data/ExtraDialogue`
    # （方案 B）会复用它并补充 mod 自己声明的角色。
    npc_names: dict[str, str] = {}
    if vanilla_extra_dialogue_root is not None:
        root = Path(vanilla_extra_dialogue_root)
        if not root.is_dir():
            warnings.append(f"vanilla 场景台词根目录不存在：{root.name}")
        else:
            sources.append({"sourceMod": "vanilla", "root": root.name})
            _warn_for_unpacked_sources(root, warnings)
            npc_names = _load_vanilla_npc_names(
                root,
                locale=vanilla_locale or locale,
                warnings=warnings,
            )
            extra_paths = _select_vanilla_dialogue_paths(
                (
                    path
                    for path in root.rglob("*.json")
                    if _EXTRA_DIALOGUE_FILENAME.match(path.name)
                ),
                root,
                vanilla_locale,
            )
            for path in extra_paths:
                relative = _relative_path(path, root)
                payload = _read_payload(path, root, warnings)
                if payload is None or not isinstance(payload, Mapping):
                    continue
                records.extend(
                    _extract_extra_dialogue_records(
                        payload,
                        npc_names=npc_names,
                        source_mod="vanilla",
                        # 无论 root 指向 `Data` 还是更上层，这张表在游戏里
                        # 都位于 `Data/`，用文件名补出可追溯的完整路径。
                        source_path=Path("Data") / path.name,
                        any_segment=False,
                    )
                )

    # CP 的 `Data/ExtraDialogue` 延后到所有 mod 文件扫完再归属：SVE 的原创角色名
    # （Sophia / Victor / …）定义在 `code/NPCs/*.json`，按字母序排在
    # `code/Locations/Summit.json` 之后。
    pending_extra_dialogue: list[dict[str, Any]] = []
    for raw_root in mod_roots:
        root = Path(raw_root)
        if not root.is_dir():
            warnings.append(f"mod 根目录不存在：{root.name}")
            continue
        source_mod = _manifest_source_mod(root, warnings)
        sources.append({"sourceMod": source_mod, "root": root.name})
        _warn_for_unpacked_sources(root, warnings)
        i18n_catalogs = _load_i18n_catalogs(
            root,
            locale=locale,
            warnings=warnings,
        )
        for path in sorted(root.rglob("*.json")):
            relative = _relative_path(path, root)
            if path.name.casefold() in {"manifest.json", "config.json"}:
                continue
            if "i18n" in {part.casefold() for part in path.parts}:
                continue
            payload = _read_payload(path, root, warnings)
            if payload is None:
                continue
            if isinstance(payload.get("Changes"), list):
                _collect_mod_npc_names(payload, npc_names)
                extracted, extracted_warnings = extract_content_patcher_dialogue(
                    payload,
                    source_mod=source_mod,
                    source_path=relative,
                    i18n_catalogs=i18n_catalogs,
                    locale=locale,
                    npc_names=npc_names,
                    extra_dialogue_sink=pending_extra_dialogue,
                )
                records.extend(extracted)
                warnings.extend(extracted_warnings)

    for pending in pending_extra_dialogue:
        records.extend(
            _extract_extra_dialogue_records(
                pending["entries"],
                npc_names=npc_names,
                source_mod=pending["sourceMod"],
                source_path=pending["sourcePath"],
                any_segment=True,
                i18n_catalogs=pending["i18nCatalogs"],
                locale=pending["locale"],
            )
        )

    records[:] = _dedupe_records(records)
    return corpus


def write_dialogue_corpus(corpus: Mapping[str, Any], output_path: str | Path) -> None:
    """原子写入导出文件。"""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)
