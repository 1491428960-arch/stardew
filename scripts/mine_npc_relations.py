"""从 SVE 的 i18n 对白里挖 NPC↔NPC 关系的候选证据。

⚠️ **这个脚本只找候选，不下结论。** 关系事实必须人工按原句判定：
「我明天要去见维克多」不是关系，「维克多对我来说一直是位好朋友」才是。
把判定也交给脚本，得到的就是一堆似是而非的边 —— 而这份数据的全部价值
恰恰在于它**有原文可依**。

⚠️ **key 前缀是「事件归属」，不是说话人。** `Sophia.4hearts.HowAreYou.07`
里那句 `"Of course, Sophia! Anything for a close family friend!"` 是 **Gus**
说的。所以输出里只说「在这些 key 下命中」，不断言谁在说。

背景见 `docs/active-work.md` 的 ㉙：SVE 把全部角色的 `FriendsAndFamily`
留空了（284 个 JSON 里 `Data/Characters` 的 EditData 全是 `{}`），所以
SVE 角色的关系只能从对白里策展。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# 命中才算候选。宁可多收（人工再筛），漏了就得重新挖一遍。
RELATION_WORDS = (
    "朋友", "好友", "家人", "亲人", "亲戚", "邻居", "熟人", "同伴", "伙伴",
    "妹妹", "姐姐", "哥哥", "弟弟", "母亲", "妈妈", "父亲", "爸爸",
    "儿子", "女儿", "妻子", "丈夫", "未婚夫", "未婚妻", "恋人", "女朋友",
    "男朋友", "师父", "师傅", "老师", "学生", "学徒", "同事", "搭档",
    "从小", "小时候", "一起长大", "认识", "约会", "结婚", "嫁给", "娶",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_display_names(i18n: dict[str, Any]) -> dict[str, str]:
    """从 SVE i18n 的 `Name.*` 取「英文 id → 中文名」。

    只收字母开头、长度合理的键；`Name.Henchman`（仆从）这类非人名会被
    人工排除在名单外，不在这里过滤。
    """

    names: dict[str, str] = {}
    for key, value in i18n.items():
        if not key.startswith("Name.") or not isinstance(value, str):
            continue
        npc_id = key[len("Name."):]
        if npc_id and npc_id[0].isupper() and 1 < len(value) <= 8:
            names[npc_id] = value
    return names


def load_vanilla_display_names(npcs_path: Path) -> dict[str, str]:
    """vanilla 的 `Strings/NPCNames.zh-CN.json`：NPC id → 中文名。"""

    payload = _read_json(npcs_path)
    return {
        str(key): str(value)
        for key, value in payload.items()
        if isinstance(value, str) and 1 < len(value) <= 8
    }


def mine(
    entries: dict[str, Any],
    names: dict[str, str],
    prefix: str,
    *,
    max_candidates: int = 400,
) -> list[dict[str, Any]]:
    """扫 `prefix.` 名下的对白，返回提到别人且含关系词的句子。"""

    candidates: list[dict[str, Any]] = []
    for key, text in entries.items():
        if not key.startswith(f"{prefix}.") or not isinstance(text, str):
            continue

        mentioned = sorted(
            {cn for cn in names.values() if cn in text},
            key=lambda cn: text.index(cn),
        )
        if not mentioned:
            continue

        words = [word for word in RELATION_WORDS if word in text]
        if not words:
            continue

        candidates.append(
            {
                "key": key,
                "text": " ".join(text.split()),
                "mentioned": mentioned,
                "relationWords": words,
            }
        )
        if len(candidates) >= max_candidates:
            break

    return candidates


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--i18n", required=True, help="SVE 的 i18n/zh.json")
    parser.add_argument(
        "--npc-names",
        help="vanilla 的 Strings/NPCNames.zh-CN.json（补齐原版角色名）",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        required=True,
        help="要扫的事件归属前缀，可重复（如 Sophia、Victor）",
    )
    parser.add_argument("--output", help="候选写到这里（JSON）；缺省打印摘要")
    parser.add_argument("--max-candidates", type=int, default=400)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    i18n = _read_json(Path(args.i18n))
    names = load_display_names(i18n)
    if args.npc_names:
        names.update(load_vanilla_display_names(Path(args.npc_names)))

    report: dict[str, Any] = {"names": names, "candidates": {}}
    for prefix in args.prefix:
        hits = mine(
            i18n,
            names,
            prefix,
            max_candidates=args.max_candidates,
        )
        report["candidates"][prefix] = hits
        print(f"{prefix}: {len(hits)} 条候选")

    if args.output:
        Path(args.output).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"候选写入：{args.output}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
