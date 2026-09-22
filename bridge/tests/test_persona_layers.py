from __future__ import annotations

from pathlib import Path

import pytest

import stardew_ai_bridge.personas as personas_module
from stardew_ai_bridge.personas import PersonaStore


PERSONAS_DIR = Path(__file__).parents[2] / "data" / "personas"


NORMAL_SVE_BATCH_ONE = (
    ("Victor", "he", "him", "his", "工程", "创造"),
    ("Olivia", "she", "her", "her", "生活品质", "家人"),
    ("Andy", "he", "him", "his", "农场", "务实"),
)

NORMAL_SVE_BATCH_TWO = (
    ("Lance", "he", "him", "his", "冒险", "探索"),
    ("Claire", "she", "her", "her", "谨慎", "新生活"),
    ("Morris", "he", "him", "his", "经营", "结果"),
)


NORMAL_VANILLA_BATCH_ONE = (
    ("Abigail", "冒险", "矿洞"),
    ("Emily", "创作", "布料"),
    ("Haley", "摄影", "审美"),
    ("Leah", "雕塑", "自然"),
)

NORMAL_VANILLA_BATCH_TWO = (
    ("Penny", "教学", "书籍"),
    ("Maru", "发明", "实验"),
    ("Jodi", "家庭", "做饭"),
    ("Robin", "木工", "建筑"),
)

NORMAL_VANILLA_BATCH_THREE = (
    ("Clint", "铁匠", "矿石", "he", "him", "his"),
    ("Demetrius", "科学", "研究", "he", "him", "his"),
    ("Evelyn", "花园", "烘焙", "she", "her", "her"),
    ("George", "生活", "经验", "he", "him", "his"),
)

NORMAL_VANILLA_BATCH_FOUR = (
    ("Gus", "食物", "酒馆", "he", "him", "his"),
    ("Kent", "家庭", "回归", "he", "him", "his"),
    ("Lewis", "小镇", "责任", "he", "him", "his"),
    ("Pam", "公交", "直率", "she", "her", "her"),
)

NORMAL_VANILLA_BATCH_FIVE = (
    ("Pierre", "商店", "经营", "he", "him", "his"),
    ("Sandy", "沙漠", "商店", "she", "her", "her"),
    ("Willy", "钓鱼", "海边", "he", "him", "his"),
    ("Dwarf", "矿洞", "矿石", "he", "him", "his"),
)

NORMAL_VANILLA_BATCH_SIX = (
    ("Krobus", "下水道", "孤独", "he", "him", "his"),
    ("Jas", "童年", "跳绳", "she", "her", "her"),
    ("Vincent", "童年", "昆虫", "he", "him", "his"),
)


# 用户口径：只保留**游戏里有好感度／社交面板**的角色 ⇒ `Birdie` 被删
# （游戏侧 `SocialTab=HiddenAlways`，且**不在**存档 friendshipData 名单里）。
#
# `Gunther` 一度也按 `SocialTab=HiddenAlways` 删过，后按**同一条判据**恢复：
# `data/friendship-roster.json`（真实存档 `Wofs_412086775` 的 `player.friendshipData`
# 导出）里 `GuntherSilvian` 在列 —— 而那正是留用 `Marlon`（`MarlonFay`）与
# `Morris`（`MorrisTod`）的同一份名单；`docs/active-work.md` 记明
# `GuntherSilvian` → `Gunther` 是同一角色。删的只是角色条目，索引语料没动。
SPECIAL_VANILLA_BATCH = (
    ("Leo", "he", "him", "his", "岛屿", "鹦鹉"),
    ("Gunther", "he", "him", "his", "博物馆", "文物"),
    ("Marlon", "he", "him", "his", "冒险者公会", "矿洞"),
)


def test_female_bachelors_eligibility_is_limited_to_male_romanceable_roles() -> None:
    eligible = {
        "Wizard",
        "Rasmodia",
        "Shane",
        "Sebastian",
        "Alex",
        "Elliott",
        "Harvey",
        "Sam",
    }
    ineligible = {
        "Sophia",
        "Caroline",
        "Marnie",
        "Linus",
        "Victor",
        "Abigail",
        "Emily",
        "Haley",
        "Leah",
        "Penny",
        "Maru",
        "Jodi",
        "Robin",
        "Clint",
        "Demetrius",
        "Evelyn",
        "George",
        "Gus",
        "Kent",
        "Lewis",
        "Pam",
        "Pierre",
        "Sandy",
        "Willy",
        "Dwarf",
        "Krobus",
        "Jas",
        "Vincent",
        "Leo",
        "Gunther",
        "Marlon",
    }

    checker = getattr(personas_module, "is_female_bachelor_eligible")

    assert all(checker(npc_id) for npc_id in eligible)
    assert not any(checker(npc_id) for npc_id in ineligible)


@pytest.mark.parametrize(
    ("npc_id", "subject", "object_", "possessive", "topic_one", "topic_two"),
    NORMAL_SVE_BATCH_ONE,
)
def test_first_normal_sve_batch_has_complete_gendered_voice_cards_without_overlay(
    npc_id: str,
    subject: str,
    object_: str,
    possessive: str,
    topic_one: str,
    topic_two: str,
) -> None:
    store = PersonaStore(PERSONAS_DIR)
    persona = store.get_persona(npc_id, ["SVE"])

    assert persona["npcId"] == npc_id
    assert persona["displayName"] == npc_id
    assert persona["pronouns"] == {
        "subject": subject,
        "object": object_,
        "possessive": possessive,
    }
    assert "genderPresentation" not in persona
    assert "female-bachelors" not in str(persona.get("modOverlay", {}))
    assert topic_one in str(persona["voiceStyle"])
    assert topic_two in str(persona["voiceStyle"])
    assert {"tone", "sentencePattern", "responseRules", "preferredTopics", "openers", "closers", "avoid", "emotionRange"} <= set(persona["voiceStyle"])
    assert set(persona["stageProfiles"]) == {
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
    }
    assert persona["knowledgeRules"]["canDiscuss"]
    assert persona["knowledgeRules"]["cannotAssume"]


def test_first_normal_sve_batch_has_distinct_voice_cards() -> None:
    store = PersonaStore(PERSONAS_DIR)
    personas = [store.get_persona(npc_id, ["SVE"]) for npc_id, *_ in NORMAL_SVE_BATCH_ONE]

    assert len({persona["voiceStyle"]["tone"] for persona in personas}) == 3


@pytest.mark.parametrize(
    ("npc_id", "subject", "object_", "possessive", "topic_one", "topic_two"),
    NORMAL_SVE_BATCH_TWO,
)
def test_second_normal_sve_batch_has_complete_gendered_voice_cards_without_overlay(
    npc_id: str,
    subject: str,
    object_: str,
    possessive: str,
    topic_one: str,
    topic_two: str,
) -> None:
    store = PersonaStore(PERSONAS_DIR)
    persona = store.get_persona(npc_id, ["SVE"])

    assert persona["npcId"] == npc_id
    assert persona["displayName"] == npc_id
    assert persona["pronouns"] == {
        "subject": subject,
        "object": object_,
        "possessive": possessive,
    }
    assert "genderPresentation" not in persona
    assert "female-bachelors" not in str(persona.get("modOverlay", {}))
    assert topic_one in str(persona["voiceStyle"])
    assert topic_two in str(persona["voiceStyle"])
    assert {"tone", "sentencePattern", "responseRules", "preferredTopics", "openers", "closers", "avoid", "emotionRange"} <= set(persona["voiceStyle"])
    assert set(persona["stageProfiles"]) == {
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
    }
    assert persona["knowledgeRules"]["canDiscuss"]
    assert persona["knowledgeRules"]["cannotAssume"]


def test_second_normal_sve_batch_has_distinct_voice_cards() -> None:
    store = PersonaStore(PERSONAS_DIR)
    personas = [store.get_persona(npc_id, ["SVE"]) for npc_id, *_ in NORMAL_SVE_BATCH_TWO]

    assert len({persona["voiceStyle"]["tone"] for persona in personas}) == 3


@pytest.mark.parametrize(
    ("npc_id", "topic_one", "topic_two"),
    NORMAL_VANILLA_BATCH_ONE,
)
def test_first_normal_vanilla_batch_has_complete_voice_cards_without_feminine_overlay(
    npc_id: str,
    topic_one: str,
    topic_two: str,
) -> None:
    store = PersonaStore(PERSONAS_DIR)
    persona = store.get_persona(npc_id, ["vanilla"])

    assert persona["npcId"] == npc_id
    assert persona["displayName"] == npc_id
    assert persona["pronouns"] == {
        "subject": "she",
        "object": "her",
        "possessive": "her",
    }
    assert "genderPresentation" not in persona
    assert "female-bachelors" not in str(persona.get("modOverlay", {}))
    assert topic_one in str(persona["voiceStyle"])
    assert topic_two in str(persona["voiceStyle"])
    assert {
        "tone",
        "sentencePattern",
        "responseRules",
        "preferredTopics",
        "openers",
        "closers",
        "avoid",
        "emotionRange",
    } <= set(persona["voiceStyle"])
    assert set(persona["stageProfiles"]) == {
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
    }
    assert persona["knowledgeRules"]["canDiscuss"]
    assert persona["knowledgeRules"]["cannotAssume"]


def test_first_normal_vanilla_batch_has_distinct_voice_cards() -> None:
    store = PersonaStore(PERSONAS_DIR)
    personas = [
        store.get_persona(npc_id, ["vanilla"])
        for npc_id, *_ in NORMAL_VANILLA_BATCH_ONE
    ]

    assert len({persona["voiceStyle"]["tone"] for persona in personas}) == 4


@pytest.mark.parametrize(
    ("npc_id", "topic_one", "topic_two"),
    NORMAL_VANILLA_BATCH_TWO,
)
def test_second_normal_vanilla_batch_has_complete_voice_cards_without_feminine_overlay(
    npc_id: str,
    topic_one: str,
    topic_two: str,
) -> None:
    store = PersonaStore(PERSONAS_DIR)
    persona = store.get_persona(npc_id, ["vanilla"])

    assert persona["npcId"] == npc_id
    assert persona["displayName"] == npc_id
    assert persona["pronouns"] == {
        "subject": "she",
        "object": "her",
        "possessive": "her",
    }
    assert "genderPresentation" not in persona
    assert "female-bachelors" not in str(persona.get("modOverlay", {}))
    assert topic_one in str(persona["voiceStyle"])
    assert topic_two in str(persona["voiceStyle"])
    assert {
        "tone",
        "sentencePattern",
        "responseRules",
        "preferredTopics",
        "openers",
        "closers",
        "avoid",
        "emotionRange",
    } <= set(persona["voiceStyle"])
    assert set(persona["stageProfiles"]) == {
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
    }
    assert persona["knowledgeRules"]["canDiscuss"]
    assert persona["knowledgeRules"]["cannotAssume"]


def test_second_normal_vanilla_batch_has_distinct_voice_cards() -> None:
    store = PersonaStore(PERSONAS_DIR)
    personas = [
        store.get_persona(npc_id, ["vanilla"])
        for npc_id, *_ in NORMAL_VANILLA_BATCH_TWO
    ]

    assert len({persona["voiceStyle"]["tone"] for persona in personas}) == 4


@pytest.mark.parametrize(
    ("npc_id", "topic_one", "topic_two", "subject", "object_", "possessive"),
    NORMAL_VANILLA_BATCH_THREE,
)
def test_third_normal_vanilla_batch_has_complete_voice_cards_without_feminine_overlay(
    npc_id: str,
    topic_one: str,
    topic_two: str,
    subject: str,
    object_: str,
    possessive: str,
) -> None:
    store = PersonaStore(PERSONAS_DIR)
    persona = store.get_persona(npc_id, ["vanilla"])

    assert persona["npcId"] == npc_id
    assert persona["displayName"] == npc_id
    assert persona["pronouns"] == {
        "subject": subject,
        "object": object_,
        "possessive": possessive,
    }
    assert "genderPresentation" not in persona
    assert "female-bachelors" not in str(persona.get("modOverlay", {}))
    assert topic_one in str(persona["voiceStyle"])
    assert topic_two in str(persona["voiceStyle"])
    assert {
        "tone",
        "sentencePattern",
        "responseRules",
        "preferredTopics",
        "openers",
        "closers",
        "avoid",
        "emotionRange",
    } <= set(persona["voiceStyle"])
    assert set(persona["stageProfiles"]) == {
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
    }
    assert persona["knowledgeRules"]["canDiscuss"]
    assert persona["knowledgeRules"]["cannotAssume"]


def test_third_normal_vanilla_batch_has_distinct_voice_cards() -> None:
    store = PersonaStore(PERSONAS_DIR)
    personas = [
        store.get_persona(npc_id, ["vanilla"])
        for npc_id, *_ in NORMAL_VANILLA_BATCH_THREE
    ]

    assert len({persona["voiceStyle"]["tone"] for persona in personas}) == 4


@pytest.mark.parametrize(
    ("npc_id", "topic_one", "topic_two", "subject", "object_", "possessive"),
    NORMAL_VANILLA_BATCH_FOUR,
)
def test_fourth_normal_vanilla_batch_has_complete_voice_cards_without_feminine_overlay(
    npc_id: str,
    topic_one: str,
    topic_two: str,
    subject: str,
    object_: str,
    possessive: str,
) -> None:
    store = PersonaStore(PERSONAS_DIR)
    persona = store.get_persona(npc_id, ["vanilla"])

    assert persona["npcId"] == npc_id
    assert persona["displayName"] == npc_id
    assert persona["pronouns"] == {
        "subject": subject,
        "object": object_,
        "possessive": possessive,
    }
    assert "genderPresentation" not in persona
    assert "female-bachelors" not in str(persona.get("modOverlay", {}))
    assert topic_one in str(persona["voiceStyle"])
    assert topic_two in str(persona["voiceStyle"])
    assert {
        "tone",
        "sentencePattern",
        "responseRules",
        "preferredTopics",
        "openers",
        "closers",
        "avoid",
        "emotionRange",
    } <= set(persona["voiceStyle"])
    assert set(persona["stageProfiles"]) == {
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
    }
    assert persona["knowledgeRules"]["canDiscuss"]
    assert persona["knowledgeRules"]["cannotAssume"]


def test_fourth_normal_vanilla_batch_has_distinct_voice_cards() -> None:
    store = PersonaStore(PERSONAS_DIR)
    personas = [
        store.get_persona(npc_id, ["vanilla"])
        for npc_id, *_ in NORMAL_VANILLA_BATCH_FOUR
    ]

    assert len({persona["voiceStyle"]["tone"] for persona in personas}) == 4


@pytest.mark.parametrize(
    ("npc_id", "topic_one", "topic_two", "subject", "object_", "possessive"),
    NORMAL_VANILLA_BATCH_FIVE,
)
def test_fifth_normal_vanilla_batch_has_complete_voice_cards_without_feminine_overlay(
    npc_id: str,
    topic_one: str,
    topic_two: str,
    subject: str,
    object_: str,
    possessive: str,
) -> None:
    store = PersonaStore(PERSONAS_DIR)
    persona = store.get_persona(npc_id, ["vanilla"])

    assert persona["npcId"] == npc_id
    assert persona["displayName"] == npc_id
    assert persona["pronouns"] == {
        "subject": subject,
        "object": object_,
        "possessive": possessive,
    }
    assert "genderPresentation" not in persona
    assert "female-bachelors" not in str(persona.get("modOverlay", {}))
    assert topic_one in str(persona["voiceStyle"])
    assert topic_two in str(persona["voiceStyle"])
    assert {
        "tone",
        "sentencePattern",
        "responseRules",
        "preferredTopics",
        "openers",
        "closers",
        "avoid",
        "emotionRange",
    } <= set(persona["voiceStyle"])
    assert set(persona["stageProfiles"]) == {
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
    }
    assert persona["knowledgeRules"]["canDiscuss"]
    assert persona["knowledgeRules"]["cannotAssume"]


def test_fifth_normal_vanilla_batch_has_distinct_voice_cards() -> None:
    store = PersonaStore(PERSONAS_DIR)
    personas = [
        store.get_persona(npc_id, ["vanilla"])
        for npc_id, *_ in NORMAL_VANILLA_BATCH_FIVE
    ]

    assert len({persona["voiceStyle"]["tone"] for persona in personas}) == 4


@pytest.mark.parametrize(
    ("npc_id", "topic_one", "topic_two", "subject", "object_", "possessive"),
    NORMAL_VANILLA_BATCH_SIX,
)
def test_sixth_normal_vanilla_batch_has_complete_voice_cards_without_feminine_overlay(
    npc_id: str,
    topic_one: str,
    topic_two: str,
    subject: str,
    object_: str,
    possessive: str,
) -> None:
    store = PersonaStore(PERSONAS_DIR)
    persona = store.get_persona(npc_id, ["vanilla"])

    assert persona["npcId"] == npc_id
    assert persona["displayName"] == npc_id
    assert persona["pronouns"] == {
        "subject": subject,
        "object": object_,
        "possessive": possessive,
    }
    assert "genderPresentation" not in persona
    assert "female-bachelors" not in str(persona.get("modOverlay", {}))
    assert topic_one in str(persona["voiceStyle"])
    assert topic_two in str(persona["voiceStyle"])
    assert {
        "tone",
        "sentencePattern",
        "responseRules",
        "preferredTopics",
        "openers",
        "closers",
        "avoid",
        "emotionRange",
    } <= set(persona["voiceStyle"])
    assert set(persona["stageProfiles"]) == {
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
    }
    assert persona["knowledgeRules"]["canDiscuss"]
    assert persona["knowledgeRules"]["cannotAssume"]


def test_sixth_normal_vanilla_batch_has_distinct_voice_cards() -> None:
    store = PersonaStore(PERSONAS_DIR)
    personas = [
        store.get_persona(npc_id, ["vanilla"])
        for npc_id, *_ in NORMAL_VANILLA_BATCH_SIX
    ]

    assert len({persona["voiceStyle"]["tone"] for persona in personas}) == 3


@pytest.mark.parametrize(
    ("npc_id", "subject", "object_", "possessive", "topic_one", "topic_two"),
    SPECIAL_VANILLA_BATCH,
)
def test_special_vanilla_batch_has_complete_normal_voice_cards(
    npc_id: str,
    subject: str,
    object_: str,
    possessive: str,
    topic_one: str,
    topic_two: str,
) -> None:
    persona = PersonaStore(PERSONAS_DIR).get_persona(npc_id, ["vanilla"])

    assert persona["npcId"] == npc_id
    assert persona["displayName"] == npc_id
    assert persona["pronouns"] == {
        "subject": subject,
        "object": object_,
        "possessive": possessive,
    }
    assert "genderPresentation" not in persona
    assert "female-bachelors" not in str(persona.get("modOverlay", {}))
    assert topic_one in str(persona["voiceStyle"])
    assert topic_two in str(persona["voiceStyle"])
    assert {
        "tone",
        "sentencePattern",
        "responseRules",
        "preferredTopics",
        "openers",
        "closers",
        "avoid",
        "emotionRange",
    } <= set(persona["voiceStyle"])
    assert set(persona["stageProfiles"]) == {
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
    }
    assert persona["knowledgeRules"]["canDiscuss"]
    assert persona["knowledgeRules"]["cannotAssume"]


def test_special_vanilla_batch_has_distinct_voice_cards() -> None:
    store = PersonaStore(PERSONAS_DIR)
    personas = [
        store.get_persona(npc_id, ["vanilla"])
        for npc_id, *_ in SPECIAL_VANILLA_BATCH
    ]

    # 4 → 3：删掉 Birdie 后这一批剩 Leo / Gunther / Marlon。
    assert len({persona["voiceStyle"]["tone"] for persona in personas}) == 3


@pytest.mark.parametrize(
    ("npc_id", "subject", "object_", "possessive"),
    [
        ("Caroline", "she", "her", "her"),
        ("Marnie", "she", "her", "her"),
        ("Linus", "he", "him", "his"),
    ],
)
def test_existing_normal_vanilla_roles_have_explicit_pronouns(
    npc_id: str,
    subject: str,
    object_: str,
    possessive: str,
) -> None:
    persona = PersonaStore(PERSONAS_DIR).get_persona(npc_id, ["vanilla"])

    assert persona["pronouns"] == {
        "subject": subject,
        "object": object_,
        "possessive": possessive,
    }
    assert "genderPresentation" not in persona


def test_persona_store_does_not_apply_female_bachelors_to_an_ineligible_npc(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    persona_dir.mkdir()
    (persona_dir / "vanilla.json").write_text(
        '{"mod":"vanilla","personas":{"Caroline":{"displayName":"Caroline",'
        '"pronouns":{"subject":"she","object":"her","possessive":"her"},'
        '"coreTraits":["warm"]}}}',
        encoding="utf-8",
    )
    (persona_dir / "female-bachelors.json").write_text(
        '{"mod":"female-bachelors","personas":{"Caroline":{"displayName":"错误名字",'
        '"pronouns":{"subject":"he","object":"him","possessive":"his"},'
        '"genderPresentation":{"layer":"expression_only"}}}}',
        encoding="utf-8",
    )

    persona = PersonaStore(persona_dir).get_persona(
        "Caroline", ["vanilla", "female-bachelors"]
    )

    assert persona["displayName"] == "Caroline"
    assert persona["pronouns"] == {
        "subject": "she",
        "object": "her",
        "possessive": "her",
    }
    assert "genderPresentation" not in persona


def test_new_female_bachelors_roles_have_complete_distinct_expression_layers() -> None:
    store = PersonaStore(PERSONAS_DIR)
    roles = ("Elliott", "Harvey", "Sam")
    required_stages = {
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
    }

    personas = [
        store.get_persona(npc_id, ["vanilla", "female-bachelors"])
        for npc_id in roles
    ]

    assert all(persona["npcId"] in roles for persona in personas)
    assert all(
        persona["pronouns"]
        == {"subject": "she", "object": "her", "possessive": "her"}
        for persona in personas
    )
    assert all(persona["genderPresentation"]["layer"] == "expression_only" for persona in personas)
    assert all(persona["genderPresentation"]["basePersonaPriority"] == "higher" for persona in personas)
    assert all(
        {"tone", "sentencePattern", "responseRules", "preferredTopics", "openers", "closers", "avoid", "emotionRange"}
        <= set(persona["voiceStyle"])
        for persona in personas
    )
    assert all(set(persona["stageProfiles"]) == required_stages for persona in personas)
    assert all(persona["knowledgeRules"]["cannotAssume"] for persona in personas)
    assert len({persona["voiceStyle"]["tone"] for persona in personas}) == len(roles)


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


def test_sophia_persona_exposes_stage_energy_and_excited_particles() -> None:
    voice = PersonaStore(PERSONAS_DIR).get_persona("Sophia", ["SVE"])[
        "voiceStyle"
    ]

    assert voice["speechParticleHints"][:3] == ["嘿", "哇", "哦哦哦"]
    assert voice["energyProfile"]["married"]
    assert "兴奋" in voice["energyProfile"]["married"]
    assert any("先反应" in item for item in voice["emotionTexture"])
