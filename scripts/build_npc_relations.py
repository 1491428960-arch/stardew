#!/usr/bin/env python3
"""生成 NPC↔NPC 关系表。

权威来源是**游戏数据**，不是模型常识：

* `Content (unpacked)/Data/Characters.json` 的 `FriendsAndFamily` 给关系图；
  中文关系词来自 `Strings/Characters.<locale>.json`（22 个 `Relative_*`）。
* Content Patcher mod（SVE 等）通过 `Changes` 里的 `EditData` 追加或覆盖
  `Data/Characters`，按声明顺序合并 —— SVE 里绝大多数角色的
  `FriendsAndFamily` 是空的（作者没声明），所以它们的关系要靠 `--extras`
  手工策展，每条都必须带证据。

`--extras` 的格式：

```json
{
  "relations": {
    "Sophia": [
      {
        "npc": "Gus",
        "term": "亲密的家庭朋友",
        "note": "酒馆老板。我去酒馆从来不点单，他知道我要格兰普顿香橙鸡，还总说不用付钱。",
        "evidence": "SVE i18n zh.json: Sophia.4hearts.HowAreYou.07 / Sophia.8hearts.14"
      }
    ]
  }
}
```

输出结构：

```json
{
  "version": 1,
  "sources": {"characters": "...", "locale": "zh-CN", "modRoots": [...], "extras": "..."},
  "relations": {
    "Marnie": [{"npc": "Shane", "term": "外甥"}],
    "Sophia": [{"npc": "Gus", "term": "亲密的家庭朋友", "note": "...", "evidence": "..."}]
  }
}
```
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "bridge" / "src"))

from stardew_ai_bridge.npc_relations import (  # noqa: E402
    build_relations,
    fill_reciprocal_relations,
    merge_relations,
)


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_possible(path: Path) -> object | None:
    try:
        return _read_json(path)
    except (OSError, ValueError):
        return None


def load_content_patcher_characters(mod_root: Path) -> dict[str, object]:
    """从 Content Patcher mod 里抽 `Data/Characters` 的编辑。

    mod 的 `Changes` 是按声明顺序排列的列表，只有 `Action == "EditData"` 且
    `Target` 以 `Data/Characters` 开头的那几条才是关系数据；后面的覆盖前面的，
    与 Content Patcher 的语义一致。读不动或格式不对的文件一律跳过 ——
    mod 目录里杂着大量非 Characters 的 JSON。
    """

    characters: dict[str, object] = {}
    for path in sorted(mod_root.rglob("*.json")):
        payload = _read_json_if_possible(path)
        if not isinstance(payload, Mapping):
            continue

        changes = payload.get("Changes")
        if not isinstance(changes, list):
            continue

        for change in changes:
            if not isinstance(change, Mapping):
                continue
            if change.get("Action") != "EditData":
                continue
            target = change.get("Target")
            if not isinstance(target, str) or not target.startswith("Data/Characters"):
                continue
            entries = change.get("Entries")
            if isinstance(entries, Mapping):
                characters.update(entries)

    return characters


def _load_extras(path: Path | None) -> dict[str, list[dict[str, str]]]:
    if path is None:
        return {}

    payload = _read_json_if_possible(path)
    if not isinstance(payload, Mapping):
        return {}

    relations = payload.get("relations")
    if not isinstance(relations, Mapping):
        return {}

    extras: dict[str, list[dict[str, str]]] = {}
    for name, entries in relations.items():
        if not isinstance(entries, list):
            continue
        extras[str(name)] = [
            {str(key): str(value) for key, value in entry.items()}
            for entry in entries
            if isinstance(entry, Mapping)
        ]

    return extras


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--characters",
        type=Path,
        required=True,
        help="已解包的 Content/Data/Characters.json",
    )
    parser.add_argument(
        "--strings",
        type=Path,
        required=True,
        help="已解包的 Strings/Characters.<locale>.json（提供中文关系词）",
    )
    parser.add_argument(
        "--mod-root",
        type=Path,
        action="append",
        default=[],
        help="Content Patcher mod 根目录，可重复传入（SVE 等）",
    )
    parser.add_argument(
        "--extras",
        type=Path,
        help="手工策展的关系（每条带 evidence），覆盖同名的自动条目",
    )
    parser.add_argument("--output", type=Path, required=True, help="输出 JSON 路径")
    parser.add_argument("--locale", default="zh-CN", help="输出的语言标记")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    characters_payload = _read_json(args.characters)
    if not isinstance(characters_payload, Mapping):
        print(f"ERROR: {args.characters} 不是对象", file=sys.stderr)
        return 2

    strings_payload = _read_json(args.strings)
    if not isinstance(strings_payload, Mapping):
        print(f"ERROR: {args.strings} 不是对象", file=sys.stderr)
        return 2

    characters: dict[str, object] = dict(characters_payload)
    for mod_root in args.mod_root:
        if mod_root.is_dir():
            characters.update(load_content_patcher_characters(mod_root))

    generated = build_relations(characters, strings_payload)
    generated = fill_reciprocal_relations(generated, characters, strings_payload)
    extras = _load_extras(args.extras)
    relations = merge_relations(generated, extras)

    output = {
        "version": 1,
        "sources": {
            "characters": str(args.characters),
            "strings": str(args.strings),
            "locale": args.locale,
            "modRoots": [str(root) for root in args.mod_root],
            "extras": str(args.extras) if args.extras else None,
        },
        "relations": relations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    edge_count = sum(len(entries) for entries in relations.values())
    curated = sum(
        1 for entries in relations.values() for entry in entries if entry.get("evidence")
    )
    print(
        f"npc relations written: {args.output} "
        f"characters={len(relations)} edges={edge_count} curated={curated}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
