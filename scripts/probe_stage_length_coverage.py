"""遍历所有 persona × 各阶段，检查 `stage_execution_card.responseShape` 有没有**数字上限**。

动机：云端数据里 `sophia`（acquaintance）平均 **68.3 字**，怀疑某阶段缺长度指令。
单独查 Sophia 发现它是有的（「先用 1 句回答，再视话题补 1 句具体细节」），
于是普遍查一遍 —— 看有没有哪个角色/阶段**真的**缺数字。

零请求、只读。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "bridge" / "src"))

from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: E402

STAGES = ((0, "stranger"), (2, "acquaintance"), (6, "friend"), (8, "close"))

targets: list[tuple[str, tuple[str, ...], str]] = []
for path in sorted((WT / "data" / "personas").glob("*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    mods = tuple(data.get("sourceMods") or ())
    for npc in (data.get("personas") or {}):
        targets.append((npc, mods, path.name))

missing: list[tuple[str, str, str, str]] = []
no_card: list[tuple[str, str, str]] = []
checked = 0

for npc, mods, src in targets:
    for hearts, stage in STAGES:
        try:
            ctx = ContextBuilder().build(npc, source_mods=mods, friendshipHearts=hearts)
            cards = PromptBuilder().build(ctx, "你好啊", compact=True)
        except Exception:
            continue
        card = next((c for c in cards if c["name"] == "stage_execution_card"), None)
        if card is None:
            no_card.append((npc, stage, src))
            continue
        checked += 1
        try:
            payload = json.loads(card["content"])
        except Exception:
            missing.append((npc, stage, src, "（卡片非 JSON）"))
            continue
        shape = str(payload.get("responseShape") or "")
        if not shape:
            missing.append((npc, stage, src, "（无 responseShape 字段）"))
        elif not any(ch.isdigit() for ch in shape) and "一" not in shape and "两" not in shape:
            missing.append((npc, stage, src, shape))

print("=" * 78)
print(f"检查了 {checked} 个 (角色, 阶段) 组合，来自 {len(targets)} 个 persona 条目")
print("=" * 78)

if missing:
    print(f"\n❌ {len(missing)} 处 responseShape **没有数字上限**：\n")
    for npc, stage, src, shape in missing:
        print(f"  [{src}] {npc} @ {stage}")
        print(f"      {shape[:160]}")
else:
    print("\n✅ 全部都有数字上限。")

if no_card:
    seen = sorted({(n, s) for n, s, _ in no_card})
    print(f"\n（{len(no_card)} 个组合没有 stage_execution_card，"
          f"涉及 {len(seen)} 个 (角色, 阶段)：{seen[:12]}{' …' if len(seen) > 12 else ''}）")

# ---------------------------------------------------------------------------
# 第二段：列出各阶段实际出现的**句数取值**，找比通用档**更宽**的。
#
# `safety_rules` 是全局兜底（1–2 句 / 15–40 字）。某个角色的阶段卡若写了
# 比它**更宽**的上限（如 1–3 句），那才是真正的泄漏点；写得更严（如 1 句）
# 是好事，不用管。
# ---------------------------------------------------------------------------
import re  # noqa: E402

CN = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5}


def max_sentences(shape: str) -> int | None:
    """从 responseShape 里取出「最多几句」。取不到返回 None。"""
    nums: list[int] = []
    for m in re.finditer(r"([一二两三四五\d]+)\s*[–~\-—]?\s*([一二两三四五\d]+)?\s*句", shape):
        for g in m.groups():
            if not g:
                continue
            nums.append(int(g) if g.isdigit() else CN.get(g, 0))
    nums = [n for n in nums if n]
    return max(nums) if nums else None


wider: list[tuple[str, str, str, int, str]] = []
for npc, mods, src in targets:
    for hearts, stage in STAGES:
        try:
            ctx = ContextBuilder().build(npc, source_mods=mods, friendshipHearts=hearts)
            cards = PromptBuilder().build(ctx, "你好啊", compact=True)
        except Exception:
            continue
        card = next((c for c in cards if c["name"] == "stage_execution_card"), None)
        if card is None:
            continue
        try:
            shape = str(json.loads(card["content"]).get("responseShape") or "")
        except Exception:
            continue
        n = max_sentences(shape)
        if n is not None and n > 2:
            wider.append((npc, stage, src, n, shape))

print()
print("=" * 78)
print("比全局兜底（1–2 句）**更宽**的阶段卡 —— 这才是泄漏点")
print("=" * 78)
if wider:
    for npc, stage, src, n, shape in wider:
        print(f"  ⚠ [{src}] {npc} @ {stage}: 最多 {n} 句")
        print(f"      {shape[:150]}")
else:
    print("  （无 —— 所有阶段卡的句数上限都 ≤ 2）")
