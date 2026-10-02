"""反向验证 —— 台账里登记的每条约束，`text` 是否**真的出现在 prompt 里**。

已有工具只验证**一个方向**：

- `check_prompt_consistency --against-scope`：**prompt 里的量 ⇒ 是否都在台账**
  （抓「漏登记」）

**反方向从未验证**：**台账里的条目 ⇒ 是否真的存在**。
如果某条台账写的是一个已经不存在的句子（改动后没同步、或当初就抄错），
它会一直躺在表里，让台账**看起来完整**，而判定引擎 `find_conflicts` 会拿它去
和真实条目比较 —— 产出的冲突是**假**的。

本探针扫全部 `CURRENT` 条目，逐条把 `text` 拿到
**3 条路径 × 7 档**的全部卡片内容里去找。零请求、只读。

`text` 里允许有 `…`（台账用省略号缩写长句）—— 按 `…` 切开后要求**每段都出现**。
"""

from __future__ import annotations

import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "bridge" / "src"))
sys.path.insert(0, str(WT / "scripts"))

from constraint_scope import CURRENT  # noqa: E402

import check_prompt_consistency as chk  # noqa: E402

#: 把三条路径 × 全部阶段的卡片正文拼成一个大文本（只拼一次，避免每条都重建）。
blob_parts: list[str] = []
for stage in chk.STAGES:
    for topic, compact in chk.PATHS:
        try:
            blob_parts.extend(
                c.get("content", "") or ""
                for c in chk.collect_parts(stage, topic=topic, compact=compact)
            )
        except AttributeError:
            # 旧版本没有 collect_parts：退化成直接复制 collect 的取卡逻辑
            from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder

            hearts, extra = chk.STAGES[stage]
            context = ContextBuilder().build("lewis", friendshipHearts=hearts, **extra)
            if topic:
                context["interaction"] = {"intent": "topic"}
            blob_parts.extend(
                c.get("content", "") or ""
                for c in PromptBuilder().build(
                    context, "" if topic else "你好啊", compact=compact
                )
            )
BLOB = "\n".join(blob_parts)
print(f"拼接了 {len(blob_parts)} 张卡的正文，共 {len(BLOB)} 字符。")
print(f"台账共 {len(CURRENT)} 条。")
print()

missing: list[tuple[str, str]] = []
partial: list[tuple[str, str, list[str]]] = []

for item in CURRENT:
    text = item.text or ""
    segments = [s.strip() for s in text.split("…") if s.strip()]
    if not segments:
        continue
    absent = [s for s in segments if s not in BLOB]
    if len(absent) == len(segments):
        missing.append((item.id, text))
    elif absent:
        partial.append((item.id, text, absent))

print("=" * 78)
print("❌ 台账里登记、但 prompt 里**完全找不到**的条目（疑似过时/抄错）")
print("=" * 78)
if missing:
    for item_id, text in missing:
        print(f"  [{item_id}]")
        print(f"      {text[:130]}")
else:
    print("  （无）")

print()
print("=" * 78)
print("⚠ 只找到一部分（`…` 分段中有一段缺席 —— 可能只是缩写，也可能真过时）")
print("=" * 78)
if partial:
    for item_id, text, absent in partial:
        print(f"  [{item_id}] 缺席片段: {absent}")
        print(f"      全文: {text[:120]}")
else:
    print("  （无）")

print()
print(f"小结：完全找不到 {len(missing)} 条，部分找不到 {len(partial)} 条。")
print()
print("⚠ 注意本探针的**已知边界**：它只对比字符串，不理解语义。")
print("  台账为了可读性常把长句缩写（用 `…`）或改写字面，")
print("  所以「部分找不到」多数是**缩写**而非错误 —— 必须人读一遍再下结论。")
