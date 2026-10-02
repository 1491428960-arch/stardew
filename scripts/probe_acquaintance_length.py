"""dump 各阶段 `stage_execution_card` 的 `responseShape`，看有没有数字上限。

背景（2026-09-28）：云端评测里 `sophia-daily`（**acquaintance**，2 心）平均 **68.3 字**、
`sophia-vineyard` **78.3 字**，而 `safety_rules` 要求整条 **15–40 字** ⇒ 超了近一倍。

已知 stranger 的 `responseShape` 是「用 1 句直接回答；只有问题需要时再补第 2 句」、
friend 是「通常 2 句：先回答，再给一个具体细节或态度」—— **都带数字**。
而收束长度的那次改动只动了 close / dating / married / parent 四档，
**acquaintance 档没动** ⇒ 怀疑它压根没有数字上限。

零请求、只读。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "bridge" / "src"))

from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: E402

#: 关系阶段 → 心数（`relationship` 会覆盖心数，这里只跑心数路径）。
CASES = [
    ("Sophia", ["SVE"], 0, "stranger"),
    ("Sophia", ["SVE"], 2, "acquaintance"),
    ("Sophia", ["SVE"], 4, "acquaintance"),
    ("Sophia", ["SVE"], 6, "friend"),
    ("Sophia", ["SVE"], 8, "close"),
]

for npc, mods, hearts, expected in CASES:
    ctx = ContextBuilder().build(npc, source_mods=mods, friendshipHearts=hearts)
    cards = PromptBuilder().build(ctx, "你好啊", compact=True)
    card = next((c for c in cards if c["name"] == "stage_execution_card"), None)
    label = f"{npc} hearts={hearts}"
    if card is None:
        print(f"{label:<24} 无 stage_execution_card")
        continue
    try:
        data = json.loads(card["content"])
    except Exception:
        print(f"{label:<24} 非 JSON：{card['content'][:160]}")
        continue
    shape = data.get("responseShape", "")
    has_num = any(ch.isdigit() for ch in shape) or "两" in shape or "一" in shape
    mark = "✅" if has_num else "❌ 无数字上限"
    print(f"{label:<24} stage={data.get('stage','?'):<13} {mark}")
    print(f"    responseShape = {shape}")
    print(f"    followUp      = {data.get('followUp','')}")

print()
print("=" * 78)
print("对照：safety_rules 的整条长度要求")
print("=" * 78)
ctx = ContextBuilder().build("Sophia", source_mods=["SVE"], friendshipHearts=4)
for c in PromptBuilder().build(ctx, "你好啊", compact=True):
    body = c.get("content", "")
    if "字" in body and ("15" in body or "40" in body):
        for frag in body.replace("\n", "。").split("。"):
            if "字" in frag and ("15" in frag or "40" in frag):
                print(f"  [{c['name']}] {frag.strip()[:150]}")
