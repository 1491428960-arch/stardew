"""列出完全没有测试覆盖的函数/方法（按 AST 判定，比逐行看行号高效）。

先有覆盖率数据再跑：

    $env:PYTHONPATH='bridge/src;scripts'
    py -3.10 -B -m pytest bridge/tests -q -p no:cacheprovider `
        --ignore=bridge/tests/test_api.py --ignore=bridge/tests/test_chat_intents.py `
        --ignore=bridge/tests/test_external_dialogue_lab.py `
        --ignore=bridge/tests/test_npc_bubble_frame_materials.py `
        --ignore=bridge/tests/test_npc_bubble_elements.py --ignore=bridge/tests/test_npc_bubble_objects.py `
        --cov=stardew_ai_bridge --cov-report=
    py -3.10 -B scripts/find_uncovered_functions.py [--limit 40]

判定口径：函数体内**一行都没执行过**才算“整段未覆盖”；部分覆盖的函数不列出
（那些属于分支补齐，成本高、优先级低）。
"""

from __future__ import annotations

import argparse
import ast
import pathlib

import coverage

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "bridge" / "src" / "stardew_ai_bridge"


def _executed_lines(data: coverage.CoverageData) -> dict[pathlib.Path, set[int]]:
    measured: dict[pathlib.Path, set[int]] = {}
    for recorded in data.measured_files():
        key = pathlib.Path(recorded).resolve()
        measured[key] = set(data.lines(recorded) or ())
    return measured


def _function_span(node: ast.AST) -> tuple[int, int]:
    start = getattr(node, "lineno", 0)
    end = start
    for child in ast.walk(node):
        end = max(end, getattr(child, "lineno", start))
        end = max(end, getattr(child, "end_lineno", start) or start)
    return start, end


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40, help="最多列出多少条（按函数体行数降序）")
    parser.add_argument("--min-lines", type=int, default=3, help="忽略小于该行数的小函数")
    args = parser.parse_args()

    cover = coverage.Coverage(data_file=str(ROOT / ".coverage"))
    cover.load()
    executed_by_file = _executed_lines(cover.get_data())

    findings: list[tuple[int, str, str, int]] = []
    for path in sorted(TARGET.glob("*.py")):
        resolved = path.resolve()
        if resolved not in executed_by_file:
            continue
        ran = executed_by_file[resolved]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            start, end = _function_span(node)
            span = set(range(start, end + 1))
            if span & ran:
                continue
            size = end - start + 1
            if size < args.min_lines:
                continue
            findings.append((size, path.name, node.name, start))

    findings.sort(reverse=True)
    total = len(findings)
    print(f"整段未覆盖的函数：{total} 个（按函数体行数降序，显示前 {min(args.limit, total)} 个）")
    for size, module, name, start in findings[: args.limit]:
        print(f"  {size:4d} 行  {module}:{start}  {name}()")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
