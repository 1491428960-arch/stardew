#!/usr/bin/env python3
"""从对话语料生成全库角色的「语言指纹」，并与现有人设的语言层对照。

用法：

```powershell
# 生成数据（写 data/voice-fingerprints.json）
python scripts/mine_voice_fingerprint.py

# 只对照、不写盘（人设 vs 原文差异表）
python scripts/mine_voice_fingerprint.py --audit

# 差异表另存 markdown
python scripts/mine_voice_fingerprint.py --audit --audit-md .tmp/pipeline-audit/gaps.md

# 校验磁盘上的数据是否与语料一致（不被 --out 覆盖，退出码非 0 表示需要重生成）
python scripts/mine_voice_fingerprint.py --check
```

数据契约见 `stardew_ai_bridge/voice_fingerprint.py` 的模块文档；这里只负责 IO。

⚠ **输出不能放 `data/personas/`** —— `PersonaStore._load()` 把该目录下每个 JSON 的顶层
当条目表，放进去会变成一个叫 `voiceFingerprints` 的垃圾 NPC（2026-09-24 关系表踩过同型坑）。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "bridge" / "src"))

from stardew_ai_bridge.personas import NPC_ID_ALIASES, canonical_npc_id  # noqa: E402
from stardew_ai_bridge.voice_fingerprint import (  # noqa: E402
    SPOKEN_EVIDENCE_KINDS,
    THIN_EVIDENCE_THRESHOLD,
    build_fingerprint,
    dialogue_text,
    persona_particles,
    persona_voice_gaps,
    residual_markers,
    suggest_voice_style,
)

DEFAULT_CORPUS = (
    PROJECT_ROOT
    / "artifacts/corpus/20260923-extra-dialogue/vanilla-sve-rasmodia-dialogue-corpus.json"
)
DEFAULT_OUT = PROJECT_ROOT / "data" / "voice-fingerprints.json"
DEFAULT_PERSONA_DIR = PROJECT_ROOT / "data" / "personas"

SCHEMA_VERSION = 1

#: 别名表**只此一份**，住在生产侧（`personas.NPC_ID_ALIASES`）—— 索引构建、prompt、
#: 阶段策略、关系门控全都走 `canonical_npc_id()`，这里再抄一份就会分叉。
#: 本脚本比生产侧多做一件事：**逐条复验别名有证据**（`_alias_evidence()`），
#: 因为一个没有证据的别名会把两个不相干的角色悄悄并成一个。
SPEAKER_ALIASES = NPC_ID_ALIASES

#: 语料里由文件名/键名误判出来的伪 npcId —— 不是角色，不该出现在「谁还没有人设」里。
NON_SPEAKER_IDS = frozenset({"MarriageDialogue", "RoommateDialogue", "rainy"})

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _alias_evidence(
    alias: str, target: str, records: list[dict[str, Any]]
) -> str:
    """校验别名归一有据可依：别名的 sourcePath 里必须出现 `/<目标名>/`。"""

    paths = {
        str(record.get("sourcePath") or "")
        for record in records
        if str(record.get("npcId") or "") == alias
    }
    hits = sorted(path for path in paths if f"/{target}/" in path)
    if not hits:
        raise SystemExit(
            f"别名 {alias} → {target} 没有证据：它的 sourcePath 里没有 /{target}/。"
            f"（现有路径：{sorted(paths)[:3]}）"
        )
    return hits[0]


def load_personas(directory: Path) -> dict[str, tuple[str, dict[str, Any]]]:
    """读 `data/personas/*.json`，返回「角色键 → (文件名, 条目)」。

    只收顶层带 `personas` 的文件 —— 该目录里还混放着 `behavior-examples.json` 这类
    非人设数据（见 `tests/test_profile_index_persona_dir.py`）。
    """

    personas: dict[str, tuple[str, dict[str, Any]]] = {}
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        entries = payload.get("personas")
        if not isinstance(entries, dict):
            continue
        for key, profile in entries.items():
            if isinstance(profile, dict):
                personas.setdefault(str(key), (path.name, profile))
    return personas


def _fingerprint_speakers(
    records: list[dict[str, Any]],
    personas: dict[str, tuple[str, dict[str, Any]]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    by_npc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    raw_by_npc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        raw_id = str(record.get("npcId") or "")
        by_npc[canonical_npc_id(raw_id)].append(record)
        raw_by_npc[raw_id].append(record)

    aliases: dict[str, dict[str, str]] = {}
    for alias, target in SPEAKER_ALIASES.items():
        if target not in personas:
            continue
        if not raw_by_npc.get(alias):
            # 语料里已经没有这个名字了（Mod 改成短名就会这样）—— 别名自动退休，不是错误。
            continue
        aliases[alias] = {
            "target": target,
            "evidence": _alias_evidence(alias, target, records),
        }

    speakers: dict[str, dict[str, Any]] = {}
    for key, (file_name, profile) in sorted(personas.items()):
        fingerprint = build_fingerprint(by_npc.get(key, []))
        voice_style = profile.get("voiceStyle")
        voice = voice_style if isinstance(voice_style, dict) else {}
        gaps = persona_voice_gaps(voice, fingerprint)
        speakers[key] = {
            "npcId": str(profile.get("npcId") or key),
            "personaFile": file_name,
            "declaredParticles": persona_particles(voice),
            **fingerprint,
            "gaps": gaps,
        }
    return speakers, aliases


def build_payload(corpus_path: Path, persona_dir: Path = DEFAULT_PERSONA_DIR) -> dict[str, Any]:
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    records = payload["records"]
    personas = load_personas(persona_dir)
    speakers, aliases = _fingerprint_speakers(records, personas)

    spoken_records = [
        record
        for record in records
        if str(record.get("evidenceKind") or "") in SPOKEN_EVIDENCE_KINDS
    ]
    spoken_by_npc = Counter(
        canonical_npc_id(record.get("npcId") or "") for record in spoken_records
    )
    covered = set(personas) | NON_SPEAKER_IDS
    uncovered = sorted(
        npc
        for npc, count in spoken_by_npc.items()
        if count >= THIN_EVIDENCE_THRESHOLD and npc not in covered
    )

    return {
        "version": SCHEMA_VERSION,
        "generatedBy": "scripts/mine_voice_fingerprint.py",
        "corpus": str(corpus_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "corpusRecords": len(records),
        "spokenRecords": len(spoken_records),
        "residualMarkers": residual_markers(
            dialogue_text(record) for record in records
        ),
        "speakerCount": len(speakers),
        "aliases": aliases,
        "uncoveredNpcIds": uncovered,
        "speakers": speakers,
    }


def _without_timestamp(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "generatedAt"}


def _print_audit(payload: dict[str, Any]) -> None:
    speakers = payload["speakers"]
    code_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()

    print(f"语料 {payload['corpus']}")
    print(
        f"总记录 {payload['corpusRecords']}　出声证据 {payload['spokenRecords']}"
        f"　人设角色 {payload['speakerCount']}"
    )
    if payload["residualMarkers"]:
        print(f"残留标记（未静默删除）：{payload['residualMarkers']}")

    print()
    print("=== 证据分级 ===")
    level_counts = Counter(item["evidenceLevel"] for item in speakers.values())
    for level, count in level_counts.most_common():
        print(f"  {level:12} {count}")
    thin = [k for k, v in speakers.items() if v["evidenceLevel"] in {"thin", "event_only", "none"}]
    if thin:
        print(f"  ⚠ 证据不足：{'、'.join(sorted(thin))}")

    print()
    print("=== 与现有人设的语言层落差 ===")
    rows: list[tuple[int, str, list[dict[str, str]]]] = []
    for key, item in speakers.items():
        gaps = item.get("gaps") or []
        for gap in gaps:
            code_counts[gap["code"]] += 1
            severity_counts[gap["severity"]] += 1
        if gaps:
            rank = min(_SEVERITY_ORDER.get(gap["severity"], 9) for gap in gaps)
            rows.append((rank, key, gaps))
    rows.sort(key=lambda row: (row[0], row[1]))
    for rank, key, gaps in rows:
        item = speakers[key]
        particle_text = " ".join(f"{c}{n}" for c, n in item["particles"][:5]) or "—"
        print(
            f"  [{['high', 'medium', 'low'][rank]}] {key}（出声 {item['spokenCount']}，"
            f"句长中位 {item['sentenceLength']['median']:.0f}，语气字 {particle_text}）"
        )
        for gap in gaps:
            print(f"      - ({gap['severity']}) {gap['detail']}")

    print()
    print("=== 汇总 ===")
    for code, count in code_counts.most_common():
        print(f"  {code:28} {count}")
    print(
        f"  受影响角色 {len(rows)}／{payload['speakerCount']}"
        f"　（high {severity_counts['high']} / medium {severity_counts['medium']}"
        f" / low {severity_counts['low']}）"
    )

    uncovered = payload.get("uncoveredNpcIds") or []
    if uncovered:
        print(
            f"  语料里有出声证据、但人设里没有的角色（{len(uncovered)}）："
            f"{'、'.join(uncovered)}"
        )


def _audit_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 语言层「人设 vs 原文」差异表",
        "",
        f"- 语料：`{payload['corpus']}`（{payload['corpusRecords']} 条，"
        f"其中出声证据 {payload['spokenRecords']} 条）",
        f"- 覆盖角色：{payload['speakerCount']}",
        "",
        "| 角色 | 出声条数 | 句长中位 | 发言中位 | 原文前 5 语气字 | 人设声明 | 问题 |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for key, item in sorted(payload["speakers"].items()):
        particles = " ".join(f"{c}{n}" for c, n in item["particles"][:5]) or "—"
        declared = item.get("declaredParticles")
        declared_text = " ".join(declared) if declared else "—"
        problems = "；".join(gap["detail"] for gap in item.get("gaps") or []) or "—"
        lines.append(
            f"| {key} | {item['spokenCount']} | {item['sentenceLength']['median']:.0f} | "
            f"{item['utteranceLength']['median']:.0f} | {particles} | {declared_text} | {problems} |"
        )
    lines.append("")
    return "\n".join(lines)


#: 草稿里**可精确判定**的字段：照抄即用（原话与语气字都是从语料里直接取的）。
_EXACT_FIELDS = ("speechParticleHints", "openers")

#: 草稿里**重述**的字段：它们是数字堆出来的骨架，与现状「说法不同」不等于「现状错」
#: —— 人写的「一句话通常十来个字」和草稿的「12 字上下」是同一件事。
_RESTATED_FIELDS = ("sentencePattern", "tone")


def _print_suggestion(key: str, item: dict[str, Any]) -> None:
    header = (
        f"[{item['evidenceLevel']}] {key}（{item['personaFile']}，"
        f"出声 {item['spokenCount']}）"
    )
    changed = item.get("changedFields") or []
    if not changed:
        print(f"  ── {header}：4 个字段与原文一致，不用改")
        return
    print(f"  ── {header}：建议改 {'、'.join(changed)}")
    for field in ("speechParticleHints", "sentencePattern", "tone", "openers"):
        if field not in (item.get("suggested") or {}):
            continue
        now = item["current"].get(field) or "—"
        if isinstance(now, list):
            now = " / ".join(now) if now else "—"
        want = item["suggested"][field]
        if isinstance(want, list):
            want = " / ".join(want)
        if field not in changed:
            mark = "="
        elif field in _EXACT_FIELDS:
            mark = "≠"  # 照抄即可
        else:
            mark = "~"  # 重述：现状若已有等价说法，不用动
        print(f"       {mark} {field}")
        print(f"           现状 {now}")
        print(f"           建议 {want}")
    for note in item.get("notes") or []:
        print(f"       ! {note}")


def _build_suggestions(
    payload: dict[str, Any],
    personas: dict[str, tuple[str, dict[str, Any]]],
    *,
    wanted: set[str] | None,
    severity: str | None,
) -> dict[str, Any]:
    suggestions: dict[str, Any] = {}
    for key, (file_name, profile) in sorted(personas.items()):
        if wanted and key not in wanted:
            continue
        speaker = payload["speakers"].get(key) or {}
        if severity and severity not in {
            gap["severity"] for gap in speaker.get("gaps") or []
        }:
            continue
        voice_style = profile.get("voiceStyle")
        draft = suggest_voice_style(
            voice_style if isinstance(voice_style, dict) else {},
            speaker,
        )
        suggestions[key] = {"personaFile": file_name, **draft}
    return suggestions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--personas", type=Path, default=DEFAULT_PERSONA_DIR)
    parser.add_argument("--audit", action="store_true", help="打印人设 vs 原文差异表")
    parser.add_argument("--audit-md", type=Path, default=None, help="差异表另存 markdown")
    parser.add_argument("--check", action="store_true", help="只校验，不写盘")
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="按原文生成 voiceStyle 草稿（**只出草稿，绝不改 data/personas/**）",
    )
    parser.add_argument(
        "--suggest-out",
        type=Path,
        default=PROJECT_ROOT / ".tmp" / "voice-suggest" / "voice-suggestions.json",
    )
    parser.add_argument("--suggest-npc", default="", help="只出这些角色的草稿（逗号分隔）")
    parser.add_argument(
        "--suggest-severity",
        choices=("high", "medium", "low"),
        default=None,
        help="只出该严重度角色的草稿",
    )
    args = parser.parse_args()

    if not args.corpus.is_file():
        print(f"找不到语料：{args.corpus}", file=sys.stderr)
        print("（语料由 scripts/export_dialogue_corpus.py 从解包 Content 生成）", file=sys.stderr)
        return 2

    payload = build_payload(args.corpus, args.personas)

    if args.check:
        if not args.out.is_file():
            print(f"数据文件不存在：{args.out}", file=sys.stderr)
            return 1
        current = json.loads(args.out.read_text(encoding="utf-8"))
        if _without_timestamp(current) != _without_timestamp(payload):
            print("指纹数据已过期：重新运行 scripts/mine_voice_fingerprint.py", file=sys.stderr)
            return 1
        print(f"指纹数据与语料一致（{payload['speakerCount']} 个角色）")
        return 0

    if args.suggest:
        wanted = {
            name.strip() for name in args.suggest_npc.split(",") if name.strip()
        } or None
        suggestions = _build_suggestions(
            payload,
            load_personas(args.personas),
            wanted=wanted,
            severity=args.suggest_severity,
        )
        args.suggest_out.parent.mkdir(parents=True, exist_ok=True)
        args.suggest_out.write_text(
            json.dumps(suggestions, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"=== voiceStyle 草稿（{len(suggestions)} 个角色）===")
        print("⚠ 这是草稿，不是成品：")
        print("   ≠ 语气字 / 开场原话 —— 直接从语料取的，可照抄")
        print("   ~ 句式 / 语气 —— 数字堆出来的骨架，要改成人话；")
        print("     现状若有等价说法（如「十来个字」对「12 字上下」）就不用动")
        for key, item in sorted(suggestions.items()):
            _print_suggestion(key, item)
        print(f"\n已写入 {args.suggest_out}")
        print("⚠ 不会动 data/personas/ —— 人工审完再手改，或另写应用脚本")
        return 0

    if args.audit:
        _print_audit(payload)

    if args.audit_md:
        args.audit_md.parent.mkdir(parents=True, exist_ok=True)
        args.audit_md.write_text(_audit_markdown(payload), encoding="utf-8")
        print(f"差异表已写入 {args.audit_md}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写入 {args.out}（{payload['speakerCount']} 个角色）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
