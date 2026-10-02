"""角色 `voiceStyle.responseRules` 的**到达率**：写了几条，有几条真的进了 prompt。

## 为什么需要这一层

"约束的话语权"此前是按**卡片**数的（字数只出现在 1 张卡 ⇒ 1/6）。
但那只是"**写进了卡**"。还有更前一层的损耗：

> **数据里写了，但组装时被丢掉** —— 连卡都进不去。

起因：查 `responseRules[0]` 落点时发现 `voiceActions = voice_actions[:3]`，
而 `signatureMoves` 为空时会先用 `sentencePattern` 占掉两个槽
⇒ 第 3 槽之后的内容**全部被丢弃**。

⇒ 于是问题变成：**36 个角色写的 `responseRules`，各自有几条能到 prompt？**

⚠ 若答案是"只有第 1 条"，那么：
- 角色数据里写的**长度规则、排除项**大量从未生效；
- 对「字数话语权只有 1/6」是**又一条独立佐证**；
- ⚠ 但**反面也要说清**：这可能只是 `voiceActions` 这一个通道的损耗，
  **不能推论"整条规则不在 prompt 里"** —— 所以本探针**全卡扫描**，不只查 `voiceActions`。

## 做法

对每个角色、每个阶段：
1. 取出该角色**全部** `responseRules` 条目；
2. 把该次 prompt 的**所有卡**拼成一个文本；
3. 逐条判断是否出现（取前 8 字做匹配，因为 `item_limit=75` 会截断长条目），
   并记录**出现在哪张卡**里。

只读、零请求、`return 0`。

用法：

    python scripts/probe_response_rules_reach.py            # 摘要
    python scripts/probe_response_rules_reach.py --detail   # 逐条列出
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "scripts"))
sys.path.insert(0, str(WT / "bridge" / "src"))

import check_prompt_consistency as chk  # noqa: E402

DATA = WT / "data" / "personas"


def load_rules() -> dict[str, list[str]]:
    """``{"<源文件>::<角色名>": [responseRules...]}``。

    ⚠ 两个坑（v1 都踩了）：
    1. **`displayName` 不在 `responseRules` 那一层** —— 结构是
       ``{"Wizard": {"displayName": ..., "voiceStyle": {"responseRules": [...]}}}``
       ⇒ 必须**向下传递**名字，不能在同一层找。
    2. **不能按角色名合并不同源文件** —— Wizard/Rasmodia 在 `vanilla.json` 与
       `rasmodia.json` 里**各有一套 `responseRules`**，而只有一套被 prompt 用到
       （实测是 `vanilla.json` 那套）。合并会得到"写了 8 条"这种虚高数字。
       ⇒ 按 **源文件::名字** 分开，由"是否出现在 prompt 里"**自己**显示谁生效，
       而不是由我猜谁生效（猜错就是又一次指错方向）。
    """
    out: dict[str, list[str]] = {}
    for path in sorted(DATA.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue

        def walk(node: object, name: str = "") -> None:
            if isinstance(node, dict):
                here = node.get("displayName") or node.get("npcId") or name
                rules = node.get("responseRules")
                if isinstance(rules, list) and rules and isinstance(here, str) and here:
                    key = f"{path.name}::{here}"
                    out.setdefault(key, [])
                    for r in rules:
                        if isinstance(r, str) and r not in out[key]:
                            out[key].append(r)
                for v in node.values():
                    walk(v, here if isinstance(here, str) else name)
            elif isinstance(node, list):
                for v in node[:80]:
                    walk(v, name)

        walk(doc)
    return out


def prompt_text(npc: str, stage: str) -> str:
    from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: PLC0415

    hearts, extra = chk.STAGES[stage]
    ctx = ContextBuilder().build(npc, friendshipHearts=hearts, **extra)
    cards = PromptBuilder().build(ctx, "你好啊", compact=True)
    if not cards:
        return ""
    return "\n".join(f"@@{c['name']}@@{c['content']}" for c in cards)


def cards_containing(text: str, frag: str) -> list[str]:
    """返回包含该片段（前 8 字）的卡名列表。"""
    key = frag[:8]
    if key not in text:
        return []
    out = []
    for chunk in text.split("@@"):
        if not chunk.strip():
            continue
        name, _, body = chunk.partition("@@")
        if key in body:
            out.append(name.strip())
    return out


def main() -> int:
    detail = "--detail" in sys.argv
    rules = load_rules()
    stage = "stranger"

    print("=" * 100)
    print("角色 responseRules 的**到达率**：写了几条 / 几条真的进了 prompt")
    print("=" * 100)
    print()
    print(f"  扫描 {len(rules)} 组（源文件::角色），阶段口径 = {stage}")
    print()

    rows: list[tuple[str, str, int, int, list[str]]] = []
    unidentified: list[str] = []
    for key, items in sorted(rules.items()):
        fname, _, npc = key.partition("::")
        # ⚠⚠ **必须先区分「名字对不上」和「规则真的没进」** ——
        # `sve.json` / `female-bachelors.json` 里存的是**汉化名**（索菲亚…），
        # 而 prompt 用英文名 ⇒ 那样查会得到一大片**假的**「一条都没进」。
        # 实测踩过：Sophia 报 0 进，但她的 `voiceActions` 里明明有
        # ["先回应玩家当前问题，再决定是否展开"]。
        try:
            text = prompt_text(npc, stage)
        except Exception:  # noqa: BLE001
            unidentified.append(f"{fname}::{npc}")
            continue
        if not text.strip():
            unidentified.append(f"{fname}::{npc}")
            continue
        reach = [r for r in items if r[:8] in text]
        rows.append((npc, fname, len(items), len(reach), reach))

    rows.sort(key=lambda r: (r[3] - r[2], r[1], r[0]))
    print(f"  {'角色':<11} {'源文件':<22} {'写了':>4} {'进了':>4}  首条到达的")
    print("  " + "-" * 94)
    zeros = []
    for npc, fname, total, hit, got in rows:
        flag = "  ⚠⚠ 一条都没进" if not hit else ""
        if not hit:
            zeros.append(f"{fname}::{npc}")
        first = got[0][:40] if got else ""
        print(f"  {npc:<11} {fname[:21]:<22} {total:>4} {hit:>4}  {first}{flag}")

    tot_all = sum(r[2] for r in rows)
    tot_hit = sum(r[3] for r in rows)
    print()
    print("=" * 100)
    if tot_all:
        print(f"  合计（**只算名字能对上的**）：写了 **{tot_all}** 条，"
              f"进 prompt **{tot_hit}** 条（**{tot_hit / tot_all * 100:.0f}%**）")
    print(f"  ⚠ 名字对不上、**未计入**的组：**{len(unidentified)}** 个")
    for u in unidentified[:12]:
        print(f"     · {u}")
    print(f"  ⚠ 其中真的一条都没进的组：**{len(zeros)}** 个")
    for z in zeros[:12]:
        print(f"     · {z}")
    print()
    print("  ⚠ **不要**把「没进 prompt」直接说成「规则无效」：")
    print("     · 匹配是**全卡扫描**的 ⇒ 若别的卡也渲染 responseRules，这里会算作「进了」。")
    print("     · 前 8 字匹配对**同前缀**条目会误判（如两条都以「先回答玩家」开头）。")
    print("     ⇒ 只用于**排序与发现异常**；下结论前须人读具体条目。")
    print("  ⚠⚠ **名字对不上 ≠ 规则没进**：`sve.json`/`female-bachelors.json` 存汉化名，")
    print("     prompt 用英文名。实测踩过：Sophia 被误报「0 进」，")
    print("     但她的 `voiceActions` 里其实是 `[\"先回应玩家当前问题，再决定是否展开\", …]`。")
    print("=" * 100)

    if detail:
        print()
        for npc, fname, total, hit, got in rows:
            print(f"  【{fname}::{npc}】")
            text = prompt_text(npc, stage) if hit or True else ""
            for i, r in enumerate(rules[f"{fname}::{npc}"]):
                mark = "✅" if r in got else "❌"
                where = ",".join(cards_containing(text, r)) if mark == "✅" else ""
                print(f"     {mark} [{i}] {r[:70]}{('  @' + where) if where else ''}")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
