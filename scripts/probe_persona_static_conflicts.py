"""静态扫描 persona 文件，找**同一个 voiceStyle 内**的量取值冲突。

为什么需要它：
`check_prompt_consistency.py` 只扫**实际渲染进 prompt 的卡**，
所以**未启用配置里的冲突扫不到** —— `rasmodia.json` 的
「用 1–3 句短句收束」vs「日常寒暄通常只说 1–2 句」就是靠人工读出来的。

本脚本补上这一段范围：直接读 `data/personas/*.json` 的
`sentencePattern` / `responseRules` / `signatureMoves`，
用**同一套正则与量名映射**找「同卡同量、取值多于一种」。

判据同 `constraint_scope.find_conflicts`，但这里只有一个维度（同 voiceStyle），
所以条件必然重叠、优先级必然相同 ⇒ **取值多于一种就是冲突**。

用法：python probe_persona_static_conflicts.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "scripts"))

from check_prompt_consistency import QUANTITIES, normalize_value  # noqa: E402

TARGETS = ("sentencePattern", "responseRules", "signatureMoves")


def values_by_quantity(texts: list[str]) -> dict[str, dict[str, list[str]]]:
    """**原始量名** → {取值: [出处文本...]}。

    ⚠ 按**原始量名**（`句数` / `字数` …）分组，不映射到台账量名 ——
    因为「每句 20 字」与「最多 2 句」本不矛盾，混在一个量名下比较会造出假冲突（Lewis）。

    ⚠ 取值必须经 `normalize_value` 归一化成**数值**：同一段里「用一句」与「一句」
    是两个不同 match 但同指取值 1，不归一化会造出大量假冲突（50 个 persona 上 20 处）。
    """
    out: dict[str, dict[str, list[str]]] = {}
    for text in texts:
        for raw, pattern in QUANTITIES.items():
            for m in re.finditer(pattern, text):
                value = normalize_value(raw, m.group(0))
                out.setdefault(raw, {}).setdefault(value, []).append(text)
    return out


def main() -> int:
    total_conflicts = 0
    scanned = 0
    for path in sorted((WT / "data" / "personas").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        personas = data.get("personas") or {}
        for name, persona in personas.items():
            voice = persona.get("voiceStyle") or {}
            fields = [f for f in TARGETS if isinstance(voice.get(f), list)]
            if not fields:
                continue
            scanned += 1
            texts = [s for f in fields for s in voice[f] if isinstance(s, str)]
            found = values_by_quantity(texts)
            conflicts = {q: v for q, v in found.items() if len(v) > 1}
            if not conflicts:
                continue
            print("=" * 78)
            print(f"{path.name}  ::  {name}  （displayName={persona.get('displayName')}）")
            print("=" * 78)
            for quantity, values in conflicts.items():
                total_conflicts += 1
                print(f"\n  ⚠ 【{quantity}】同一 voiceStyle 内 {len(values)} 种取值：")
                for value, sources in values.items():
                    print(f"     「{value}」")
                    for s in sources:
                        print(f"        ← {s}")
            print()

    print("=" * 78)
    print(f"扫描了 {scanned} 个 persona 定义，{total_conflicts} 组出现「同量多值」。")
    print()
    print("⚠ **多值 ≠ 冲突** —— 本脚本只摊开取值，判断留给人。已知的合法多值：")
    print("   · `sentencePattern` 与 `responseRules` 管**不同粒度**")
    print("     （前者是句式节奏、后者是场景长度），同量多值但方向一致；")
    print("   · 「断成第二句」是**断句行为**，「就一句」是**片段长度**，不是同一条上限。")
    print("   ⚠ 反面教材：`rasmodia.json` 的「用 1–3 句收束」vs「只说 1–2 句」")
    print("     **看着**像真冲突，其实是不同粒度（句式节奏 vs 日常寒暄场景），属分层防御，")
    print("     且有测试钉住 `1–3 句`。2026-09-28 误改后全量立刻红，已回滚。")
    print("     ⇒ **多值本身不是判决**：真冲突与分层防御在取值这一层长得一样，")
    print("       区别只在**粒度**与**测试是否钉住**。改之前先 grep 测试。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
