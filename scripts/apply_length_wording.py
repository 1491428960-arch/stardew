"""长度措辞改动的**可回滚补丁工具**（三个方案，默认 dry-run）。

## 背景（2026-09-28 晚实测）

整份 prompt 里 **「句数」出现在 6 张卡，「字数」只出现在 1 张卡**（`safety_rules`）。
按**已被实测证实的「取最宽」规律** ⇒ **字数的话语权只有 1/6**
⇒ 模型以句数为准，`15–40 字` 被无视（实测 **43.8%** 超 40 字）。

⇒ **修法是改措辞**（不是重试 / 截断 —— 模型没做错）。三个方案：

| 方案 | 做什么 | 改动点 |
|---|---|---|
| `jia` | **甲·补字数**：在其余各卡的句数旁都补字数，话语权对等 | 多处 |
| `yi`  | **乙·去字数**：把唯一的 `15–40 字` 删掉，只留句数 | `prompts.py` 1 行 + 测试 1 行 |
| `bing`| **丙·改单点**：只改 `safety_rules` 一行 | ❌ 已知**等于没改**，仅作对照 |

## 用法

    python scripts/apply_length_wording.py --plan              # 看三个方案各改什么
    python scripts/apply_length_wording.py --apply yi           # dry-run，只打印
    python scripts/apply_length_wording.py --apply yi --write   # 真改（自动备份）
    python scripts/apply_length_wording.py --rollback           # 从备份还原

⚠ **默认 dry-run**：不带 `--write` 绝不落盘。
⚠ 每次 `--write` 前会把原文件备份到 `.tmp/length-wording-backup/<时间戳>/`。
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = WT / ".tmp" / "length-wording-backup"

#: 唯一的字数来源。
SRC_WORDY = "中文通常 1–2 句、15–40 字；"
#: 各种「只有句数」的写法（补字数时要挨着它们补）。
BARE_SENTENCE_FORMS = (
    "通常 1–2 句",
    "回复最多 1 句",
    "只输出 NPC 的中文对白，1–2 句",
)

PLANS = {
    "jia": {
        "title": "甲·补字数（在其余各卡的句数旁都补上字数）",
        "why": "让字数获得与句数对等的话语权（6 处都提）。改动面最大，最贴合原意。",
        "edits": [],  # 见 plan_jia()
    },
    "yi": {
        "title": "乙·去字数（删掉唯一的 15–40 字，只留句数）",
        "why": (
            "最诚实：40 字在「最多 2 句」的前提下本身就偏紧"
            "（实测每句中位 18 字，两句自然 36~40），"
            "留着只会被违反。删掉后少一个被违反的约束。"
            "风险已验证为低：长回复的**最终质量并不更差**（41–60 字组才最差）。"
        ),
        "edits": [
            # (相对路径, 原文, 新文, 说明)
            (
                "bridge/src/stardew_ai_bridge/prompts.py",
                SRC_WORDY,
                "中文通常 1–2 句；",
                "删掉字数，只留句数",
            ),
            (
                "bridge/tests/test_prompts.py",
                'assert "15–40 字" in safety_message["content"]',
                'assert "1–2 句" in safety_message["content"]',
                "对应的断言改为钉句数",
            ),
        ],
    },
    "bing": {
        "title": "丙·改单点（只把 15–40 字放宽到 15–50 字）",
        "why": (
            "❌ **已知等于没改** —— 剩下五处句数照样压过它。"
            "仅作为 A/B 的对照臂存在，不要当作解决方案。"
        ),
        "edits": [
            (
                "bridge/src/stardew_ai_bridge/prompts.py",
                SRC_WORDY,
                "中文通常 1–2 句、15–50 字；",
                "只放宽上限数字，仍只在这一处出现",
            ),
            (
                "bridge/tests/test_prompts.py",
                'assert "15–40 字" in safety_message["content"]',
                'assert "15–50 字" in safety_message["content"]',
                "断言跟着改",
            ),
        ],
    },
}


def plan_jia() -> list[tuple[str, str, str, str]]:
    """甲方案：给只有句数的写法补上字数。"""
    out: list[tuple[str, str, str, str]] = []
    p = "bridge/src/stardew_ai_bridge/prompts.py"
    out.append((p, SRC_WORDY, "中文通常 1–2 句、每句约 15–20 字；", "把复合上限改成可同时满足的写法"))
    out.append((p, "通常 1–2 句", "通常 1–2 句，每句约 15–20 字", "在 responseShape 旁补字数"))
    out.append((p, "回复最多 1 句", "回复最多 1 句（约 15–20 字）", "在 stage_execution_card 旁补字数"))
    out.append((p, "只输出 NPC 的中文对白，1–2 句", "只输出 NPC 的中文对白，1–2 句、每句约 15–20 字", "在 topic 契约旁补字数"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="长度措辞改动的可回滚补丁工具（默认 dry-run）")
    ap.add_argument("--plan", action="store_true", help="打印三个方案各改什么")
    ap.add_argument("--apply", choices=sorted(PLANS), help="应用某个方案（默认只打印）")
    ap.add_argument("--write", action="store_true", help="**真正落盘**（默认关）")
    ap.add_argument("--rollback", action="store_true", help="从最近一次备份还原")
    args = ap.parse_args()

    if args.rollback:
        if not BACKUP_ROOT.exists():
            print("没有找到任何备份目录。")
            return 0
        runs = sorted((d for d in BACKUP_ROOT.iterdir() if d.is_dir()), key=lambda d: d.name)
        if not runs:
            print("备份目录为空。")
            return 0
        latest = runs[-1]
        print(f"从备份还原：{latest}")
        for f in latest.rglob("*"):
            if f.is_file():
                rel = f.relative_to(latest)
                dst = WT / rel
                if args.write:
                    shutil.copy2(f, dst)
                    print(f"  [已还原] {rel}")
                else:
                    print(f"  [dry-run] 将还原 {rel}")
        if not args.write:
            print("\n（加 --write 才真正还原）")
        return 0

    if args.plan or not args.apply:
        print("=" * 92)
        print("长度措辞改动的三个方案")
        print("=" * 92)
        print()
        print("**共同前提**：整份 prompt 里「句数」出现在 6 张卡、「字数」只出现在 1 张卡")
        print("⇒ 按「取最宽」规律，字数的话语权只有 1/6 ⇒ 被无视（实测 43.8% 超 40 字）。")
        print()
        for key in ("jia", "yi", "bing"):
            pl = PLANS[key]
            edits = plan_jia() if key == "jia" else pl["edits"]
            print(f"## {key} —— {pl['title']}")
            print()
            print(f"  理由：{pl['why']}")
            print()
            print(f"  改动 {len(edits)} 处：")
            for rel, old, new, note in edits:
                print(f"    · {rel}")
                print(f"        旧: {old[:70]}")
                print(f"        新: {new[:70]}")
                print(f"        （{note}）")
            print()
        print("=" * 92)
        print("⚠ 三个方案**都未应用**。选定后：")
        print("    python scripts/apply_length_wording.py --apply <方案>            # 看 diff")
        print("    python scripts/apply_length_wording.py --apply <方案> --write    # 真改")
        print("    python scripts/apply_length_wording.py --rollback --write        # 还原")
        print()
        print("⚠ 改完**必须**跑全量测试（基线 4314 passed）并重新跑")
        print("   `python scripts/probe_length_directives.py` 确认「字数」的出现处确实对等了。")
        return 0

    edits = plan_jia() if args.apply == "jia" else PLANS[args.apply]["edits"]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"方案 `{args.apply}`：{len(edits)} 处改动")
    print(f"模式：{'**真改**' if args.write else 'dry-run（不落盘）'}")
    print()

    ok = 0
    for rel, old, new, note in edits:
        path = WT / rel
        if not path.exists():
            print(f"  [跳过] {rel} 不存在")
            continue
        text = path.read_text(encoding="utf-8")
        n = text.count(old)
        if n == 0:
            print(f"  [跳过] {rel}：找不到锚点「{old[:45]}」")
            print("         ⚠ 可能已经被改过，或锚点需更新。")
            continue
        print(f"  [{'改' if args.write else '将改'}] {rel}（命中 {n} 处）× {note}")
        if args.write:
            bdir = BACKUP_ROOT / stamp / path.parent.relative_to(WT)
            bdir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, bdir / path.name)
            path.write_text(text.replace(old, new), encoding="utf-8")
        ok += 1

    print()
    if args.write:
        print(f"已改 {ok} 处；备份在 .tmp/length-wording-backup/{stamp}/")
        print("⚠ 下一步：跑全量测试 + `probe_length_directives.py` 复核出现处。")
    else:
        print(f"将改 {ok} 处。**加 --write 才真正落盘。**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
