"""改动前后对比：style 可用条数是否退化。

旧：speech(limit=6)  + style(limit=8)
新：speech(limit=12) + style(limit=24)

两个 accessor 都按文本互斥（`ContextBuilder` 用 speech 的文本去重 style），
所以 speech 池一放宽就会多吃掉 style 几条；而 style 池同时从 8 放到 24，
又多拿进来一批。净效果只能实测。

两个 limit 都远小于新 cap（18 / 24），所以**直接传 limit 就能模拟旧行为**，
不需要 monkeypatch 常量。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bridge" / "src"))

from stardew_ai_bridge.profile_index import ProfileIndexStore  # noqa: E402

INDEX_PATH = (
    ROOT / "data" / "generated"
    / "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)
SOURCE_MODS = ["FlashShifter.StardewValleyExpandedCP"]

OLD = (6, 8)      # (speech limit, style limit)
NEW = (18, 24)
INJECT_CAP = 6


def available(store: ProfileIndexStore, npc: str, speech_limit: int, style_limit: int) -> int:
    """去重后 style 这一路实际能注入几条。"""

    speech = store.speech_evidence(npc, SOURCE_MODS, limit=speech_limit)
    style = store.style_samples(npc, SOURCE_MODS, limit=style_limit)
    speech_texts = {str(i.get("text", "")) for i in speech}
    return len([i for i in style if str(i.get("text", "")) not in speech_texts])


def main() -> None:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    npcs = sorted({
        str(s.get("npcId", "")).strip()
        for s in index.get("speechEvidence", [])
        if str(s.get("npcId", "")).strip()
    })

    store = ProfileIndexStore(INDEX_PATH)
    before: dict[str, int] = {}
    after: dict[str, int] = {}
    for npc in npcs:
        before[npc] = available(store, npc, *OLD)
        after[npc] = available(store, npc, *NEW)

    verdicts: Counter[str] = Counter()
    worse: list[tuple[str, int, int]] = []
    for npc in npcs:
        old_n, new_n = before[npc], after[npc]
        if new_n > old_n:
            verdicts["改善"] += 1
        elif new_n < old_n:
            verdicts["**退化**"] += 1
            worse.append((npc, old_n, new_n))
        else:
            verdicts["不变"] += 1

    print(f"角色数: {len(npcs)}   （旧 speech/style = {OLD}，新 = {NEW}）")
    print("\n--- 逐角色比较 ---")
    for key, count in verdicts.most_common():
        print(f"  {key}: {count}")

    print(f"\n  改动前: style 可用 0 条的角色 {sum(1 for v in before.values() if v == 0)} 个"
          f"；不足 {INJECT_CAP} 条 {sum(1 for v in before.values() if v < INJECT_CAP)} 个")
    print(f"  改动后: style 可用 0 条的角色 {sum(1 for v in after.values() if v == 0)} 个"
          f"；不足 {INJECT_CAP} 条 {sum(1 for v in after.values() if v < INJECT_CAP)} 个")
    print(f"  改动前 style 可用条数合计 {sum(before.values())}，改动后 {sum(after.values())}")

    if worse:
        print(f"\n--- 退化角色（{len(worse)} 个）---")
        for npc, old_n, new_n in worse[:30]:
            print(f"  {npc}: {old_n} → {new_n}")
    else:
        print("\n没有任何角色的 style 可用条数下降。")


if __name__ == "__main__":
    main()
