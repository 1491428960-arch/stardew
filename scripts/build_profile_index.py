from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "bridge" / "src"))

from stardew_ai_bridge.profile_index import ProfileIndexBuilder  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="构建 Stardew AI NPC 离线资料索引")
    parser.add_argument(
        "--persona-dir",
        required=True,
        type=Path,
        help="项目内人设 JSON 目录",
    )
    parser.add_argument(
        "--mod-root",
        action="append",
        default=[],
        type=Path,
        help="可重复指定已安装 Mod 根目录",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="明确指定的派生索引输出路径",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.persona_dir.is_dir():
        print(f"persona directory not found: {args.persona_dir}", file=sys.stderr)
        return 2
    missing_roots = [root for root in args.mod_root if not root.is_dir()]
    if missing_roots:
        for root in missing_roots:
            print(f"mod root not found: {root}", file=sys.stderr)
        return 2

    index = ProfileIndexBuilder(args.persona_dir).build(args.mod_root)
    try:
        ProfileIndexBuilder.write(index, args.output)
    except OSError as error:
        print(f"cannot write profile index: {error}", file=sys.stderr)
        return 2

    profiles = index.get("profiles", {})
    samples = index.get("styleSamples", [])
    warnings = index.get("warnings", [])
    print(
        f"profile index written: {args.output} "
        f"profiles={len(profiles) if isinstance(profiles, dict) else 0} "
        f"styleSamples={len(samples) if isinstance(samples, list) else 0} "
        f"warnings={len(warnings) if isinstance(warnings, list) else 0}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
