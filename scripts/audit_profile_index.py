"""体检资料索引：只读汇总 `warnings`，便于每次重建索引后快速核对。

用法：

    py -3.10 -B scripts/audit_profile_index.py [--index <索引路径>] [--show 12]

背景：`scripts/build_profile_index.py` 每次重建都会把无法处理的输入记进索引的 `warnings`，
而这些警告藏在十几 MB 的 JSON 里，很容易一直没人看。2026-09-20 的一次体检发现 67 条警告中：

- **55 条**是 SVE 的 `assets/XNBs/*.xnb` **未解包**——这部分内容根本没进索引，
  `storyEvents` 因此为 0 条（剧情/地点素材缺失）；
- **3 条**是 `data/personas/` 目录里混入了非 persona 文件（`behavior-quality-scenarios.json`）；
- **9 条**是 `code/*.json` 解析失败（很可能是未解包的 xnb）。

本脚本**只读**，不修改索引、不写任何文件。
"""

from __future__ import annotations

import argparse
import json
import pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INDEX = (
    ROOT
    / "data"
    / "generated"
    / "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)


def _category(message: str) -> str:
    if message.startswith("xnb source requires unpacked JSON"):
        return "xnb 未解包"
    if message.startswith("invalid persona"):
        return "非 persona 文件混入 personas 目录"
    if message.startswith("无法解析 JSON"):
        return "JSON 解析失败"
    return "其他"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="索引 JSON 路径")
    parser.add_argument("--show", type=int, default=8, help="每类最多展示几条原文")
    args = parser.parse_args()

    path = pathlib.Path(args.index)
    if not path.is_file():
        print(f"找不到索引：{path}")
        return 2

    payload = json.loads(path.read_text(encoding="utf-8"))
    print(f"索引：{path.name}（{path.stat().st_size / 1024 / 1024:.2f} MB）")
    print()

    # 时效：索引要比它的生产者（索引器、personas）与消费者（读取模块）都新，
    # 否则 Prompt 用的可能是旧数据。注意本审计脚本自身不参与比较（它不影响索引内容）。
    index_time = path.stat().st_mtime
    refreshed_by = [ROOT / "scripts" / "build_profile_index.py"]
    persona_files = sorted((ROOT / "data" / "personas").glob("*.json"))
    if persona_files:
        refreshed_by.append(max(persona_files, key=lambda item: item.stat().st_mtime))
    refreshed_by.append(ROOT / "bridge" / "src" / "stardew_ai_bridge" / "profile_index.py")
    newer = [
        candidate.name
        for candidate in refreshed_by
        if candidate.is_file() and candidate.stat().st_mtime > index_time
    ]
    if newer:
        print(f"⚠ 索引可能已过期：{'、'.join(newer)} 比它更新，请重建索引。")
    else:
        print("索引时效：未过期（索引器、personas 与读取模块都不比它新）。")
    print()

    print("规模：")
    for key in (
        "profiles",
        "voiceCards",
        "styleSamples",
        "speechEvidence",
        "behaviorExamples",
        "knowledgeFacts",
        "knownCharacters",
        "storyEvents",
        "sources",
    ):
        value = payload.get(key)
        if isinstance(value, dict):
            print(f"  {key:<18} {len(value)} 键")
        elif isinstance(value, list):
            print(f"  {key:<18} {len(value)} 条")

    warnings = payload.get("warnings") or []
    print()
    print(f"警告：{len(warnings)} 条")
    if warnings:
        grouped: dict[str, list[str]] = {}
        for message in warnings:
            grouped.setdefault(_category(str(message)), []).append(str(message))
        for name, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
            print(f"  [{len(items):>3}] {name}")
            # xnb 类按目录聚合，比逐条罗列更有用
            if name == "xnb 未解包":
                dirs = Counter(
                    item.split(": ", 1)[1].rsplit("/", 1)[0]
                    for item in items
                    if ": " in item
                )
                for directory, count in dirs.most_common():
                    print(f"          {count:>3} 个在 {directory}/")
            for item in items[: args.show]:
                print(f"          · {item[:110]}")
            if len(items) > args.show:
                print(f"          …… 其余 {len(items) - args.show} 条省略")

    # 角色样本分布：只看有 profile 的角色，便于发现“有骨架但没素材”的角色。
    samples = payload.get("styleSamples") or []
    if samples and payload.get("profiles"):
        counts = Counter(str(item.get("npcId")) for item in samples)
        profiles = sorted(payload["profiles"])
        cards = set(payload.get("voiceCards") or ())
        rich = [name for name in profiles if counts.get(name, 0) >= 100]
        thin = [name for name in profiles if 0 < counts.get(name, 0) <= 3]
        blank = [name for name in profiles if counts.get(name, 0) == 0]
        print()
        print("角色样本分布（按 profile 计）：")
        print(f"  ≥100 条：{len(rich)} 个")
        print(f"  1～3 条：{len(thin)} 个")
        print(f"  0 条   ：{len(blank)} 个 {blank[:8]}")
        missing_cards = [name for name in profiles if name not in cards]
        if missing_cards:
            print(f"  没有 voiceCard：{len(missing_cards)} 个 {missing_cards[:8]}")
        # 变体 ID（含下划线或点号）通常样本极少，量大了才值得处理
        variant_ids = [name for name in counts if "_" in name or "." in name]
        if variant_ids:
            variant_total = sum(counts[name] for name in variant_ids)
            share = variant_total / max(sum(counts.values()), 1) * 100
            print(
                f"  变体 ID（含 _ 或 .）：{len(variant_ids)} 个、"
                f"{variant_total} 条样本（{share:.2f}%）"
            )

    events = payload.get("storyEvents") or []
    if not events:
        print()
        print("注意：storyEvents 为 0 条——若上面的 xnb 警告里有剧情/地点素材，解包后应能补上。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
