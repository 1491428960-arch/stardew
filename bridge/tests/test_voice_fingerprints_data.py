"""`data/voice-fingerprints.json` 的数据闸。

语料（`artifacts/`）不入版本控制，所以这里只钉**产物**与**产物自洽性**；
「产物是否与语料一致」由 `scripts/mine_voice_fingerprint.py --check` 负责。
"""

from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.voice_fingerprint import (
    PROMPT_PARTICLE_LIMIT,
    THIN_EVIDENCE_THRESHOLD,
    load_voice_fingerprints,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "voice-fingerprints.json"
PERSONAS_DIR = ROOT / "data" / "personas"

_EVIDENCE_LEVELS = {"spoken", "thin", "event_only", "none"}
_GAP_FIELDS = {"code", "severity", "detail"}


def _persona_ids() -> set[str]:
    ids: set[str] = set()
    for path in sorted(PERSONAS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("personas"), dict):
            ids.update(payload["personas"])
    return ids


def test_fingerprint_data_lives_outside_the_persona_directory() -> None:
    """`data/personas/` 下每个 JSON 的顶层都会被 `PersonaStore._load()` 当条目表。

    指纹表放进去会变成一个叫 `voiceFingerprints` 的垃圾 NPC —— 关系表踩过同型坑
    （见 `test_persona_store_load.py`）。
    """

    assert DATA.is_file(), f"缺少指纹数据：{DATA}"
    assert not (PERSONAS_DIR / "voice-fingerprints.json").exists()


def test_payload_declares_the_basics() -> None:
    payload = load_voice_fingerprints(DATA)
    assert payload["version"] == 1
    assert payload["generatedBy"] == "scripts/mine_voice_fingerprint.py"
    assert payload["corpus"].startswith("artifacts/corpus/")
    assert payload["speakerCount"] == len(payload["speakers"]) > 0
    assert payload["spokenRecords"] > 0


def test_the_corpus_still_resolves_its_i18n_references() -> None:
    """`{` 的残留量是「语料有没有退回未解析状态」的哨兵。

    2026-09-26 实测：读错字段时看到 18373 个 `{`（全是 CP 模板）；读对之后是两位数。
    """

    payload = load_voice_fingerprints(DATA)
    assert payload["residualMarkers"].get("{", 0) < 1000


def test_every_persona_has_a_fingerprint_entry() -> None:
    payload = load_voice_fingerprints(DATA)
    missing = sorted(_persona_ids() - set(payload["speakers"]))
    assert not missing, f"这些人设有条目却没有指纹：{missing}"


def test_every_speaker_declares_a_known_evidence_level() -> None:
    payload = load_voice_fingerprints(DATA)
    for name, speaker in payload["speakers"].items():
        assert speaker["evidenceLevel"] in _EVIDENCE_LEVELS, name
        assert speaker["spokenCount"] >= 0
        assert speaker["eventCount"] >= 0


def test_particle_counts_are_positive_and_sorted() -> None:
    payload = load_voice_fingerprints(DATA)
    for name, speaker in payload["speakers"].items():
        counts = [count for _, count in speaker["particles"]]
        assert counts == sorted(counts, reverse=True), name
        assert all(count > 0 for count in counts), name


def test_particle_table_is_not_truncated() -> None:
    """语气字表必须**全量**存 —— 只留 top10 会把排在第 11 位之后的真实用字误判成
    「原文 0 次」，从而产出假警报。"""

    payload = load_voice_fingerprints(DATA)
    leah = payload["speakers"]["Leah"]
    counts = dict(leah["particles"])
    assert len(counts) > 10
    assert min(counts.values()) == 1


def test_thin_speakers_are_marked_thin() -> None:
    payload = load_voice_fingerprints(DATA)
    for name, speaker in payload["speakers"].items():
        if 0 < speaker["spokenCount"] < THIN_EVIDENCE_THRESHOLD:
            assert speaker["evidenceLevel"] == "thin", name


def test_gaps_are_structured() -> None:
    payload = load_voice_fingerprints(DATA)
    for name, speaker in payload["speakers"].items():
        for gap in speaker["gaps"]:
            assert set(gap) == _GAP_FIELDS, (name, gap)
            assert gap["severity"] in {"high", "medium", "low"}, (name, gap)


def test_aliases_carry_their_evidence() -> None:
    """别名归一必须带证据路径 —— 否则就是又一次「凭印象合并角色」。"""

    payload = load_voice_fingerprints(DATA)
    aliases = payload.get("aliases") or {}
    assert aliases, "SVE 的 MorrisTod / MarlonFay / GuntherSilvian 必须被归一"
    for alias, info in aliases.items():
        assert f"/{info['target']}/" in info["evidence"], alias


def test_alias_targets_absorb_their_corpus() -> None:
    """归一后这三个角色的证据量必须**明显高于**只算短名时 —— 否则归一没生效。"""

    payload = load_voice_fingerprints(DATA)
    for name, floor in (("Morris", 100), ("Marlon", 80), ("Gunther", 50)):
        assert payload["speakers"][name]["spokenCount"] >= floor, name


def test_lewis_pilot_declares_only_particles_his_corpus_actually_uses() -> None:
    """Lewis 是语言层改造的试点：声明的语气字必须全部有原文出处。"""

    payload = load_voice_fingerprints(DATA)
    lewis = payload["speakers"]["Lewis"]
    codes = {gap["code"] for gap in lewis["gaps"]}
    assert "particle_not_in_corpus" not in codes, lewis["gaps"]
    counts = dict(lewis["particles"])
    for particle in lewis["declaredParticles"]:
        assert counts.get(particle, 0) > 0, particle


def test_lewis_pilot_declares_no_more_than_the_prompt_keeps() -> None:
    """写第 5 个语气字是净损失（prompt 只取前 4 个），试点里已经删掉了。"""

    payload = load_voice_fingerprints(DATA)
    lewis = payload["speakers"]["Lewis"]
    assert 0 < len(lewis["declaredParticles"]) <= PROMPT_PARTICLE_LIMIT
    assert "particle_over_prompt_limit" not in {gap["code"] for gap in lewis["gaps"]}


def test_lewis_pilot_particles_follow_his_corpus_frequency() -> None:
    """声明的顺序就是进 prompt 的顺序，必须按原文频次从高到低。"""

    payload = load_voice_fingerprints(DATA)
    lewis = payload["speakers"]["Lewis"]
    counts = dict(lewis["particles"])
    declared = lewis["declaredParticles"]
    assert declared == sorted(declared, key=lambda ch: -counts.get(ch, 0))
