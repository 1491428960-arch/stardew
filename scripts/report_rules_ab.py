"""把 `responseRules[0]` 交织 A/B 的产物**并排成一份人读报告**。

跑批是 `scripts/run_rules_ab_interleaved.py` 的事；本脚本**只读产物、不发请求**，
把 A 臂与 B 臂在**同一个 case、同一轮**上的台词摆在一起，并在开头写清判读方法。

用法：
    python -B scripts/report_rules_ab.py
    python -B scripts/report_rules_ab.py --dir artifacts/rules-ab --out /tmp/compare.md
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

WT = Path(__file__).resolve().parents[1]

ARM_A_TEXT = "先回答眼前的问题"
ARM_B_TEXT = "问到具体的事就直说，其余时候按自己的状态开口"

HEADER = f"""# `responseRules[0]` 交织 A/B —— 人读对照

**改的是什么**：`Wizard.voiceStyle.responseRules[0]`

| 臂 | 这一句 |
|---|---|
| A（基线） | {ARM_A_TEXT} |
| B（改动） | {ARM_B_TEXT} |

**B 想治的病**：角色被 `responseRules[0]` 拉回「答题模式」—— 玩家问什么就机械答什么，
每句都服务于回答，不像一个正在过自己日子的活人。

---

## 一、先读这段：怎么看、判断什么

### 三个观察维度

| # | 找什么 | 变多算好还是坏 |
|---|---|---|
| ① **自我状态** | 角色主动说出自己的状态、正在做的事（「锅要开了，走不开」「眼睛看酸了」） | **好** —— 这正是改动的目的 |
| ② **漏答** | 玩家问了具体的事，角色整轮没答（指标 `answeredCurrentTopic=false`） | **坏** —— 这是去掉「先回答眼前的问题」要付的代价 |
| ③ **生硬跑题** | 答非所问，但**不**像有意的自我表达，更像失焦 | **坏** |

### 四条纪律（不遵守就会得出假结论）

1. **不要用字数差当证据。** 单跑的 σ ≈ 24 字，本轮这个规模远不足以让字数差异脱离噪音。
   字数只能当**现象描述**，不能当**结论**。
2. **只看模式，不看单例。** 「B 臂有一句写得特别好」不算证据 —— A 臂同样会有写得好的句子。
   要看的是**这一类句子的出现频率**有没有系统性变化。
3. **重点读第 2、3 轮。** 第 1 轮是固定开场，两臂的差异通常被开场模板吃掉。
4. **不确定就说不确定。** 这次的设计**本来就只给方向**，给不了统计显著性。看不出差别时，
   「效应小于噪音」本身就是一个真结论，不要硬解释。

### 结论怎么下

- ✅ ① 明显变多，**且** ② 没有上升 ⇒ 方向对，值得再投额度跑统计
- ❌ ② 上升 ⇒ 得不偿失（上次回滚正是这个理由）
- ⚠️ 看不出差别 ⇒ 到此为止

---
"""


def _load(arm: str, base: Path) -> list[dict]:
    """把某一臂所有批次的 results.jsonl 读成 case 记录列表。"""
    out: list[dict] = []
    for path in sorted(glob.glob(str(base / f"{arm}-*" / "results.jsonl"))):
        batch = Path(path).parent.name
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                record["_batch"] = batch
                out.append(record)
    return out


def _index(records: list[dict]) -> dict[tuple[str, str], dict]:
    """按 (caseId, turnId) 建索引；同一 case 跨批次时保留先到的，并记下重复批次数。"""
    index: dict[tuple[str, str], dict] = {}
    for record in records:
        case_id = str(record.get("caseId", ""))
        for turn in record.get("turns") or []:
            key = (case_id, str(turn.get("turnId", "")))
            index.setdefault(key, {**turn, "_batch": record["_batch"], "_npcId": record.get("npcId")})
    return index


def _reply(turn: dict) -> str:
    text = turn.get("reply")
    if not isinstance(text, str) or not text.strip():
        err = turn.get("errorMessage") or turn.get("error")
        return f"（无回复{ ': ' + str(err) if err else ''}）"
    return text.strip()


def _cell(text: str) -> str:
    """表格单元格里不能有裸换行。"""
    return text.replace("\n", " ⏎ ").replace("|", "\\|")


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 responseRules[0] 交织 A/B 人读报告")
    ap.add_argument("--dir", default=str(WT / "artifacts" / "rules-ab"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    base = Path(args.dir)
    a_records, b_records = _load("A", base), _load("B", base)
    if not a_records or not b_records:
        print(f"⚠ {base} 下缺 A 或 B 的产物（A={len(a_records)} B={len(b_records)}）")
        return 2

    a_index, b_index = _index(a_records), _index(b_records)
    keys = sorted(set(a_index) | set(b_index))

    lines = [HEADER]
    lines.append(f"**产物**：`{base}`（A {len(a_records)} 个 case / B {len(b_records)} 个 case）\n")

    # 按 case 分组
    by_case: dict[str, list[tuple[str, str]]] = {}
    for case_id, turn_id in keys:
        by_case.setdefault(case_id, []).append((case_id, turn_id))

    current = None
    for case_id in sorted(by_case):
        turns = sorted(by_case[case_id], key=lambda k: k[1])
        npc = (a_index.get(turns[0], {}) or {}).get("_npcId") or "?"
        lines.append(f"\n## {case_id}（{npc}）\n")
        lines.append("| 轮 | 玩家 | A 臂（基线） | B 臂（改动） |")
        lines.append("|---|---|---|---|")
        for key in turns:
            turn_id = key[1]
            a_turn = a_index.get(key, {})
            b_turn = b_index.get(key, {})
            player = _cell(str(a_turn.get("playerInput") or b_turn.get("playerInput") or ""))
            lines.append(
                f"| {turn_id} | {player} | {_cell(_reply(a_turn))} | {_cell(_reply(b_turn))} |"
            )
        current = case_id

    # 汇总：只给现象描述，不给结论
    def _miss_rate(index: dict[tuple[str, str], dict]) -> tuple[int, int, int]:
        total = wrong = chars = 0
        for turn in index.values():
            if not turn.get("reply"):
                continue
            total += 1
            if turn.get("answeredCurrentTopic") is False:
                wrong += 1
            chars += len(str(turn.get("reply", "")))
        return wrong, total, (chars // total if total else 0)

    a_wrong, a_total, a_avg = _miss_rate(a_index)
    b_wrong, b_total, b_avg = _miss_rate(b_index)

    lines.append("\n---\n\n## 汇总（**现象**，不是结论）\n")
    lines.append("| 指标 | A 臂 | B 臂 | 怎么读 |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| 漏答轮数（`answeredCurrentTopic=false`） | {a_wrong}/{a_total} | {b_wrong}/{b_total} "
        f"| ⚠ **这是主判据**：B 变高 = 得不偿失 |"
    )
    lines.append(
        f"| 平均回复字数 | {a_avg} | {b_avg} | ⚠ **不能当证据**（σ≈24 字），仅描述现象 |"
    )
    lines.append(
        f"| 有效轮数 | {a_total} | {b_total} | 失败的轮次不参与判读 |"
    )
    lines.append(
        "\n> 判读顺序：先看**漏答**有没有上升，再回到上面逐 case 读**自我状态句**的频率。"
        "只有①变多且②不升，才算方向对。\n"
    )

    body = "\n".join(lines)
    out = Path(args.out) if args.out else base / "compare.md"
    out.write_text(body, encoding="utf-8")
    print(f"已写出：{out}")
    print(f"A 漏答 {a_wrong}/{a_total}  B 漏答 {b_wrong}/{b_total}  "
          f"A 均字 {a_avg}  B 均字 {b_avg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
