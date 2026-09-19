"""`ProfileIndexStore.voice_card` 的阶段锚点解析，重点是 dating 的“最后回退”规则。

2026-09-20 用覆盖率定位到 `profile_index.py` 只有 88%，其中 **L2532–2547 是连续 16 行未覆盖**
（`collect_stage_candidates()` 的 `allow_nearby_stage` 分支）。读通之后，它的语义是：

    请求 dating 时先精确收集；**只有当候选里连 close/friend/acquaintance 都没有**，
    才再收一次并**允许 stranger** 作为最后回退——免得 stranger 压过 close/friend。

`speech._stage_distance` 里有同源的阶段距离规则（见 `test_speech_stage.py`），这里是它在
证据检索侧的对偶。

另外钉住 `voiceAnchors` 的来源过滤：**已启用内容包的对白优先于原版**，但原版仍作为补充保留，
避免只有少量覆盖层语料时语气锚点窗口为空。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.profile_index import ProfileIndexStore


def _evidence(sample_id: str, stage: str, text: str, source_mod: str = "Vanilla") -> dict[str, object]:
    return {
        "sampleId": sample_id,
        "npcId": "Shane",
        "text": text,
        "sourceMod": source_mod,
        "sourceKey": f"Mon{sample_id[-1]}",
        "sourcePath": "characters.json",
        "evidenceKind": "dialogue",
        "conditions": {"relationshipStage": stage},
    }


def _store(
    tmp_path: Path,
    *,
    evidence: list[dict[str, object]] | None = None,
    anchors: list[dict[str, object]] | None = None,
    schema_version: int = 2,
) -> ProfileIndexStore:
    index = {
        "schemaVersion": schema_version,
        "profiles": {},
        "voiceCards": {
            "Shane": {
                "npcId": "Shane",
                "features": {},
                "topicHints": [],
                "evidenceRefs": [],
                "voiceAnchors": anchors
                if anchors is not None
                else [{"sampleId": "base", "text": "原版锚点一句", "sourceMod": "Vanilla"}],
            }
        },
        "speechEvidence": evidence or [],
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return ProfileIndexStore(path)


def _anchor_texts(card: dict[str, object]) -> list[str]:
    return [str(item.get("text")) for item in card.get("voiceAnchors", [])]


# --- 基本结构 ---------------------------------------------------------------


def test_voice_card_returns_none_for_unknown_npc(tmp_path: Path) -> None:
    assert _store(tmp_path).voice_card("Nobody", source_mods=(), relationship_stage="") == {}


def test_voice_card_without_a_stage_keeps_the_static_anchors(tmp_path: Path) -> None:
    store = _store(tmp_path, evidence=[_evidence("s1", "dating", "dating 原文一句")])

    card = store.voice_card("Shane", source_mods=(), relationship_stage="")

    assert _anchor_texts(card) == ["原版锚点一句"]


# --- 精确阶段命中 -----------------------------------------------------------


def test_exact_stage_samples_replace_the_anchors(tmp_path: Path) -> None:
    store = _store(
        tmp_path,
        evidence=[
            _evidence("s1", "dating", "dating 原文一句"),
            _evidence("s2", "married", "married 原文一句"),
        ],
    )

    card = store.voice_card("Shane", source_mods=(), relationship_stage="dating")

    assert _anchor_texts(card) == ["dating 原文一句"]


# --- dating 的“最后回退”（本次补测的核心）----------------------------------


def test_dating_uses_nearby_stages_without_needing_the_fallback(tmp_path: Path) -> None:
    # 有 close 时，第一次收集就能拿到（has_dating_stage 为真），不需要允许 stranger。
    store = _store(
        tmp_path,
        evidence=[
            _evidence("s1", "close", "close 原文一句"),
            _evidence("s2", "stranger", "stranger 原文一句"),
        ],
    )

    card = store.voice_card("Shane", source_mods=(), relationship_stage="dating")

    assert "close 原文一句" in _anchor_texts(card)
    assert "stranger 原文一句" not in _anchor_texts(card)


def test_dating_falls_back_to_stranger_only_when_nothing_nearer_exists(
    tmp_path: Path,
) -> None:
    # 没有 dating/close/friend/acquaintance 时，才允许把 stranger 当作最后回退。
    store = _store(tmp_path, evidence=[_evidence("s1", "stranger", "stranger 原文一句")])

    card = store.voice_card("Shane", source_mods=(), relationship_stage="dating")

    assert _anchor_texts(card) == ["stranger 原文一句"]


def test_dating_does_not_borrow_post_marriage_samples(tmp_path: Path) -> None:
    # married/parent 不在允许借用的集合里：它们是婚后语境，借来会串味。
    store = _store(
        tmp_path,
        evidence=[
            _evidence("s1", "married", "married 原文一句"),
            _evidence("s2", "parent", "parent 原文一句"),
        ],
    )

    card = store.voice_card("Shane", source_mods=(), relationship_stage="dating")

    # 借不到任何东西 → 保留静态锚点，而不是清空
    assert _anchor_texts(card) == ["原版锚点一句"]


def test_other_stages_do_not_get_the_nearby_fallback(tmp_path: Path) -> None:
    # 只有 dating 有这条回退规则；请求 married 时 stranger 不该被借来。
    store = _store(tmp_path, evidence=[_evidence("s1", "stranger", "stranger 原文一句")])

    card = store.voice_card("Shane", source_mods=(), relationship_stage="married")

    assert _anchor_texts(card) == ["原版锚点一句"]


def test_no_evidence_at_all_keeps_the_static_anchors(tmp_path: Path) -> None:
    store = _store(tmp_path, evidence=[])

    card = store.voice_card("Shane", source_mods=(), relationship_stage="dating")

    assert _anchor_texts(card) == ["原版锚点一句"]


# --- 来源过滤 ---------------------------------------------------------------


def test_enabled_content_pack_anchors_come_before_vanilla(tmp_path: Path) -> None:
    store = _store(
        tmp_path,
        evidence=[],
        anchors=[
            {"sampleId": "v", "text": "原版锚点", "sourceMod": "Vanilla"},
            {"sampleId": "m", "text": "内容包锚点", "sourceMod": "FlashShifter.SVE"},
        ],
    )

    card = store.voice_card("Shane", source_mods=["SVE"], relationship_stage="")

    assert _anchor_texts(card) == ["内容包锚点", "原版锚点"]


def test_disabled_source_anchors_are_filtered_out(tmp_path: Path) -> None:
    store = _store(
        tmp_path,
        evidence=[],
        anchors=[
            {"sampleId": "v", "text": "原版锚点", "sourceMod": "Vanilla"},
            {"sampleId": "m", "text": "别的包锚点", "sourceMod": "SomeOtherMod"},
        ],
    )

    card = store.voice_card("Shane", source_mods=["SVE"], relationship_stage="")

    assert _anchor_texts(card) == ["原版锚点"]


def test_anchors_are_capped_at_eight(tmp_path: Path) -> None:
    anchors = [
        {"sampleId": f"a{i}", "text": f"锚点{i}", "sourceMod": "Vanilla"} for i in range(12)
    ]
    store = _store(tmp_path, evidence=[], anchors=anchors)

    assert len(store.voice_card("Shane", source_mods=(), relationship_stage="")["voiceAnchors"]) == 8


# --- schemaVersion 1 的兼容 -------------------------------------------------


def test_schema_v1_falls_back_to_style_samples(tmp_path: Path) -> None:
    # 旧索引没有 speechEvidence 时，阶段证据要从 styleSamples 取。
    index = {
        "schemaVersion": 1,
        "profiles": {},
        "voiceCards": {
            "Shane": {
                "npcId": "Shane",
                "features": {},
                "topicHints": [],
                "evidenceRefs": [],
                "voiceAnchors": [{"sampleId": "base", "text": "原版锚点一句", "sourceMod": "Vanilla"}],
            }
        },
        "styleSamples": [_evidence("s1", "dating", "旧索引 dating 原文")],
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    card = ProfileIndexStore(path).voice_card("Shane", source_mods=(), relationship_stage="dating")

    assert _anchor_texts(card) == ["旧索引 dating 原文"]
