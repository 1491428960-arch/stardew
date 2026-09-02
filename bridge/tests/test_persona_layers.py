from __future__ import annotations

from pathlib import Path

from stardew_ai_bridge.personas import PersonaStore


PERSONAS_DIR = Path(__file__).parents[2] / "data" / "personas"


def test_female_bachelors_adds_expression_layer_without_replacing_base_persona() -> None:
    store = PersonaStore(PERSONAS_DIR)
    persona = store.get_persona("Shane", ["female-bachelors"])

    assert "直白" in persona["voiceStyle"]["tone"]
    assert persona["genderPresentation"]["layer"] == "expression_only"
    assert persona["genderPresentation"]["basePersonaPriority"] == "higher"


def test_each_feminine_overlay_has_distinct_expression_and_affection_cues() -> None:
    store = PersonaStore(PERSONAS_DIR)
    overlays = {
        npc_id: store.get_persona(npc_id, ["female-bachelors"])[
            "genderPresentation"
        ]
        for npc_id in ("Shane", "Sebastian", "Alex")
    }

    assert all(
        overlay["layer"] == "expression_only"
        and overlay["basePersonaPriority"] == "higher"
        and overlay["toneAdjustments"]
        and overlay["affectionExpression"]
        for overlay in overlays.values()
    )
    assert len(
        {
            tuple(overlay["toneAdjustments"])
            for overlay in overlays.values()
        }
    ) == 3


def test_feminine_overlay_does_not_replace_canonical_topics_or_core_traits() -> None:
    store = PersonaStore(PERSONAS_DIR)

    for npc_id in ("Shane", "Sebastian", "Alex"):
        base = store.get_persona(npc_id)
        feminine = store.get_persona(npc_id, ["female-bachelors"])

        assert feminine["coreTraits"] == base["coreTraits"]
        assert feminine["voiceStyle"]["preferredTopics"] == base["voiceStyle"][
            "preferredTopics"
        ]
