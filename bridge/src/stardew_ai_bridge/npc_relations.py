"""NPC↔NPC 关系表的纯函数层。

关系图的权威来源是游戏数据 `Data/Characters.json` 的 `FriendsAndFamily`：

* value 是本地化引用时（`[LocalizedText Strings\\Characters:Relative_Nephew]`），
  亲属关系能精确落到中文 —— 词表见 `Strings/Characters.zh-CN.json` 的 22 个
  `Relative_*`（外甥、侄女、丈夫、女儿……）；
* value 是空串时，表示**关系密切但不是亲属** —— 原版这个字段的语义就是
  「朋友和家人」，空串只是没细分是哪一种朋友（Gus 的 Emily／Pam 就是）。

SVE 角色的 `FriendsAndFamily` 是空的（mod 作者没声明），它们的关系另从
事件对白补：Gus 在索菲亚的 4 心事件里说的是
`"Anything for a close family friend!"`。

2026-09-24 实机背景：索菲亚身上关于格斯的素材只有「格斯做菜时那股香味」，
于是她提到格斯时自己编成了「就是、就是有点怕打扰到他」—— 与事件对白里
「熟到不用点单」的关系完全相反。这一层就是把关系事实变成可注入的数据。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

#: `FriendsAndFamily` 的 value 形如
#: `[LocalizedText Strings\Characters:Relative_Sister]`。
_LOCALIZED_REFERENCE = re.compile(
    r"^\[LocalizedText\s+(?P<path>[^:\]]+):(?P<key>[^\]]+)\]$"
)

#: 非亲属边的说法。原版用它列「朋友和家人」却不写类型，所以空串的含义是
#: 「关系密切，但不是亲属」。
NON_RELATIVE_TERM = "熟人"

#: 引用解得出、词表里却没有时的兜底 —— 至少要说清是亲属。
UNKNOWN_RELATIVE_TERM = "亲戚"


def relation_key(value: str) -> str | None:
    """从 `FriendsAndFamily` 的 value 里取出本地化键。

    空串和普通文本都返回 `None`：它们按「非亲属」处理。
    """

    if not isinstance(value, str):
        return None

    match = _LOCALIZED_REFERENCE.match(value.strip())
    return match.group("key") if match else None


def resolve_relation_term(value: str, strings: Mapping[str, Any]) -> str:
    """把一条 `FriendsAndFamily` 的 value 解析成中文关系词。"""

    key = relation_key(value)
    if key is None:
        return NON_RELATIVE_TERM

    term = strings.get(key)
    if isinstance(term, str) and term.strip():
        return term.strip()

    return UNKNOWN_RELATIVE_TERM


def build_relations(
    characters: Mapping[str, Any],
    strings: Mapping[str, Any],
) -> dict[str, list[dict[str, str]]]:
    """生成 `{角色: [{"npc": 对方, "term": 关系词}, ...]}` 的关系表。

    没有 `FriendsAndFamily`、或者它是空字典的角色不进结果 —— 那表示
    「这份数据里没声明」，不代表「这个角色没有关系」。SVE 角色正是这种情况，
    它们的关系由事件对白另外补上。
    """

    relations: dict[str, list[dict[str, str]]] = {}
    for name, character in characters.items():
        if not isinstance(character, Mapping):
            continue

        family = character.get("FriendsAndFamily")
        if not isinstance(family, Mapping) or not family:
            continue

        entries: list[dict[str, str]] = []
        for other, value in family.items():
            entries.append(
                {
                    "npc": str(other),
                    "term": resolve_relation_term(
                        value if isinstance(value, str) else "",
                        strings,
                    ),
                }
            )
        relations[str(name)] = entries

    return relations


def merge_relations(
    generated: Mapping[str, list[dict[str, str]]],
    extras: Mapping[str, list[dict[str, str]]],
) -> dict[str, list[dict[str, str]]]:
    """合并自动生成的关系表与手工策展的关系。

    `extras` 里同一个对手方会覆盖自动生成的条目 —— 手工策展那条带着事件
    对白的证据，信息量一定不小于从 `FriendsAndFamily` 推出来的「熟人」。
    输出按角色名与对手方名排序，保证同一份输入永远得到同一个顺序。
    """

    merged: dict[str, list[dict[str, str]]] = {}
    for name in sorted(set(generated) | set(extras)):
        by_npc: dict[str, dict[str, str]] = {}
        for entry in generated.get(name, []):
            by_npc[str(entry.get("npc", ""))] = dict(entry)
        for entry in extras.get(name, []):
            by_npc[str(entry.get("npc", ""))] = dict(entry)
        merged[name] = [by_npc[npc] for npc in sorted(by_npc)]

    return merged


#: 亲属关系是双向的，但原版数据常常只声明一个方向：`Abigail → Caroline`
#: 写着 `Relative_Mom`，`Caroline → Abigail` 却是空串（2026-09-24 实测
#: `Data/Characters.json` 就是这样）。这张表把「B 是 A 的什么」翻成
#: 「A 是 B 的什么」，值按 **A 本人** 的性别取 ——「妈妈」的反向是「儿子」
#: 还是「女儿」取决于 A，不是 B。
#:
#: 只收无歧义的条目：姐妹／兄弟的长幼、叔伯姑姨的区分在数据里判不出来，
#: 宁可不猜，保持原样。
_RECIPROCAL_KEYS: dict[str, dict[str, str]] = {
    "Relative_Mom": {"Male": "Relative_Son", "Female": "Relative_Daughter"},
    "Relative_Mother": {"Male": "Relative_Son", "Female": "Relative_Daughter"},
    "Relative_Dad": {"Male": "Relative_Son", "Female": "Relative_Daughter"},
    "Relative_Husband": {"*": "Relative_Wife"},
    "Relative_Wife": {"*": "Relative_Husband"},
}


def _gender_of(characters: Mapping[str, Any], name: str) -> str:
    character = characters.get(name)
    if isinstance(character, Mapping):
        raw = character.get("Gender")
        if isinstance(raw, str):
            return raw.strip()
    return ""


def _reciprocal_relation_key(forward_key: str, subject_gender: str) -> str | None:
    mapping = _RECIPROCAL_KEYS.get(forward_key)
    if mapping is None:
        return None

    return mapping.get(subject_gender) or mapping.get("*")


def fill_reciprocal_relations(
    relations: Mapping[str, list[dict[str, str]]],
    characters: Mapping[str, Any],
    strings: Mapping[str, Any],
) -> dict[str, list[dict[str, str]]]:
    """给「单向声明」的亲属关系补上反方向。

    只填空缺（当前是 `NON_RELATIVE_TERM` 的边），**绝不覆盖已经写明的条目** ——
    原版明确声明的措辞属于作者意图，哪怕读起来奇怪（`Pam → Penny` 在原版数据里
    就是 `Relative_LittleBabyGirl`「小女婴」）。判不出反向的边同样保持原样。
    """

    term_by_key: dict[str, str] = {}
    key_by_term: dict[str, str] = {}
    for key, value in strings.items():
        if isinstance(value, str) and value.strip():
            term_by_key[str(key)] = value.strip()
            key_by_term.setdefault(value.strip(), str(key))

    # {对方: {主体: 关系键}} —— 用来反查「B 眼里 A 是什么」
    forward: dict[str, dict[str, str]] = {}
    for name, entries in relations.items():
        for entry in entries:
            other = str(entry.get("npc", ""))
            key = key_by_term.get(str(entry.get("term", "")))
            if other and key:
                forward.setdefault(other, {})[name] = key

    filled: dict[str, list[dict[str, str]]] = {}
    for name, entries in relations.items():
        resolved: list[dict[str, str]] = []
        for entry in entries:
            term = str(entry.get("term", ""))
            other = str(entry.get("npc", ""))

            if term != NON_RELATIVE_TERM:
                resolved.append(dict(entry))
                continue

            forward_key = forward.get(name, {}).get(other)
            reverse_key = (
                _reciprocal_relation_key(
                    forward_key,
                    _gender_of(characters, other),
                )
                if forward_key
                else None
            )
            resolved.append(
                {"npc": other, "term": term_by_key.get(reverse_key or "", term)}
            )

        filled[name] = resolved

    return filled
