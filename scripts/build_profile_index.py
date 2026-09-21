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
        "--corpus",
        action="append",
        default=[],
        type=Path,
        help="可重复指定已导出的对白语料 JSON",
    )
    parser.add_argument(
        "--vanilla-root",
        type=Path,
        help="已解包的 vanilla Dialogue JSON 根目录",
    )
    parser.add_argument(
        "--vanilla-events-root",
        type=Path,
        help="已解包的 vanilla Data/Events JSON 根目录",
    )
    parser.add_argument(
        "--vanilla-extra-dialogue-root",
        type=Path,
        help=(
            "已解包的 vanilla Data/ExtraDialogue JSON 所在目录（通常就是 "
            "Content (unpacked)/Data）；同目录树的 Data/Characters.json 与 "
            "Strings/NPCNames.<locale>.json 用来判定每个键的说话人"
        ),
    )
    parser.add_argument(
        "--vanilla-locale",
        help="原版对白语言后缀，例如 zh-CN；未指定时保留所有语言文件",
    )
    parser.add_argument(
        "--runtime-samples",
        action="append",
        default=[],
        type=Path,
        help="运行时解析对白 JSONL，可重复指定",
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

    missing_corpora = [path for path in args.corpus if not path.is_file()]
    if missing_corpora:
        for path in missing_corpora:
            print(f"corpus file not found: {path}", file=sys.stderr)
        return 2
    if args.vanilla_root is not None and not args.vanilla_root.is_dir():
        print(f"vanilla root not found: {args.vanilla_root}", file=sys.stderr)
        return 2
    if (
        args.vanilla_extra_dialogue_root is not None
        and not args.vanilla_extra_dialogue_root.is_dir()
    ):
        print(
            "vanilla extra dialogue root not found: "
            f"{args.vanilla_extra_dialogue_root}",
            file=sys.stderr,
        )
        return 2
    missing_runtime_samples = [path for path in args.runtime_samples if not path.is_file()]
    if missing_runtime_samples:
        for path in missing_runtime_samples:
            print(f"runtime samples not found: {path}", file=sys.stderr)
        return 2

    index = ProfileIndexBuilder(args.persona_dir).build(
        args.mod_root,
        corpus_paths=args.corpus,
        vanilla_root=args.vanilla_root,
        vanilla_events_root=args.vanilla_events_root,
        vanilla_extra_dialogue_root=args.vanilla_extra_dialogue_root,
        vanilla_locale=args.vanilla_locale,
        runtime_sample_paths=args.runtime_samples,
    )
    try:
        ProfileIndexBuilder.write(index, args.output)
    except OSError as error:
        print(f"cannot write profile index: {error}", file=sys.stderr)
        return 2

    profiles = index.get("profiles", {})
    samples = index.get("styleSamples", [])
    speech_evidence = index.get("speechEvidence", [])
    knowledge_facts = index.get("knowledgeFacts", [])
    warnings = index.get("warnings", [])
    print(
        f"profile index written: {args.output} "
        f"profiles={len(profiles) if isinstance(profiles, dict) else 0} "
        f"styleSamples={len(samples) if isinstance(samples, list) else 0} "
        f"speechEvidence={len(speech_evidence) if isinstance(speech_evidence, list) else 0} "
        f"knowledgeFacts={len(knowledge_facts) if isinstance(knowledge_facts, list) else 0} "
        f"warnings={len(warnings) if isinstance(warnings, list) else 0}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
