"""审计 Bridge 侧的两件事：**公开名字是否真的有人用**、以及**脚本有没有破坏性操作护栏**。

用法：

    py -3.10 -B scripts/audit_bridge_health.py [--limit 20]

## “公开名字”部分的判据，以及两个已经踩过的坑

**坑 1：只减去“定义那一行”，不要排除整个定义文件。**
同文件内部调用是**合法的生产使用**。早期版本把定义文件整个排除掉，于是把
`merge_persona`（`personas.py:318` 就在调它）、`case_by_id`、`build_group_messages`、
`build_vertex_url` 四个核心函数误报成“没人用”——44 个结果里有 18 个是假阳性。

**坑 2：装饰器注册的函数天然没有显式调用。**
FastAPI 的 `@app.get(...)` 路由处理函数（`app.py` 里的页面与接口）用名字是搜不到的。
本脚本用 `ast` 的 `decorator_list` 把它们单独标注，不混进死代码候选。

**已知的保守性**：名字出现在注释或 docstring 里也算作引用，所以结果是**宁可少报、不多报**。

**读结果时的提醒**：若 `prompts`／评测链路只 import 某个模块的“投影”函数，
该模块里的“状态变换”函数就可能合理地没有生产调用方——那是**架构分工**，不是未接线
（例：`relationship_world` 的状态变换在 SMAPI 侧完成，Bridge 只做投影）。
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bridge" / "src" / "stardew_ai_bridge"
PRODUCTION_DIRS = (SOURCE, ROOT / "scripts")
TEST_DIR = ROOT / "bridge" / "tests"

# 会不会发网络。必须把 provider 抽象也算进来：`--provider cloud` 这条路走的是
# `OpenAICompatibleProvider`，源码里根本没有 httpx/requests——早期检测因此**漏掉了
# 成本最高的 `run_character_quality_eval.py`**（单 NPC 评测累计约 5,514 万 tokens）。
_NETWORK_PATTERN = re.compile(
    r"httpx|requests\.|urllib|OpenAICompatibleProvider|--provider"
)


def _code_without_docstrings(text: str) -> str:
    """返回去掉注释与 docstring 的代码文本。

    否则本文件 docstring 里**列举**的那些模式会把脚本自己匹配成“会发网络”。
    `ast.unparse` 同时会丢掉注释，所以注释里的举例也不会误伤。
    """

    tree = ast.parse(text)
    holders = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            node.body = body[1:]
    return ast.unparse(tree)


def _read_all(directories: tuple[pathlib.Path, ...] | list[pathlib.Path]) -> list[str]:
    texts: list[str] = []
    for base in directories:
        for path in sorted(base.glob("*.py")):
            try:
                texts.append(path.read_text(encoding="utf-8"))
            except OSError:
                continue
    return texts


def _count(name: str, texts: list[str]) -> int:
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    return sum(len(pattern.findall(text)) for text in texts)


def _public_definitions() -> list[tuple[str, str, bool]]:
    """返回 (名字, 模块文件名, 是否带装饰器) 的列表。"""

    found: list[tuple[str, str, bool]] = []
    for path in sorted(SOURCE.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in module.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if node.name.startswith("_"):
                continue
            found.append((node.name, path.name, bool(node.decorator_list)))
    return found


def _report_references(limit: int) -> None:
    production = _read_all(PRODUCTION_DIRS)
    tests = _read_all([TEST_DIR])

    unreferenced: list[tuple[str, str, int, bool]] = []
    for name, module, decorated in _public_definitions():
        # 关键：只减掉“定义本身”这一次出现，而不是排除整个定义文件。
        if _count(name, production) - 1 > 0:
            continue
        unreferenced.append((name, module, _count(name, tests), decorated))

    routed = [row for row in unreferenced if row[3]]
    candidates = [row for row in unreferenced if not row[3]]
    tested = [row for row in candidates if row[2] > 0]
    untested = [row for row in candidates if row[2] == 0]

    print(f"Bridge 顶层公开名字在生产代码里零引用：{len(unreferenced)} 个")
    print()
    print(f"[装饰器注册，非死代码] {len(routed)} 个（多为 FastAPI 路由）")
    for name, module, _, _ in routed[:limit]:
        print(f"  · {name:<34} {module}")
    print()
    print(f"[只被测试引用] {len(tested)} 个 —— 公开 API 没有生产调用方（可能是预留或架构分工）")
    for name, module, tests_n, _ in sorted(tested, key=lambda row: -row[2])[:limit]:
        print(f"  · {name:<34} {module:<28} 测试 {tests_n} 次")
    print()
    print(f"[连测试都没引用] {len(untested)} 个 —— 死代码的首要候选")
    if untested:
        for name, module, _, _ in untested[:limit]:
            print(f"  · {name:<34} {module}")
    else:
        print("  （没有）")


def _report_script_guards() -> None:
    """扫 `scripts/*.py` 的四类标记，重点标出“会发网络但没有确认门”的脚本。

    2026-09-20 做这项审计时发现：15 个脚本里只有 `run_group_dialogue_cloud_batch.py`
    带 `--confirm-cloud`，而**成本最高**的 `run_character_quality_eval.py --provider cloud`
    反而没有任何确认门（单 NPC 评测累计消耗约 5,514 万 tokens，是群聊的约 100 倍）。
    """

    rows: list[tuple[str, bool, bool, bool, bool]] = []
    own_name = pathlib.Path(__file__).name
    for path in sorted((ROOT / "scripts").glob("*.py")):
        if path.name == own_name:
            # 跳过自己：本文件源码里就写着那些要匹配的模式字符串，否则必然自我匹配。
            continue
        # 只看**代码**：去掉注释与 docstring，避免列举模式的文档把自己匹配成风险项。
        code = _code_without_docstrings(path.read_text(encoding="utf-8"))
        rows.append(
            (
                path.name,
                bool(_NETWORK_PATTERN.search(code)),
                bool(re.search(r"--confirm|dry[_-]?run", code)),
                "__main__" in code,
                bool(re.search(r"write_text|\.writelines?\b|json\.dump", code)),
            )
        )

    print()
    print("scripts/*.py 的安全门（网络 / 确认门 / 写盘）：")
    risky = [row for row in rows if row[1] and not row[2]]
    for name, net, guarded, has_main, writes in rows:
        flags = [
            "网络" if net else "    ",
            "确认" if guarded else "    ",
            "写盘" if writes else "    ",
            "入口" if has_main else "    ",
        ]
        mark = "  <-- 会发网络但没有确认门，请确认是否符合预期" if (net and not guarded) else ""
        print(f"  {name:<40} {' '.join(flags)}{mark}")
    if not risky:
        print("  （没有“发网络但无确认门”的脚本）")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20, help="每类最多展示多少条")
    parser.add_argument(
        "--only",
        choices=("references", "guards"),
        help="只跑其中一节；默认两节都跑",
    )
    args = parser.parse_args()

    if args.only in (None, "references"):
        _report_references(args.limit)
    if args.only in (None, "guards"):
        _report_script_guards()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
