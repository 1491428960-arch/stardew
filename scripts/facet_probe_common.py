"""面判据探针的公用件：全库语料 + 判面工具（**只读**，不写任何文件）。

被 `audit_facet_wordlist_drift.py` 与 `audit_facet_attribution.py` 共用。
单独放一个文件，是因为"从索引里把语料捞出来、按面判一遍"这件事有两个使用者，
而两份重复的实现迟早会各自演化 —— 本项目为同类问题付过代价。

语料来源：`data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json`。
**不要**换用别的索引做审计：索引之间有覆盖差异，换一份会造出假警报
（`docs/active-work.md` 里记过这个坑）。

用法（一般不必直接跑）：

    import sys; sys.path.insert(0, "scripts")
    from facet_probe_common import corpus, patched, first_hit, hits
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge" / "src"))

from stardew_ai_bridge.stage_policy import _LIFE_FACET_PATTERNS  # noqa: E402

INDEX = (
    ROOT
    / "data"
    / "generated"
    / "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)

NONE_LABEL = "（无面）"
WORK = "工作或手艺"


def corpus(quiet: bool = False) -> list[tuple[str, str]]:
    """全库语料：(npcId, text)。

    索引里语料字段有两种形态（实测）：`styleSamples` / `speechEvidence` 是**扁平
    list**（元素带 `npcId` / `text`），而 `behaviorExamples` 一类可能是 `NPC → list`。
    两种都收，最后按 `(npcId, text)` 去重 —— 两个字段各有 1 万多条且高度重叠。
    """

    raw = json.loads(INDEX.read_text(encoding="utf-8"))
    rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for field, container in raw.items():
        found = 0
        if isinstance(container, dict):
            pairs = [
                (str(item.get("npcId") or npc), str(item.get("text") or "").strip())
                for npc, items in container.items()
                if isinstance(items, list)
                for item in items
                if isinstance(item, dict)
            ]
        elif isinstance(container, list):
            pairs = [
                (str(item.get("npcId") or ""), str(item.get("text") or "").strip())
                for item in container
                if isinstance(item, dict)
            ]
        else:
            continue
        for npc, text in pairs:
            if not text or (npc, text) in seen:
                continue
            seen.add((npc, text))
            rows.append((npc, text))
            found += 1
        if found and not quiet:
            print(f"  语料字段 {field:<18} {found:>6} 条（去重后新增）")
    return rows


def patched(extra: dict[str, list[str]] | None = None) -> list[tuple[str, str]]:
    """把候选词接到指定面的模式末尾。

    ⚠ **模式是逐行拼接的字符串，末尾绝不能多一个 `|`** —— 那会引入一个空分支，
    让该面匹配任意字符串（历史上这一行 `|` 让 117 条测试一起红，且报错伪装成
    量词语义问题）。本函数保证接上去的一定是非空分支。
    """

    result: list[tuple[str, str]] = []
    for name, pattern in _LIFE_FACET_PATTERNS:
        words = (extra or {}).get(name)
        if words:
            joined = "|".join(word for word in words if word)
            if joined:
                pattern = f"{pattern}|{joined}"
        result.append((name, pattern))
    return result


def first_hit(text: str, patterns: list[tuple[str, str]]) -> str | None:
    """主面：**按声明顺序**第一个命中的面（与 `_facet_of_topic` 同规则）。"""

    for name, pattern in patterns:
        if re.search(pattern, text):
            return name
    return None


def hits(text: str, patterns: list[tuple[str, str]]) -> set[str]:
    """命中即算的面集合（与 `_facet_hits` 同规则）。"""

    return {name for name, pattern in patterns if re.search(pattern, text)}
