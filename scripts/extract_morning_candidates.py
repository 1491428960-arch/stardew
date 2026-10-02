#!/usr/bin/env python3
"""从语料里挑出可做晨间预设池的候选，并按 `morning.json` 的字段格式排好。

## 为什么需要它

`morning.json` 的开场白**必须逐字取自角色原话**（模块硬约束第 1 条），
而这条由 `test_morning_scenario.py::test_every_opening_traces_back_to_corpus`
机器守着。手写开场白必然会在某个标点、某个控制码上翻车 —— 2026-09-27 扩池子
时就这么翻过一次：跨 `#$e#` 拼了两句，还落了一个性别变体分支。

所以开场白不由人写，由**这个脚本从语料里裁**。人只写 `direction`。

## 裁切规则（都是被守卫逼出来的）

守卫的做法是：把 `opening` 按 `？` 和 `。` 切开，每段 strip 掉 `。，？！！…… `
之后必须 ≥6 字，且**每一段都得是某一条原始记录的子串**。于是：

1. **裁到第一个控制码之前。** `#$e#` `#$b#` `$h` `$s` `@` 这类控制码一旦落在
   片段中间，去掉它就不再是子串；留着它玩家又会看到 `$h`。
   所以干脆只取控制码之前的那一段 —— 这是唯一既安全又不脏的做法。
2. **`！` 不切分。** 守卫只按 `？` 和 `。` 切，所以 `A！B` 是一整段，
   必须整体是子串。裁剪不改变这点，但**不要人工在 `！` 处拼接**。
3. **`resolvedText` 优先。** SVE / RomRas 角色的 `text` 是 i18n 模板
   （`{{i18n:Sophia.CharacterDialogue.061}}`），中文在 `resolvedText`；
   原版角色 `resolvedText` 为空、`text` 本身就是中文。两者都要看。

脚本最后会**自己跑一遍同样的检查**，把过不了的候选直接丢掉并报数 ——
宁可少几条，不要写进去一条要等到测试才发现是假的。

## 用法

    python scripts/extract_morning_candidates.py \
        --corpus artifacts/corpus/20260927-string-eventid/vanilla-sve-rasmodia-dialogue-corpus.json \
        --output .scratch/morning-candidates.json
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: 季节键：`spring_1` / `summer_12` / …（`Data/Characters/Dialogue` 的键）。
_SEASON_KEY = re.compile(r"^(spring|summer|fall|winter)_(\d{1,2})$", re.IGNORECASE)

#: 控制码。`@` 是玩家名占位符，`%` 是 `%noturn` 之类，`^` 是性别变体分隔。
#: **顺序无关**，因为只用来找「第一个控制码的位置」。
_CONTROL = re.compile(r"#\$[a-zA-Z]#|\$[a-zA-Z0-9]|%[a-zA-Z]+|\^|@")

#: 守卫 strip 掉的字符集，必须与 `test_every_opening_traces_back_to_corpus` 一致。
_STRIP_CHARS = "。，？！！…… "


def _clean(text: str) -> str:
    """取控制码之前的那一段，并去掉首尾空白。"""
    match = _CONTROL.search(text)
    head = text[: match.start()] if match else text
    return head.strip()


def _fragments(opening: str) -> list[str]:
    """复刻守卫的切片方式，用来在写进文件**之前**自检。"""
    return [
        part.strip(_STRIP_CHARS)
        for part in opening.replace("？", "？|").replace("。", "。|").split("|")
        if len(part.strip()) >= 6
    ]


def _is_traceable(opening: str, lines: list[str]) -> bool:
    fragments = _fragments(opening)
    if not fragments:
        return False
    return all(any(part in line for line in lines) for part in fragments)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--existing",
        type=Path,
        default=PROJECT_ROOT / "data" / "scenarios" / "morning.json",
        help="已存在的预设文件，用来避开重复开场白",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.corpus.read_text(encoding="utf-8"))
    records = payload["records"]

    used_openings: set[str] = set()
    if args.existing.exists():
        existing = json.loads(args.existing.read_text(encoding="utf-8"))
        used_openings = {
            str(item.get("opening") or "").strip()
            for item in existing.get("scenarios", [])
        }

    # 先把每个 NPC 的**全部**可读中文台词收起来 —— 自检要拿它当子串字典，
    # 不能只用季节键那几条，否则「这句话在别处也说过」的情况会被误判成伪造。
    all_lines: dict[str, list[str]] = defaultdict(list)
    for record in records:
        text = str(record.get("resolvedText") or record.get("text") or "")
        if text:
            all_lines[str(record.get("npcId") or "")].append(text)

    candidates: list[dict[str, object]] = []
    dropped = Counter()
    for record in records:
        key = str(record.get("sourceKey") or "")
        match = _SEASON_KEY.match(key)
        if not match:
            continue
        npc_id = str(record.get("npcId") or "")
        source_path = str(record.get("sourcePath") or "")
        if not npc_id:
            dropped["缺 npcId"] += 1
            continue
        # 婚后对白要结了婚才触发，不能当日常晨间开场。
        if "MarriageDialogue" in source_path or "MarriageDialogue" in key:
            dropped["婚后对白"] += 1
            continue

        text = str(record.get("resolvedText") or record.get("text") or "")
        if not text or "{{i18n:" in text:
            dropped["无中文（i18n 未解析）"] += 1
            continue
        if len(re.findall(r"[\u4e00-\u9fff]", text)) < 4:
            dropped["几乎没有中文"] += 1
            continue

        opening = _clean(text)
        if opening in used_openings:
            dropped["已被现有预设占用"] += 1
            continue
        if not _is_traceable(opening, all_lines[npc_id]):
            dropped["裁完过不了守卫的片段检查"] += 1
            continue

        season, day = match.group(1).lower(), int(match.group(2))
        candidates.append(
            {
                "npcId": npc_id,
                "opening": opening,
                "_openingSource": (
                    f"{record.get('sourceMod')}:{source_path}:{key}"
                    " —— 逐字取自原版，裁到第一个控制码之前。"
                ),
                "trigger": {"kind": "season", "season": season, "dayInSeason": day},
                "_sourceKey": key,
                "_rawText": text[:160],
            }
        )

    by_npc = Counter(str(item["npcId"]) for item in candidates)
    by_season = Counter(str(item["trigger"]["season"]) for item in candidates)  # type: ignore[index]
    covered_days = {item["_sourceKey"] for item in candidates}

    result = {
        "schemaVersion": 1,
        "_comment": [
            "由 scripts/extract_morning_candidates.py 生成，**不是**可直接上线的预设。",
            "开场白已按守卫规则裁切并自检通过；direction / boundaries / closingHook",
            "需要人工补齐后才应合并进 data/scenarios/morning.json。",
            "",
            f"候选 {len(candidates)} 条，覆盖 {len(covered_days)} 个不同「季节_日」。",
        ],
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"候选 {len(candidates)} 条，覆盖 {len(covered_days)} 个不同「季节_日」")
    print(f"  按季节: {dict(by_season)}")
    print("  按 NPC (前 15):")
    for npc, count in by_npc.most_common(15):
        print(f"    {npc:<16} {count}")
    if dropped:
        print("  丢弃:")
        for reason, count in dropped.most_common():
            print(f"    {reason:<28} {count}")
    print(f"已写入 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
