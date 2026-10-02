#!/usr/bin/env python
"""preferredTopics 现状审计 —— 夜间「补其他角色」工作的第一步。

口径**全部来自真实函数**，本脚本不自己实现任何正则或截断：

    _preferred_topics_for_prompt   prompt 里真正可见的那一份（含魔法证据排除）
    _facet_of_topic                主面 = `_LIFE_FACET_PATTERNS` 声明顺序的第一个命中
    _facet_hits                    **全部**命中面 —— `narrow_topic_pool` 用的是这个
    _render_role_guidance          roleGuidance 真实渲染（替换 `{topicPool}`）
    _compact_conversation_lead     240 字截断线所在

为什么必须调真实函数：`_facet_of_topic` 的判据是「声明顺序取第一个命中」，
自己写一份正则必然漂移；而 240 字越线是**静默失效**（不报错、测试也不红），
只有按真实渲染长度算才算得准。

用法：
    python scripts/probe_preferred_topics_audit.py                # 全量
    python scripts/probe_preferred_topics_audit.py --role Sophia  # 单角色细查
    python scripts/probe_preferred_topics_audit.py --gaps         # 只列缺口
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge" / "src"))

from stardew_ai_bridge import stage_policy as sp  # noqa: E402
from stardew_ai_bridge import prompts as P  # noqa: E402

# roleGuidance 的真实截断线（`_compact_conversation_lead`）。
GUIDANCE_LIMIT = 240


def _guidance_tables() -> dict[str, dict[str, str]]:
    """含 `{topicPool}` 的角色模板表（角色 -> {表名: 模板}）。"""

    names = (
        "_CONVERSATION_LEAD_ROLE_GUIDANCE",
        "_RELATIONSHIP_DISCUSSION_ROLE_GUIDANCE",
    )
    out: dict[str, dict[str, str]] = {}
    for table_name in names:
        table = getattr(sp, table_name, None)
        if not isinstance(table, dict):
            continue
        for role, template in table.items():
            if isinstance(template, str) and sp._TOPIC_POOL_PLACEHOLDER in template:
                out.setdefault(str(role), {})[table_name] = template
    return out


def _walk(node: object, fname: str, path: tuple[str, ...], out: list) -> None:
    """递归定位所有 preferredTopics，并记下它在 JSON 里的路径（角色名由此可读）。"""

    if isinstance(node, dict):
        if isinstance(node.get("preferredTopics"), list):
            out.append((fname, path, node))
        for key, value in node.items():
            _walk(value, fname, path + (str(key),), out)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk(value, fname, path + (f"[{index}]",), out)


def collect() -> list[tuple[str, tuple[str, ...], dict]]:
    rows: list[tuple[str, tuple[str, ...], dict]] = []
    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        _walk(data, path.name, (), rows)
    return rows


def audit(fname: str, path: tuple[str, ...], voice_style: dict) -> dict:
    raw = voice_style.get("preferredTopics")
    raw_items = [str(x).strip() for x in raw if isinstance(x, str) and str(x).strip()]
    visible = P._preferred_topics_for_prompt(raw)

    facets = [sp._facet_of_topic(item) for item in visible]
    no_facet = [item for item, facet in zip(visible, facets) if facet is None]
    first_facet = facets[0] if facets else None

    # 角色名：优先用 JSON 路径里最贴近 preferredTopics 的那一段。
    role_hint = path[-2] if len(path) >= 2 else "?"
    role_hint = role_hint.split("/")[-1]

    templates = _guidance_tables().get(role_hint, {})
    guidance = {}
    for table_name, template in templates.items():
        rendered = sp._render_role_guidance(template, visible)
        guidance[table_name] = {
            "chars": len(rendered),
            "over": len(rendered) - GUIDANCE_LIMIT,
            "pool_chars": len(sp._topic_pool_phrase(visible)),
        }

    return {
        "file": fname,
        "path": "/".join(path),
        "role": role_hint,
        "n_raw": len(raw_items),
        "n_visible": len(visible),
        "n_limit": P._PREFERRED_TOPICS_LIMIT,
        "magic_dropped": len(raw_items) - len(visible),
        "facets": facets,
        "no_facet": no_facet,
        "first_facet": first_facet,
        "guidance": guidance,
        "items": visible,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", help="只看某个角色（按 JSON 路径里的名字匹配）")
    ap.add_argument("--gaps", action="store_true", help="只列缺口（条数不足或超预算）")
    args = ap.parse_args()

    rows = [audit(*row) for row in collect()]
    if args.role:
        rows = [r for r in rows if args.role.lower() in r["role"].lower()]
        if not rows:
            print(f"没有匹配 --role {args.role!r} 的角色")
            return 1

    print(f"_PREFERRED_TOPICS_LIMIT = {P._PREFERRED_TOPICS_LIMIT}   roleGuidance 截断线 = {GUIDANCE_LIMIT}")
    print(f"含 {{topicPool}} 的模板表：{sorted(_guidance_tables().keys())}")
    print()

    header = f"{'role':<22}{'file':<26}{'n':>4}{'vis':>5}{'magi':>6}{'noFace':>8}{'firstFacet':<12}{'rgChars':>9}{'over':>6}"
    print(header)
    print("-" * len(header))

    gaps: list[str] = []
    for row in rows:
        rg = row["guidance"]
        rg_chars = rg_over = ""
        if rg:
            worst = max(rg.values(), key=lambda d: d["chars"])
            rg_chars, rg_over = worst["chars"], worst["over"]

        if args.gaps:
            under = row["n_visible"] < row["n_limit"]
            over = isinstance(rg_over, int) and rg_over > 0
            if not (under or over):
                continue

        print(
            f"{row['role'][:21]:<22}{row['file'][:25]:<26}"
            f"{row['n_raw']:>4}{row['n_visible']:>5}{row['magic_dropped']:>6}"
            f"{len(row['no_facet']):>8}{str(row['first_facet'])[:11]:<12}"
            f"{str(rg_chars):>9}{str(rg_over):>6}"
        )

        if row["n_visible"] < row["n_limit"]:
            gaps.append(f"  {row['role']:<22} 缺 {row['n_limit'] - row['n_visible']:>2} 条  ({row['file']})")
        if isinstance(rg_over, int) and rg_over > 0:
            gaps.append(f"  {row['role']:<22} roleGuidance 超 {rg_over} 字  ({row['file']})")

    print()
    print(f"角色数：{len(rows)}   总条数（可见）：{sum(r['n_visible'] for r in rows)}")
    if args.role:
        for row in rows:
            print(f"\n=== {row['role']} @ {row['path']} ===")
            for index, (item, facet) in enumerate(zip(row["items"], row["facets"]), 1):
                print(f"  {index:>2}. [{facet or '无面'}] {item}")

    if gaps:
        print(f"\n缺口（{len(gaps)} 条）：")
        for line in gaps:
            print(line)
    else:
        print("\n没有缺口。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
