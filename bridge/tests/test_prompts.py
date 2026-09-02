from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from stardew_ai_bridge.personas import PersonaStore, merge_persona
    from stardew_ai_bridge.profile_index import ProfileIndexBuilder, ProfileIndexStore
    from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder
except ModuleNotFoundError:
    class _MissingImplementation:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def __getattr__(self, name: str) -> object:
            del name
            pytest.fail("Task 4 人物与提示词模块尚未实现")

    PersonaStore = _MissingImplementation  # type: ignore[misc,assignment]
    ProfileIndexBuilder = _MissingImplementation  # type: ignore[misc,assignment]
    ProfileIndexStore = _MissingImplementation  # type: ignore[misc,assignment]
    ContextBuilder = _MissingImplementation  # type: ignore[misc,assignment]
    PromptBuilder = _MissingImplementation  # type: ignore[misc,assignment]

    def merge_persona(*args: object, **kwargs: object) -> object:
        del args, kwargs
        pytest.fail("Task 4 人物合并模块尚未实现")


PERSONAS_DIR = Path(__file__).parents[2] / "data" / "personas"


def test_persona_store_loads_required_json_datasets() -> None:
    store = PersonaStore(PERSONAS_DIR)

    assert store.get_persona("Wizard")["displayName"] == "Wizard"
    assert {"vanilla.json", "sve.json", "female-bachelors.json", "rasmodia.json"} <= {
        path.name for path in PERSONAS_DIR.glob("*.json")
    }


def test_sve_overlay_requires_sve_source_mod() -> None:
    store = PersonaStore(PERSONAS_DIR)

    vanilla = store.get_persona("Wizard", source_mods=[])
    sve = store.get_persona("Wizard", source_mods=["SVE"])

    assert vanilla["displayName"] == "Wizard"
    assert vanilla["modOverlay"] == {}
    assert sve["displayName"] != vanilla["displayName"]
    assert "SVE" in sve["modOverlay"]


def test_rasmodia_overlay_changes_display_name_pronouns_and_addressing() -> None:
    store = PersonaStore(PERSONAS_DIR)

    rasmodia = store.get_persona(
        "Wizard", source_mods=["Romanceable Rasmodius"]
    )

    assert rasmodia["displayName"] == "Rasmodia"
    assert rasmodia["pronouns"]["subject"] == "she"
    assert rasmodia["addressing"]["player"] == "你"


def test_rasmodia_alias_uses_wizard_without_unenabled_romance_overlay() -> None:
    store = PersonaStore(PERSONAS_DIR)

    vanilla_alias = store.get_persona("Rasmodia")
    romance_alias = store.get_persona(
        "Rasmodia", source_mods=["Romanceable Rasmodius"]
    )

    assert vanilla_alias["npcId"] == "Wizard"
    assert vanilla_alias["displayName"] == "Wizard"
    assert vanilla_alias["pronouns"]["subject"] == "he"
    assert romance_alias["npcId"] == "Wizard"
    assert romance_alias["displayName"] == "Rasmodia"
    assert romance_alias["pronouns"]["subject"] == "she"


def test_persona_overlays_accept_human_readable_mod_names() -> None:
    store = PersonaStore(PERSONAS_DIR)

    sophia = store.get_persona("Sophia", source_mods=["Stardew Valley Expanded"])
    rasmodia = store.get_persona("Wizard", source_mods=["Romanceable Rasmodia"])

    assert sophia["modOverlay"]
    assert "SVE" in sophia["modOverlay"]
    assert rasmodia["displayName"] == "Rasmodia"
    assert rasmodia["modOverlay"]


def test_female_bachelors_overlay_supports_female_shane() -> None:
    store = PersonaStore(PERSONAS_DIR)

    shane = store.get_persona("Shane", source_mods=["female-bachelors"])

    assert shane["pronouns"]["subject"] == "she"
    assert shane["addressing"]["player"]


def test_unprofiled_npc_receives_safe_default_profile_layers() -> None:
    store = PersonaStore(PERSONAS_DIR)

    alex = store.get_persona("Alex", source_mods=["female-bachelors"])

    assert isinstance(alex["voiceStyle"], dict)
    assert set(alex["stageProfiles"]) == {
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
    }
    assert alex["knowledgeRules"]["cannotAssume"]


def test_representative_profiles_include_voice_stage_and_knowledge_layers() -> None:
    store = PersonaStore(PERSONAS_DIR)

    representatives = (
        ("Sophia", ["SVE"]),
        ("Shane", ["female-bachelors"]),
        ("Wizard", ["Romanceable Rasmodius"]),
    )
    for npc_id, source_mods in representatives:
        persona = store.get_persona(npc_id, source_mods=source_mods)
        assert isinstance(persona.get("voiceStyle"), dict)
        assert isinstance(persona.get("stageProfiles"), dict)
        assert isinstance(persona.get("knowledgeRules"), dict)
        assert {"stranger", "friend", "close", "married"} <= set(
            persona["stageProfiles"]
        )


def test_evaluation_characters_have_distinct_complete_voice_cards() -> None:
    store = PersonaStore(PERSONAS_DIR)
    evaluation_personas = {
        "Wizard/Rasmodia": store.get_persona(
            "Wizard", source_mods=["Romanceable Rasmodius"]
        ),
        "Sophia": store.get_persona("Sophia", source_mods=["SVE"]),
        "Shane": store.get_persona(
            "Shane", source_mods=["female-bachelors"]
        ),
        "Sebastian": store.get_persona(
            "Sebastian", source_mods=["female-bachelors"]
        ),
        "Alex": store.get_persona("Alex"),
    }
    required_fields = {
        "tone",
        "sentencePattern",
        "responseRules",
        "preferredTopics",
        "openers",
        "closers",
        "avoid",
        "emotionRange",
    }

    for persona in evaluation_personas.values():
        assert required_fields <= set(persona["voiceStyle"])
    assert len(
        {persona["voiceStyle"]["tone"] for persona in evaluation_personas.values()}
    ) == len(evaluation_personas)


def test_friendship_only_npcs_have_distinct_voice_and_stage_layers() -> None:
    store = PersonaStore(PERSONAS_DIR)
    evaluation_personas = {
        npc_id: store.get_persona(npc_id)
        for npc_id in ("Caroline", "Marnie", "Linus")
    }
    required_fields = {
        "tone",
        "sentencePattern",
        "responseRules",
        "preferredTopics",
        "openers",
        "closers",
        "avoid",
        "emotionRange",
    }

    for persona in evaluation_personas.values():
        assert required_fields <= set(persona["voiceStyle"])
        assert {"stranger", "acquaintance", "friend", "close"} <= set(
            persona["stageProfiles"]
        )
        assert persona["knowledgeRules"]["canDiscuss"]

    assert "茶园" in json.dumps(evaluation_personas["Caroline"], ensure_ascii=False)
    assert "动物" in json.dumps(evaluation_personas["Marnie"], ensure_ascii=False)
    assert "野外" in json.dumps(evaluation_personas["Linus"], ensure_ascii=False)
    assert len(
        {persona["voiceStyle"]["tone"] for persona in evaluation_personas.values()}
    ) == len(evaluation_personas)


def test_prompt_tells_every_stage_to_respect_an_explicit_conversation_exit() -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        "Shane",
        source_mods=["female-bachelors"],
        friendshipHearts=8,
        history=[
            {"role": "user", "content": "你最近是不是又睡不好？"},
            {"role": "assistant", "content": "昨晚没怎么睡。"},
        ],
    )

    messages = PromptBuilder().build(
        context,
        "好，那我不问了，你想说的时候再说。",
    )
    stage_card = next(
        message for message in messages if message["name"] == "stage_execution_card"
    )

    assert "玩家明确表示先不问、先休息、有空再聊或先走时" in stage_card["content"]
    assert "不得主动抛出新问题、新对象或新话题" in stage_card["content"]


def test_final_voice_card_reasserts_plain_dialogue_after_style_guidance() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "voiceStyle": {
                "tone": "直白、疲惫",
                "sentencePattern": ["句子偏短"],
                "responseRules": ["直接回答"],
                "avoid": ["动作旁白"],
            },
            "stagePolicy": {
                "stage": "friend",
                "responseShape": "通常两句",
                "selfDisclosure": "只说愿意说的部分",
                "initiative": "只接当前话题",
                "followUp": "围绕当前话题",
                "boundaryMode": "保留边界",
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "最近还好吗？")
    voice_card = next(
        message for message in messages if message["name"] == "voice_execution_card"
    )

    assert "即使原版示例或历史中出现动作，也不要输出动作旁白" in voice_card[
        "content"
    ]


def test_sebastian_has_a_vanilla_persona_without_female_bachelors_overlay() -> None:
    persona = PersonaStore(PERSONAS_DIR).get_persona("Sebastian", ["vanilla"])

    assert persona["coreTraits"]
    voice_style = persona["voiceStyle"]
    assert "编程" in json.dumps(voice_style, ensure_ascii=False)
    assert "摩托车" in json.dumps(voice_style, ensure_ascii=False)
    assert "低声" in voice_style["tone"]
    assert "演讲腔" in voice_style["avoid"]
    assert "stranger" in persona["stageProfiles"]


def test_alex_has_signature_topics_and_non_coach_boundaries() -> None:
    persona = PersonaStore(PERSONAS_DIR).get_persona("Alex")

    stage_text = json.dumps(persona["stageProfiles"], ensure_ascii=False)
    voice_text = json.dumps(persona["voiceStyle"], ensure_ascii=False)
    knowledge_text = json.dumps(persona["knowledgeRules"], ensure_ascii=False)

    for marker in ("全明星四分卫", "夹克上的小星星", "海滩", "投球", "职业选手"):
        assert marker in stage_text or marker in voice_text or marker in knowledge_text
    assert "微不足道的小事" in stage_text or "微不足道的小事" in knowledge_text
    assert "教练" in voice_text
    assert "没提运动时" in voice_text or "不把普通问题" in voice_text


def test_alex_stranger_daily_context_selects_a_character_specific_behavior_example(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    index = ProfileIndexBuilder(PERSONAS_DIR).build()
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    context = ContextBuilder(
        PersonaStore(PERSONAS_DIR), ProfileIndexStore(index_path)
    ).build(
        "Alex",
        source_mods=["vanilla"],
        friendshipHearts=0,
        message="最近怎么样？",
    )

    examples = context.get("behaviorExamples", [])
    assert examples
    assert any(
        ("投" in str(example.get("npcReply", "")) and "球" in str(example.get("npcReply", "")))
        or "全明星四分卫" in str(example.get("npcReply", ""))
        for example in examples
    )

    messages = PromptBuilder().build(context, "最近怎么样？")
    rendered = json.dumps(messages, ensure_ascii=False)
    assert "泛化教练" not in rendered
    assert "没提运动时不要硬转成训练建议" in rendered or "不把普通问题改成训练建议" in rendered


@pytest.mark.parametrize(
    ("npc_id", "source_mods", "voice_marker"),
    (
        (
            "Rasmodia",
            ["Romanceable Rasmodius"],
            "未提及魔法、星界、预兆时不主动引入",
        ),
        ("Sophia", ["SVE"], "葡萄园"),
        ("Shane", ["female-bachelors"], "干巴巴的玩笑"),
        ("Sebastian", ["female-bachelors"], "冷幽默"),
        ("Alex", [], "行动派"),
    ),
)
def test_prompt_contains_the_current_characters_voice_constraints(
    npc_id: str,
    source_mods: list[str],
    voice_marker: str,
) -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        npc_id,
        source_mods=source_mods,
        friendshipHearts=6,
    )

    messages = PromptBuilder().build(context, "最近怎么样？")
    persona_message = next(
        message for message in messages if message["name"] == "persona_core"
    )
    safety_message = next(
        message for message in messages if message["name"] == "safety_rules"
    )

    assert voice_marker in persona_message["content"]
    assert "必须遵守当前角色的 voiceStyle" in safety_message["content"]
    assert "还算顺利" not in json.dumps(messages, ensure_ascii=False)
    assert "谢谢你的关心" not in json.dumps(messages, ensure_ascii=False)


def test_prompt_keeps_signature_topics_and_concrete_behavior_reference() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "voiceStyle": {
                "tone": "像在街边聊天，偶尔爱炫耀",
                "preferredTopics": ["全明星四分卫和夹克上的小星星", "海滩和投球"],
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "alex:daily:acquaintance",
                "channels": ["face_to_face"],
                "relationshipStages": ["acquaintance"],
                "speechFunction": "answer_with_confident_detail",
                "topic": "daily_status",
                "emotion": "confident_energy",
                "playerInput": "你高中时真的打过全明星四分卫吗？",
                "npcReply": "当然是真的。你没看到我夹克上的小星星吗？",
            }
        ],
    }

    messages = PromptBuilder().build(context, "你高中时真的打过全明星四分卫吗？")
    persona = next(message for message in messages if message["name"] == "persona_core")
    behavior = next(
        message for message in messages if message["name"] == "behavior_examples"
    )
    behavior_payload = json.loads(behavior["content"])
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "全明星四分卫和夹克上的小星星" in persona["content"]
    assert behavior_payload["examples"][0]["conditions"]["topic"] == "daily_status"
    assert "playerInput" not in behavior_payload["examples"][0]
    assert "npcReply" not in behavior_payload["examples"][0]
    assert "不是原文台词" in behavior_payload["instruction"]
    assert "behavior_example_user" in rendered
    assert "behavior_example_assistant" in rendered


def test_prompt_retains_a_wider_diverse_original_evidence_window() -> None:
    context = {
        "npcIdentity": {"npcId": "Alex", "displayName": "Alex"},
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "speechEvidence": [
            {"sourceMod": "vanilla", "sourceKey": f"Mon{index}", "text": f"原文证据 {index}"}
            for index in range(6)
        ],
        "styleSamples": [
            {"sourceMod": "vanilla", "sourceKey": f"Tue{index}", "text": f"语气样本 {index}"}
            for index in range(6)
        ],
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    speech = json.loads(
        next(message for message in messages if message["name"] == "speech_evidence")[
            "content"
        ]
    )["speechEvidence"]
    style = json.loads(
        next(message for message in messages if message["name"] == "style_evidence")[
            "content"
        ]
    )["styleSamples"]

    assert len(speech) >= 4
    assert len(style) >= 3


def test_prompt_discourages_mechanical_voice_templates_and_bookish_summaries() -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        "Sebastian",
        source_mods=["female-bachelors"],
        friendshipHearts=6,
    )

    messages = PromptBuilder().build(context, "你今天看起来有点累。")
    safety_message = next(
        message for message in messages if message["name"] == "safety_rules"
    )

    assert "通常 15–80 字" in safety_message["content"]
    assert "不要机械拼接 voiceStyle 中的开场、收尾或口头语" in safety_message[
        "content"
    ]
    assert "语气参考，不是固定台词" in safety_message["content"]
    assert "不要用书面化的总结句" in safety_message["content"]
    assert "不要在同一句中无必要重复同一名词" in safety_message["content"]


def test_plain_dialogue_does_not_promote_location_or_evidence_to_a_topic() -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        "Wizard",
        source_mods=["Romanceable Rasmodius"],
        location="法师塔",
        friendshipHearts=6,
    )

    messages = PromptBuilder().build(context, "最近怎么样？")
    safety_message = next(
        message for message in messages if message["name"] == "safety_rules"
    )

    assert "地点、季节和语料中的主题仅作事实背景" in safety_message["content"]
    assert "不是玩家问题" in safety_message["content"]


def test_plain_dialogue_removes_magic_topic_hints_from_persona_prompt() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "voiceStyle": {
                "tone": "克制、古雅",
                "sentencePattern": ["先给结论", "谈魔法时使用准确术语"],
                "responseRules": ["先直接回应", "未提及魔法时不主动引入"],
                "preferredTopics": ["魔法研究", "星界与自然征兆", "塔内日常"],
                "avoid": ["把未知的魔法当作事实", "连续堆叠华丽比喻"],
            },
        },
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
    }

    messages = PromptBuilder().build(context, "最近过得怎么样？")
    persona = next(message for message in messages if message["name"] == "persona_core")

    assert "魔法研究" not in persona["content"]
    assert "星界与自然征兆" not in persona["content"]
    assert "塔内日常" in persona["content"]


def test_prompt_treats_current_scene_facts_as_hard_without_forcing_them_into_reply() -> None:
    context = {
        "npcIdentity": {"npcId": "Sebastian", "displayName": "Sebastian"},
        "modSources": ["vanilla"],
        "gameState": {
            "weather": "下雨",
            "time": 2200,
            "location": "卧室",
        },
        "recentFacts": [],
        "history": [],
    }

    messages = PromptBuilder().build(context, "你喜欢下雨天吗？")
    safety_message = next(
        message for message in messages if message["name"] == "safety_rules"
    )

    assert "天气、时间和地点是当前场景的硬事实" in safety_message["content"]
    assert "不要为了显得贴合而硬塞" in safety_message["content"]


def test_rasmodia_voice_style_captures_source_rhythm_and_register() -> None:
    store = PersonaStore(PERSONAS_DIR)

    voice_style = store.get_persona(
        "Wizard", source_mods=["Romanceable Rasmodius"]
    )["voiceStyle"]

    sentence_patterns = "；".join(voice_style["sentencePattern"])
    avoid = "；".join(voice_style["avoid"])
    response_rules = "；".join(voice_style["responseRules"])
    assert "1–3 句" in sentence_patterns
    assert "短句" in sentence_patterns
    assert "称呼优先使用‘你’或玩家名字" in sentence_patterns
    assert "华丽比喻" in avoid
    assert "网络口吻" in avoid
    assert "反复使用‘旅行者’" in avoid
    assert "不写环境开场" in response_rules
    assert "未提及魔法、星界、预兆时不主动引入" in response_rules


def test_context_selects_one_stage_profile_without_dumping_all_stages() -> None:
    builder = ContextBuilder(PersonaStore(PERSONAS_DIR))

    context = builder.build(
        "Shane",
        source_mods=["female-bachelors"],
        friendshipHearts=8,
    )

    identity = context["npcIdentity"]
    assert identity["stageProfile"]["stage"] == "close"
    assert "stageProfiles" not in identity
    assert "voiceStyle" in identity
    assert "knowledgeRules" in identity


def test_context_projects_executable_stage_policy_for_all_evaluation_characters() -> None:
    builder = ContextBuilder(PersonaStore(PERSONAS_DIR))

    for npc_id, source_mods, hearts in (
        ("Wizard", ["Romanceable Rasmodius"], 0),
        ("Sophia", ["SVE"], 6),
        ("Shane", ["female-bachelors"], 0),
        ("Sebastian", ["female-bachelors"], 6),
        ("Alex", ["female-bachelors"], 8),
    ):
        context = builder.build(
            npc_id,
            source_mods=source_mods,
            friendshipHearts=hearts,
        )
        policy = context["npcIdentity"]["stagePolicy"]

        assert policy["stage"] in {"stranger", "friend", "close"}
        assert {
            "responseShape",
            "selfDisclosure",
            "initiative",
            "followUp",
            "boundaryMode",
        } <= set(policy)


def test_prompt_adds_stage_execution_card_after_history() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "stageProfile": {"stage": "stranger"},
            "stagePolicy": {
                "stage": "stranger",
                "responseShape": "一两句，先直接回答",
                "selfDisclosure": "只说眼前的表层近况",
                "initiative": "不主动开启新话题",
                "followUp": "不反问延长对话",
                "boundaryMode": "被追问私人话题时结束",
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [{"role": "user", "content": "你还好吗？"}],
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    names = [message["name"] for message in messages]
    card = next(
        message for message in messages if message["name"] == "stage_execution_card"
    )
    payload = json.loads(card["content"])

    assert names.index("conversation_history") < names.index("stage_execution_card")
    assert names.index("stage_execution_card") < names.index("player_input")
    assert payload["stage"] == "stranger"
    assert payload["initiative"] == "不主动开启新话题"
    assert "responseShape" in payload
    assert "初识阶段不得反问、邀约或主动换题" in payload["instruction"]


def test_prompt_builder_renders_selected_profile_layers() -> None:
    builder = ContextBuilder(PersonaStore(PERSONAS_DIR))
    context = builder.build(
        "Shane",
        source_mods=["female-bachelors"],
        friendshipHearts=8,
    )

    messages = PromptBuilder().build(context, "最近怎么样？")
    persona_message = next(
        message for message in messages if message["name"] == "persona_core"
    )
    payload = json.loads(persona_message["content"])
    identity = payload["npcIdentity"]

    assert identity["voiceStyle"]["tone"]
    assert identity["stageProfile"]["stage"] == "close"
    assert identity["knowledgeRules"]["cannotAssume"]


def test_prompt_places_base_persona_before_gender_and_story_layers() -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        "Shane",
        source_mods=["female-bachelors"],
        friendshipHearts=10,
        marriageStatus="married",
        completedEventIds=["vanilla:shane-heart-6"],
    )

    messages = PromptBuilder().build(context, "今天还好吗？")
    names = [item.get("name") for item in messages]

    assert names.index("persona_core") < names.index("gender_presentation")
    assert names.index("gender_presentation") < names.index("story_state")


def test_prompt_builder_renders_voice_card_as_separate_safe_message() -> None:
    context = {
        "npcIdentity": {"npcId": "Rasmodia", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "voiceCard": {
            "npcId": "Rasmodia",
            "features": {"magicMarkers": 3},
            "topicHints": ["魔法与星界"],
            "evidenceRefs": ["vanilla:Wizard:Rain"],
        },
    }

    messages = PromptBuilder().build(context, "你知道那件事吗？")
    names = [message["name"] for message in messages]
    voice_message = next(
        message for message in messages if message["name"] == "voice_card"
    )

    assert names.index("voice_card") < names.index("conversation_history")
    assert json.loads(voice_message["content"])["voiceCard"]["features"][
        "magicMarkers"
    ] == 3
    assert "text" not in voice_message["content"]


def test_prompt_teaches_voice_imitation_and_in_game_brevity() -> None:
    context = {
        "npcIdentity": {"npcId": "Rasmodia", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "speechEvidence": [
            {
                "npcId": "Rasmodia",
                "sourceMod": "Parrot.RomRas",
                "text": "啊，旅行者。#$b#今天的星象很安静。",
            }
        ],
        "styleSamples": [
            {
                "npcId": "Rasmodia",
                "sourceMod": "Parrot.RomRas",
                "text": "唔……我想我应该能与你作伴。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    safety = next(message for message in messages if message["name"] == "safety_rules")
    speech = next(message for message in messages if message["name"] == "speech_evidence")
    style = next(message for message in messages if message["name"] == "style_evidence")

    assert "模仿" in safety["content"]
    assert "1–3 句" in safety["content"]
    assert "不要用环境描写开头" in safety["content"]
    assert "不要主动引入玩家未提到的魔法设定" in safety["content"]
    assert "只用于模仿" in speech["content"]
    assert "不要照抄" in style["content"]


def test_prompt_projects_original_dialogue_as_high_signal_voice_few_shots() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "voiceStyle": {"tone": "直白、疲惫，偶尔用干巴巴的玩笑"},
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [],
        "speechEvidence": [
            {
                "sampleId": "shane:mon",
                "sourceKey": "Mon",
                "text": "如果没有重要的事，请不要打搅我。我还有好多活要干呢。",
            },
            {
                "sampleId": "shane:tue",
                "sourceKey": "Tue",
                "text": "我今天没心情聊天。你要是没别的事，就先走吧。",
            },
        ],
    }

    messages = PromptBuilder().build(context, "今天天气怎么样？")
    names = [message["name"] for message in messages]
    style_instruction = next(
        message
        for message in messages
        if message["name"] == "original_style_examples"
    )
    example_users = [
        message
        for message in messages
        if message["name"] == "original_style_example_user"
    ]
    example_assistants = [
        message
        for message in messages
        if message["name"] == "original_style_example_assistant"
    ]

    assert "原版对白语气示例" in style_instruction["content"]
    assert not example_users
    assert len(example_assistants) == 2
    assert all(message["role"] == "assistant" for message in example_assistants)
    assert example_assistants[0]["content"].startswith("如果没有重要的事")
    assert example_assistants[1]["content"].startswith("我今天没心情")
    assert names.index("original_style_examples") < names.index("player_input")
    assert names.index("original_style_example_assistant") < names.index(
        "player_input"
    )


def test_prompt_deduplicates_speech_and_style_evidence() -> None:
    context = {
        "npcIdentity": {"npcId": "Shane", "displayName": "Shane"},
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "speechEvidence": [
            {
                "sourceMod": "vanilla",
                "sourceKey": "Mon",
                "text": "嗯……今天还行。",
            },
            {
                "sourceMod": "vanilla",
                "sourceKey": "Tue",
                "text": "没什么特别的。",
            },
        ],
        "styleSamples": [
            {
                "sourceMod": "vanilla",
                "sourceKey": "Mon",
                "text": "嗯……今天还行。",
            },
            {
                "sourceMod": "vanilla",
                "sourceKey": "Wed",
                "text": "别把小事想得太复杂。",
            },
        ],
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    speech = next(message for message in messages if message["name"] == "speech_evidence")
    style = next(message for message in messages if message["name"] == "style_evidence")
    speech_texts = {
        item["text"]
        for item in json.loads(speech["content"])["speechEvidence"]
    }
    style_texts = {
        item["text"]
        for item in json.loads(style["content"])["styleSamples"]
    }

    assert speech_texts.isdisjoint(style_texts)
    assert "嗯……今天还行。" in speech_texts
    assert "别把小事想得太复杂。" in style_texts


def test_prompt_renders_behavior_examples_and_reinforces_voice_after_history() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "voiceStyle": {
                "tone": "直白、疲惫，偶尔用干巴巴的玩笑挡一下脆弱",
                "responseRules": ["先给短答", "用具体行动表达关心"],
            },
            "stageProfile": {"stage": "friend"},
        },
        "modSources": ["female-bachelors"],
        "gameState": {},
        "recentFacts": [],
        "history": [
            {"role": "user", "content": "你说过今天要去鸡舍。"},
            {"role": "assistant", "content": "嗯，记得。"},
        ],
        "behaviorExamples": [
            {
                "exampleId": "shane:work:friend",
                "channel": "face_to_face",
                "relationshipStages": ["friend"],
                "speechFunction": "answer_directly",
                "topic": "work_pressure",
                "emotion": "tired_dry_humor",
                "playerInput": "鸡舍今天忙吗？",
                "npcReply": "还行。没着火，就算顺利。",
                "sourceType": "human_approved",
            }
        ],
        "interaction": {"intent": "chat", "channel": "face_to_face"},
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    names = [message["name"] for message in messages]
    examples = next(
        message for message in messages if message["name"] == "behavior_examples"
    )
    post_history = next(
        message
        for message in messages
        if message["name"] == "post_history_voice_guard"
    )

    assert names.index("behavior_examples") < names.index("conversation_history")
    assert "不是原文台词" in examples["content"]
    assert "speechEvidence" in examples["content"]
    assert "behavior_example_user" in names
    assert "behavior_example_assistant" in names
    assert "行为参考卡" in examples["content"]
    assert "npcReply" not in examples["content"]
    assert names.index("conversation_history") < names.index("post_history_voice_guard")
    assert names.index("behavior_examples") < names.index("player_input")
    assert "face_to_face" in post_history["content"]
    assert "本轮只处理当前话题" in post_history["content"]


def test_prompt_uses_reviewed_behavior_as_a_condition_card_before_history() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "voiceStyle": {"tone": "直白、疲惫，偶尔用干巴巴的玩笑挡一下脆弱"},
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [
            {"role": "user", "content": "你说今天要去鸡舍。"},
            {"role": "assistant", "content": "嗯，记得。"},
        ],
        "behaviorExamples": [
            {
                "exampleId": "shane:work:friend",
                "relationshipStages": ["friend"],
                "speechFunction": "answer_directly",
                "topic": "chicken_coop",
                "topicKeywords": ["鸡舍"],
                "playerInput": "鸡舍今天忙吗？",
                "npcReply": "还行。没着火，就算顺利。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    names = [message.get("name") for message in messages]
    behavior_index = names.index("behavior_examples")
    history_index = names.index("conversation_history")
    behavior_payload = json.loads(messages[behavior_index]["content"])
    example = behavior_payload["examples"][0]

    assert behavior_index < history_index
    assert example["conditions"]["topic"] == "chicken_coop"
    assert example["conditions"]["topicKeywords"] == ["鸡舍"]
    assert "playerInput" not in example
    assert "npcReply" not in example
    player_input_index = names.index("player_input")
    assert behavior_index < player_input_index
    assert messages[player_input_index]["content"] == "鸡舍今天忙吗？"


def test_prompt_limits_behavior_cards_and_deduplicates_topics() -> None:
    context = {
        "npcIdentity": {"npcId": "Shane", "displayName": "Shane"},
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "shane:coop:one",
                "topic": "chicken_coop",
                "topicKeywords": ["鸡舍"],
                "playerInput": "鸡舍今天忙吗？",
                "npcReply": "还行。没着火，就算顺利。",
                "review": {"naturalChinese": 2, "hardErrors": []},
            },
            {
                "exampleId": "shane:coop:two",
                "topic": "chicken_coop",
                "topicKeywords": ["鸡舍"],
                "playerInput": "鸡舍最近还好吗？",
                "npcReply": "还行。没着火，暂时算顺利。",
            },
            {
                "exampleId": "shane:coffee",
                "topic": "morning_routine",
                "topicKeywords": ["咖啡"],
                "playerInput": "早上喝咖啡了吗？",
                "npcReply": "喝了。否则我现在不会说人话。",
            },
        ],
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    behavior_payload = json.loads(
        next(message for message in messages if message["name"] == "behavior_examples")[
            "content"
        ]
    )
    examples = behavior_payload["examples"]
    rendered = json.dumps(messages, ensure_ascii=False)

    assert behavior_payload["count"] == 2
    assert [example["conditions"]["topic"] for example in examples] == [
        "chicken_coop",
        "morning_routine",
    ]
    assert all("playerInput" not in example for example in examples)
    assert all("npcReply" not in example for example in examples)
    assert "还行。没着火，暂时算顺利。" not in rendered
    assert "喝了。否则我现在不会说人话。" in rendered
    assert "naturalChinese" not in rendered
    assert "hardErrors" not in rendered
    assert "review" not in rendered


def test_behavior_examples_do_not_become_fake_conversation_turns() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "voiceStyle": {"tone": "直白、疲惫"},
        },
        "modSources": ["female-bachelors"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "shane:work:friend",
                "relationshipStages": ["friend"],
                "speechFunction": "answer_directly",
                "topic": "work_pressure",
                "topicKeywords": ["鸡舍"],
                "emotion": "tired_dry_humor",
                "playerInput": "鸡舍今天忙吗？",
                "npcReply": "还行。没着火，就算顺利。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    names = [message["name"] for message in messages]
    behavior = next(
        message for message in messages if message["name"] == "behavior_examples"
    )
    behavior_content = behavior["content"]

    assert "behavior_example_user" in names
    assert "behavior_example_assistant" in names
    assert "不是原文台词" in behavior_content
    assert "行为参考卡" in behavior_content
    assert "npcReply" not in behavior_content


def test_prompt_adds_current_topic_anchor_after_history() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "friend"},
        },
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [
            {"role": "user", "content": "你先看看第三组。"},
            {"role": "assistant", "content": "我先核对记录。"},
        ],
        "behaviorExamples": [
            {
                "exampleId": "wizard:research-result",
                "npcId": "Wizard",
                "speechFunction": "give_specific_detail",
                "topic": "research_result",
                "playerInput": "这批符文有结果吗？",
                "npcReply": "有一点。第三组的读数稳定，第二组还得重测。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "那第三组现在稳定了吗？")
    names = [message["name"] for message in messages]
    anchor = next(
        message for message in messages if message["name"] == "current_topic_anchor"
    )
    payload = json.loads(anchor["content"])

    assert payload["topic"] == "research_result"
    assert payload["speechFunction"] == "give_specific_detail"
    assert payload["playerInput"] == "那第三组现在稳定了吗？"
    assert "先直接回答这个具体话题" in payload["instruction"]
    assert "保留玩家输入中的具体对象或动作" in payload["instruction"]
    assert "不要给 requiredTerms 加引号" in payload["instruction"]
    assert names.index("post_history_voice_guard") < names.index(
        "current_topic_anchor"
    ) < names.index("player_input")


def test_prompt_treats_history_as_continuity_without_mechanical_topic_repetition() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "friend"},
        },
        "modSources": ["SVE"],
        "gameState": {},
        "recentFacts": [],
        "history": [
            {"role": "user", "content": "葡萄园今天忙吗？"},
            {"role": "assistant", "content": "东边的藤架有点松。"},
        ],
    }

    messages = PromptBuilder().build(context, "你今天还好吗？")
    guard = next(
        message
        for message in messages
        if message["name"] == "post_history_voice_guard"
    )

    assert "历史只承接已经发生的事实和本轮话题" in guard["content"]
    assert "不要为了显得连贯重复上一条 NPC 的同一细节" in guard["content"]
    assert "当前输入没有继续追问时" in guard["content"]


def test_plain_current_topic_anchor_repeats_mundane_boundary_near_user_input() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "acquaintance"},
        },
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "wizard:daily",
                "topic": "daily_status",
                "topicKeywords": ["最近", "怎么样"],
                "playerInput": "最近过得怎么样？",
                "npcReply": "比昨天好些。今天的记录没有再次失控。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "最近过得怎么样？")
    anchor = next(
        message for message in messages if message["name"] == "current_topic_anchor"
    )

    assert "日常问题" in anchor["content"]
    assert "不要主动出现魔法、星界、符文或预言" in anchor["content"]


def test_history_current_topic_anchor_requires_the_continued_object() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "friend"},
        },
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [
            {"role": "user", "content": "你先看看第三组。"},
            {"role": "assistant", "content": "我先核对记录。"},
        ],
        "behaviorExamples": [
            {
                "exampleId": "wizard:research",
                "topic": "research_result",
                "topicKeywords": ["第三组", "稳定"],
                "playerInput": "那第三组现在稳定了吗？",
                "npcReply": "第三组稳定，第二组还得重测。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "那第三组现在稳定了吗？")
    anchor = next(
        message for message in messages if message["name"] == "current_topic_anchor"
    )

    assert "承接历史中的具体对象" in anchor["content"]
    assert "不得只回答状态" in anchor["content"]


def test_current_topic_anchor_lists_terms_that_must_be_carried_forward() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "friend"},
        },
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "wizard:research-result",
                "npcId": "Wizard",
                "topic": "research_result",
                "topicKeywords": ["符文", "第三组", "稳定", "读数"],
                "playerInput": "这批符文有结果吗？",
                "npcReply": "有一点。第三组的读数稳定，第二组还得重测。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "那第三组现在稳定了吗？")
    anchor = next(
        message for message in messages if message["name"] == "current_topic_anchor"
    )
    payload = json.loads(anchor["content"])

    assert payload["requiredTerms"] == ["第三组", "稳定"]
    assert "必须原样使用 requiredTerms 中至少一个" in payload["instruction"]


def test_prompt_adds_final_reply_contract_with_topic_and_history_anchors() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "friend"},
        },
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [
            {"role": "user", "content": "你先看看第三组。"},
            {"role": "assistant", "content": "我先核对记录。"},
        ],
        "behaviorExamples": [
            {
                "topic": "research_result",
                "topicKeywords": ["第三组", "稳定"],
                "playerInput": "那第三组现在稳定了吗？",
                "npcReply": "第三组稳定，第二组还得重测。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "那第三组现在稳定了吗？")
    names = [message["name"] for message in messages]
    contract = next(
        message for message in messages if message["name"] == "reply_contract"
    )
    payload = json.loads(contract["content"])

    assert names[-1] == "player_input"
    assert names.index("reply_contract") < names.index("player_input")
    assert payload["mustMention"] == ["第三组", "稳定"]
    assert payload["historyAnchors"] == ["第三组"]
    assert "只输出 NPC 中文对白" in payload["instruction"]
    assert "不要使用 Markdown 标记" in payload["instruction"]
    assert "优先满足 historyAnchors" in payload["instruction"]


def test_history_anchors_keep_longest_phrase_without_nested_substrings() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "friend"},
        },
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [
            {"role": "user", "content": "我们刚检查了第三组。"},
            {"role": "assistant", "content": "第三组的记录还需整理。"},
        ],
        "behaviorExamples": [],
    }

    messages = PromptBuilder().build(context, "那第三组现在稳定了吗？")
    anchor = next(
        message for message in messages if message["name"] == "current_topic_anchor"
    )

    assert json.loads(anchor["content"])["historyAnchors"] == ["第三组"]


def test_prompt_builds_continuity_anchor_without_a_selected_behavior_example() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "friend"},
        },
        "modSources": ["SVE"],
        "gameState": {},
        "recentFacts": [],
        "history": [
            {"role": "user", "content": "我们刚才闻过新酿的葡萄酒。"},
        ],
        "behaviorExamples": [],
    }

    messages = PromptBuilder().build(context, "刚才那桶酒的味道怎么样？")
    anchor = next(
        message for message in messages if message["name"] == "current_topic_anchor"
    )
    contract = next(
        message for message in messages if message["name"] == "reply_contract"
    )

    assert json.loads(anchor["content"])["historyAnchors"] == ["酒"]
    contract_payload = json.loads(contract["content"])
    assert contract_payload["historyAnchors"] == ["酒"]
    assert contract_payload["mustMention"] == ["酒"]


def test_prompt_carries_previous_topic_into_anaphoric_follow_up() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stageProfile": {"stage": "acquaintance"},
        },
        "modSources": ["vanilla", "female-bachelors"],
        "gameState": {},
        "recentFacts": [],
        "history": [
            {"role": "user", "content": "今天训练得怎么样？"},
            {"role": "assistant", "content": "还不错，刚练完一组。"},
        ],
        "behaviorExamples": [
            {
                "topic": "training",
                "topicKeywords": ["训练", "跑步", "锻炼"],
                "playerInput": "今天训练得怎么样？",
                "npcReply": "还不错，刚练完一组。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "今天练的是力量还是速度？")
    anchor = next(
        message for message in messages if message["name"] == "current_topic_anchor"
    )
    contract = next(
        message for message in messages if message["name"] == "reply_contract"
    )

    assert json.loads(anchor["content"])["historyAnchors"] == ["训练"]
    assert json.loads(contract["content"])["mustMention"] == ["训练"]


def test_prompt_explicitly_blocks_roleplay_meta_commentary() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stageProfile": {"stage": "acquaintance"},
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
    }

    messages = PromptBuilder().build(context, "今天训练得怎么样？")
    safety = next(message for message in messages if message["name"] == "safety_rules")
    guard = next(
        message for message in messages if message["name"] == "post_history_voice_guard"
    )

    for message in (safety, guard):
        assert "不得说自己是 NPC、模型或提示词" in message["content"]
        assert "不要复述规则或解释自己正在扮演角色" in message["content"]


def test_current_topic_keeps_concrete_single_character_terms() -> None:
    context = {
        "npcIdentity": {"npcId": "Sophia", "displayName": "Sophia"},
        "modSources": ["SVE"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "behaviorExamples": [
            {
                "topic": "winemaking",
                "topicKeywords": ["酒", "味道"],
                "playerInput": "刚才那桶酒的味道怎么样？",
                "npcReply": "酒的味道还得再尝尝。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "刚才那桶酒的味道怎么样？")
    anchor = next(
        message for message in messages if message["name"] == "current_topic_anchor"
    )
    payload = json.loads(anchor["content"])

    assert payload["requiredTerms"] == ["酒", "味道"]


def test_plain_dialogue_filters_unrelated_magic_from_evidence_messages() -> None:
    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "speechEvidence": [
            {"text": "我最近只是在整理日常记录。"},
            {"text": "星界的预兆正在改变一切。"},
        ],
        "styleSamples": [
            {"text": "今天还算安静。"},
            {"text": "魔法的波动又开始了。"},
        ],
    }

    messages = PromptBuilder().build(context, "最近过得怎么样？")
    rendered = json.dumps(messages, ensure_ascii=False)
    evidence_messages = [
        message
        for message in messages
        if message["name"] in {"speech_evidence", "style_evidence"}
    ]

    assert evidence_messages
    assert "星界的预兆" not in rendered
    assert "魔法的波动" not in rendered
    assert "日常记录" in rendered
    assert "今天还算安静" in rendered


def test_plain_dialogue_filters_wizard_lore_variants_from_evidence_messages() -> None:
    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "speechEvidence": [
            {"text": "魔导炉今天又出了问题。"},
            {"text": "我昨晚睡得不多，今天还有几页记录要看。"},
        ],
        "styleSamples": [],
    }

    messages = PromptBuilder().build(context, "最近过得怎么样？")
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "魔导炉今天又出了问题" not in rendered
    assert "昨晚睡得不多" in rendered


def test_plain_dialogue_excludes_current_mod_magic_sample_from_generation_context() -> None:
    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodia"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "speechEvidence": [
            {
                "sourceMod": "Parrot.RomRas",
                "text": "预见你的到来，是我今天最有趣的发现。",
            }
        ],
        "styleSamples": [
            {
                "sourceMod": "Parrot.RomRas",
                "text": "预见你的到来，是我今天最有趣的发现。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "预见你的到来" not in rendered


def test_prompt_marks_mundane_input_for_plain_original_style_reply() -> None:
    context = {
        "npcIdentity": {"npcId": "Rasmodia", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
    }

    messages = PromptBuilder().build(context, "早上好，最近研究得怎么样？")
    safety = next(message for message in messages if message["name"] == "safety_rules")

    assert "当前输入属于日常寒暄或近况" in safety["content"]
    assert "不要把研究、咖啡、疲惫或小镇改写成神秘隐喻" in safety["content"]


def test_prompt_treats_history_as_continuity_not_voice_source() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "voiceStyle": {
                "tone": "直白、疲惫，偶尔用干巴巴的玩笑挡一下脆弱",
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [
            {"role": "user", "content": "你最近还好吗？"},
            {"role": "assistant", "content": "今天还算顺利。"},
        ],
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    safety = next(message for message in messages if message["name"] == "safety_rules")

    assert "历史只用于承接当前对话" in safety["content"]
    assert "不是角色语气来源" in safety["content"]


def test_prompt_does_not_apply_plain_mode_to_explicit_magic_question() -> None:
    context = {
        "npcIdentity": {"npcId": "Rasmodia", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
    }

    messages = PromptBuilder().build(context, "星界的预兆会影响今天的魔法实验吗？")
    safety = next(message for message in messages if message["name"] == "safety_rules")

    assert "当前输入属于日常寒暄或近况" not in safety["content"]


def test_prompt_turns_conversation_channel_into_explicit_scene_constraints() -> None:
    base_context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
    }

    remote_messages = PromptBuilder().build(
        {**base_context, "interaction": {"intent": "chat", "channel": "remote"}},
        "改天一起核对一下记录？",
    )
    remote_interaction = next(
        message for message in remote_messages if message["name"] == "interaction"
    )
    remote_payload = json.loads(remote_interaction["content"])

    face_messages = PromptBuilder().build(
        {
            **base_context,
            "interaction": {"intent": "chat", "channel": "face_to_face"},
        },
        "改天一起核对一下记录？",
    )
    face_interaction = next(
        message for message in face_messages if message["name"] == "interaction"
    )
    face_payload = json.loads(face_interaction["content"])

    assert remote_payload["channel"] == "remote"
    assert "手机或线上聊天" in remote_payload["channelInstruction"]
    assert "不要写成已经见面、走过来或当面发生" in remote_payload[
        "channelInstruction"
    ]
    assert face_payload["channel"] == "face_to_face"
    assert "当面聊天" in face_payload["channelInstruction"]
    assert "不要写成发消息或线上约定" in face_payload["channelInstruction"]


def test_prompt_removes_stardew_markup_from_style_evidence() -> None:
    context = {
        "npcIdentity": {"npcId": "Rasmodia", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "speechEvidence": [
            {
                "npcId": "Rasmodia",
                "sourceMod": "Parrot.RomRas",
                "text": (
                    "你好，年轻的@。#$b#${{e7}}#$e#$h"
                    "{{Random:1,2}} inputSeparator=|马格努斯转身离开。"
                ),
            }
        ],
        "styleSamples": [],
    }

    messages = PromptBuilder().build(context, "你好")
    speech = next(message for message in messages if message["name"] == "speech_evidence")

    assert "#$" not in speech["content"]
    assert "${{" not in speech["content"]
    assert "$h" not in speech["content"]
    assert "%马格努斯" not in speech["content"]
    assert "{{Random:" not in speech["content"]
    assert "inputSeparator=" not in speech["content"]
    assert "年轻的你" in speech["content"]


def test_prompt_removes_action_and_lone_dollar_residue_from_style_evidence() -> None:
    context = {
        "npcIdentity": {"npcId": "Shane", "displayName": "Shane"},
        "voiceCard": {
            "voiceAnchors": [
                {"sampleId": "action", "text": "*唉*……今天还得上班。"},
                {"sampleId": "dollar", "text": "$"},
            ]
        },
        "speechEvidence": [
            {"sampleId": "action", "text": "*唉*……今天还得上班。"},
            {"sampleId": "dollar", "text": "$"},
        ],
        "styleSamples": [],
        "history": [],
    }

    messages = PromptBuilder().build(context, "今天还好吗？")
    rendered = "\n".join(message["content"] for message in messages)

    assert "*唉*" not in rendered
    assert "今天还得上班" in rendered
    assert '"text": "$"' not in rendered


def test_prompt_drops_inline_narration_and_parenthetical_actions() -> None:
    context = {
        "npcIdentity": {"npcId": "Sophia", "displayName": "Sophia"},
        "speechEvidence": [
            {
                "sampleId": "good",
                "text": "呃……你好。",
            },
            {
                "sampleId": "inline-narration",
                "text": "…… %索菲娅没有理你。她看起来很伤心。",
            },
            {
                "sampleId": "parenthetical-action",
                "text": "（愤怒）你到底是什么意思？",
            },
        ],
        "styleSamples": [],
        "history": [],
    }

    messages = PromptBuilder().build(context, "你好")
    speech = next(message for message in messages if message["name"] == "speech_evidence")

    assert '"sampleId": "good"' in speech["content"]
    assert "索菲娅没有理你" not in speech["content"]
    assert "愤怒" not in speech["content"]


def test_prompt_removes_unseparated_stardew_input_separator_garbage() -> None:
    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "speechEvidence": [
            {
                "npcId": "Wizard",
                "sourceMod": "Parrot.RomRas",
                "text": "你好，年轻的@。inputSeparator=你你}}",
            }
        ],
        "styleSamples": [],
    }

    messages = PromptBuilder().build(context, "你今天看起来有点累。")
    speech = next(message for message in messages if message["name"] == "speech_evidence")

    assert "inputSeparator" not in speech["content"]
    assert "}}" not in speech["content"]


def test_plain_dialogue_omits_unrelated_global_magic_topic_hint() -> None:
    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "voiceCard": {
            "npcId": "Wizard",
            "features": {"magicMarkers": 291, "uncertaintyMarkers": 209},
            "topicHints": ["魔法与星界"],
            "evidenceRefs": ["Parrot.RomRas:daily"],
        },
    }

    messages = PromptBuilder().build(context, "最近小镇怎么样？")
    voice = next(message for message in messages if message["name"] == "voice_card")

    assert "魔法与星界" not in voice["content"]


def test_plain_dialogue_omits_unrelated_magic_voice_anchors_but_keeps_mundane_voice() -> None:
    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "history": [],
        "voiceCard": {
            "npcId": "Wizard",
            "voiceAnchors": [
                {
                    "sampleId": "magic",
                    "sourceMod": "vanilla",
                    "text": "我看到了星界的预兆，元素正在回应。",
                },
                {
                    "sampleId": "mundane",
                    "sourceMod": "vanilla",
                    "text": "如果没有重要的事，请不要打搅我。我还有好多活要干呢。",
                },
            ],
        },
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    voice = json.loads(
        next(message for message in messages if message["name"] == "voice_card")[
            "content"
        ]
    )["voiceCard"]
    anchor_texts = [item["text"] for item in voice["voiceAnchors"]]

    assert "我看到了星界的预兆，元素正在回应。" not in anchor_texts
    assert "如果没有重要的事，请不要打搅我。我还有好多活要干呢。" in anchor_texts


def test_explicit_magic_dialogue_keeps_magic_voice_anchor() -> None:
    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "history": [],
        "voiceCard": {
            "npcId": "Wizard",
            "voiceAnchors": [
                {
                    "sampleId": "magic",
                    "sourceMod": "vanilla",
                    "text": "我看到了星界的预兆，元素正在回应。",
                }
            ],
        },
    }

    messages = PromptBuilder().build(context, "你看到了什么星界预兆？")
    voice = json.loads(
        next(message for message in messages if message["name"] == "voice_card")[
            "content"
        ]
    )["voiceCard"]

    assert voice["voiceAnchors"][0]["text"] == "我看到了星界的预兆，元素正在回应。"


@pytest.mark.parametrize(
    ("state", "expected_stage"),
    (
        ({"friendshipHearts": 10}, "close"),
        ({"friendshipHearts": 10, "marriageStatus": "married"}, "married"),
        ({"friendshipHearts": 10, "marriageStatus": "roommate"}, "married"),
        (
            {"friendshipHearts": 10, "marriageStatus": "married", "childrenCount": 1},
            "parent",
        ),
        ({"relationshipStage": "dating"}, "dating"),
    ),
)
def test_context_stage_priority_tracks_relationship_lifecycle(
    state: dict[str, object],
    expected_stage: str,
) -> None:
    builder = ContextBuilder(PersonaStore(PERSONAS_DIR))

    context = builder.build(
        "Sophia",
        source_mods=["SVE"],
        **state,
    )

    assert context["npcIdentity"]["stageProfile"]["stage"] == expected_stage


def test_merge_persona_applies_only_matching_source_mod_overlays() -> None:
    base = {
        "npcId": "Wizard",
        "displayName": "Wizard",
        "pronouns": {"subject": "he"},
        "modOverlay": {
            "SVE": {"displayName": "Magnus"},
            "Rasmodia": {"displayName": "Rasmodia"},
        },
    }

    merged = merge_persona(base, source_mods=["SVE"])

    assert merged["displayName"] == "Magnus"
    assert base["displayName"] == "Wizard"


def test_persona_json_does_not_store_complete_story_text() -> None:
    for path in PERSONAS_DIR.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "story" not in json.dumps(payload, ensure_ascii=False).lower()


def test_context_builder_keeps_allowed_state_and_limits_history() -> None:
    builder = ContextBuilder(PersonaStore(PERSONAS_DIR))
    history = [
        {"role": "user", "content": f"第 {index} 轮"}
        for index in range(16)
    ]
    history[0]["unknown"] = "不得进入上下文"

    context = builder.build(
        npc_id="Wizard",
        source_mods=["SVE"],
        date="春 1 日",
        weather="晴",
        location="法师塔",
        friendship=128,
        relationship="朋友",
        recent_facts=["玩家刚刚拜访法师塔"],
        history=history,
        unknown_field="secret-value",
    )

    assert set(context) == {
        "npcIdentity",
        "modSources",
        "gameState",
        "recentFacts",
        "history",
    }
    assert set(context["gameState"]) == {
        "date",
        "weather",
        "location",
        "friendship",
        "relationship",
    }
    assert len(context["history"]) == 12
    assert [item["content"] for item in context["history"]] == [
        f"第 {index} 轮" for index in range(4, 16)
    ]
    assert "unknown" not in context["history"][0]
    assert "unknown_field" not in json.dumps(context, ensure_ascii=False)
    assert all(len(item["content"]) <= 240 for item in context["history"])


def test_behavior_examples_are_a_single_non_conversational_card() -> None:
    context = {
        "npcIdentity": {"npcId": "Shane", "displayName": "Shane"},
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "shane:work",
                "npcId": "Shane",
                "channels": ["face_to_face"],
                "relationshipStages": ["friend"],
                "playerInput": "鸡舍今天忙吗？",
                "npcReply": "还行。没着火，就算顺利。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    behavior = next(
        message for message in messages if message["name"] == "behavior_examples"
    )
    payload = json.loads(behavior["content"])

    assert payload["count"] == 1
    assert "不是原文台词" in payload["instruction"]
    assert sum(
        message.get("name") == "behavior_example_user" for message in messages
    ) == 1
    assert sum(
        message.get("name") == "behavior_example_assistant" for message in messages
    ) == 1
    assert messages[-1]["name"] == "player_input"


def test_behavior_card_does_not_expose_canned_dialogue_as_generation_target() -> None:
    context = {
        "npcIdentity": {"npcId": "Shane", "displayName": "Shane"},
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "shane:work",
                "npcId": "Shane",
                "channels": ["face_to_face"],
                "relationshipStages": ["friend"],
                "speechFunction": "answer_directly",
                "topic": "chicken_coop",
                "topicKeywords": ["鸡舍", "鸡"],
                "emotion": "tired_dry_humor",
                "playerInput": "鸡舍今天忙吗？",
                "npcReply": "还行。没着火，就算顺利。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    payload = json.loads(
        next(message for message in messages if message["name"] == "behavior_examples")[
            "content"
        ]
    )
    example = payload["examples"][0]

    assert "playerInput" not in example
    assert "npcReply" not in example
    assert example["conditions"]["speechFunction"] == "answer_directly"
    assert example["conditions"]["topic"] == "chicken_coop"
    assert "行为" in payload["instruction"]


def test_prompt_uses_only_one_behavior_example_card() -> None:
    context = {
        "npcIdentity": {"npcId": "Shane", "displayName": "Shane"},
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "shane:work",
                "playerInput": "鸡舍今天忙吗？",
                "npcReply": "还行。没着火，就算顺利。",
            },
            {
                "exampleId": "shane:food",
                "playerInput": "你吃饭了吗？",
                "npcReply": "吃了。至少咖啡没算一顿饭。",
            },
        ],
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    behavior_payload = json.loads(
        next(message for message in messages if message["name"] == "behavior_examples")[
            "content"
        ]
    )

    assert sum(
        message.get("name") == "behavior_example_user" for message in messages
    ) == 2
    assert sum(
        message.get("name") == "behavior_example_assistant" for message in messages
    ) == 2
    assert behavior_payload["count"] == 2


def test_prompt_labels_behavior_example_conditions_without_leaking_review_payload() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "stageProfile": {"stage": "acquaintance"},
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "shane:coop:acquaintance",
                "npcId": "Shane",
                "channels": ["face_to_face"],
                "relationshipStages": ["acquaintance"],
                "speechFunction": "answer_directly",
                "topic": "chicken",
                "emotion": "tired_dry_humor",
                "playerInput": "鸡舍今天忙吗？",
                "npcReply": "还行。没着火，就算顺利。",
                "review": {"naturalChinese": 2, "hardErrors": []},
            }
        ],
        "interaction": {
            "intent": "chat",
            "channel": "face_to_face",
        },
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    behavior_message = next(
        message for message in messages if message["name"] == "behavior_examples"
    )
    behavior_payload = json.loads(behavior_message["content"])
    rendered = json.dumps(messages, ensure_ascii=False)

    assert behavior_payload["examples"][0]["conditions"]["channel"] == [
        "face_to_face"
    ]
    assert behavior_payload["examples"][0]["conditions"]["relationshipStage"] == [
        "acquaintance"
    ]
    assert "answer_directly" in rendered
    assert "tired_dry_humor" in rendered
    assert "naturalChinese" not in rendered
    assert "hardErrors" not in rendered
    assert "不是原文台词" in behavior_payload["instruction"]
    assert any(
        message["name"] == "behavior_example_user" for message in messages
    )
    assert any(
        message["name"] == "behavior_example_assistant" for message in messages
    )
    assert messages[-1]["name"] == "player_input"


def test_reviewed_behavior_examples_become_adjacent_few_shot_messages_before_history() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "voiceStyle": {"tone": "直白、疲惫，偶尔用干巴巴的玩笑挡一下脆弱"},
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [
            {"role": "user", "content": "你说过今天要去鸡舍。"},
            {"role": "assistant", "content": "嗯，记得。"},
        ],
        "behaviorExamples": [
            {
                "exampleId": "shane:coop:approved",
                "sourceType": "human_approved",
                "relationshipStages": ["friend"],
                "channels": ["face_to_face"],
                "topic": "chicken_coop",
                "topicKeywords": ["鸡舍"],
                "playerInput": "鸡舍今天忙吗？",
                "npcReply": "还行。没着火，就算顺利。",
            },
            {
                "exampleId": "shane:coop:draft",
                "sourceType": "model_draft",
                "relationshipStages": ["friend"],
                "channels": ["face_to_face"],
                "topic": "chicken_coop",
                "topicKeywords": ["鸡舍"],
                "playerInput": "鸡舍今天忙吗？",
                "npcReply": "未审核的模型腔不应该进入示例。",
            },
        ],
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    names = [message["name"] for message in messages]
    user_index = names.index("behavior_example_user")
    assistant_index = names.index("behavior_example_assistant")
    history_index = names.index("conversation_history")
    player_input_index = names.index("player_input")

    assert assistant_index == user_index + 1
    assert messages[user_index]["content"] == "鸡舍今天忙吗？"
    assert messages[assistant_index]["content"] == "还行。没着火，就算顺利。"
    assert user_index < history_index < player_input_index
    assert "未审核的模型腔" not in json.dumps(messages, ensure_ascii=False)


def test_prompt_does_not_project_model_review_behavior_examples_into_few_shot() -> None:
    context = {
        "npcIdentity": {"npcId": "Alex", "displayName": "Alex"},
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "alex:approved",
                "sourceType": "human_approved",
                "topic": "training",
                "topicKeywords": ["训练"],
                "playerInput": "今天训练吗？",
                "npcReply": "当然。先热身，再开始。",
            },
            {
                "exampleId": "alex:review",
                "sourceType": "model_review",
                "topic": "training",
                "topicKeywords": ["训练"],
                "playerInput": "今天训练吗？",
                "npcReply": "这是一条尚未审核的评审草稿。",
            },
        ],
    }

    messages = PromptBuilder().build(context, "今天训练吗？")
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "当然。先热身，再开始。" in rendered
    assert "这是一条尚未审核的评审草稿" not in rendered


def test_unreviewed_handcrafted_behavior_is_only_a_condition_card() -> None:
    context = {
        "npcIdentity": {"npcId": "Alex", "displayName": "Alex"},
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "alex:draft",
                "sourceType": "handcrafted_example",
                "topic": "training",
                "topicKeywords": ["训练"],
                "speechFunction": "answer_directly",
                "playerInput": "今天训练吗？",
                "npcReply": "这条尚未人工确认的生成对白不能教模型说话。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "今天训练吗？")
    names = [message["name"] for message in messages]
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "behavior_examples" in names
    assert "behavior_example_user" not in names
    assert "behavior_example_assistant" not in names
    assert "这条尚未人工确认的生成对白" not in rendered
    assert "answer_directly" in rendered
    behavior = json.loads(
        next(message for message in messages if message["name"] == "behavior_examples")[
            "content"
        ]
    )
    assert "human_approved" in behavior["instruction"]


def test_stranger_stage_gives_shane_a_concrete_conversation_exit() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "stageProfile": {"stage": "stranger"},
            "stagePolicy": {
                "stage": "stranger",
                "responseShape": "用一句短答",
                "selfDisclosure": "只说表层近况",
                "initiative": "不主动",
                "followUp": "没有可补内容就停下",
                "boundaryMode": "不想聊时直接结束",
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [
            {"role": "user", "content": "最近还好吗？"},
            {"role": "assistant", "content": "还行。"},
        ],
    }

    messages = PromptBuilder().build(context, "你是不是不想和我聊天？")
    stage_card = json.loads(
        next(message for message in messages if message["name"] == "stage_execution_card")[
            "content"
        ]
    )

    assert "最多 1 句" in stage_card["instruction"]
    assert "不想聊" in stage_card["instruction"]
    assert "不补问题" in stage_card["instruction"]


def test_prompt_keeps_all_twelve_recent_history_turns_before_current_input() -> None:
    context = {
        "npcIdentity": {"npcId": "Shane", "displayName": "Shane"},
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [
            {"role": "user", "content": f"历史第 {index} 轮"}
            for index in range(12)
        ],
    }

    messages = PromptBuilder().build(context, "当前这一轮")
    history_messages = [
        message for message in messages if message["name"] == "conversation_history"
    ]
    rendered_history = "\n".join(message["content"] for message in history_messages)

    assert len(history_messages) == 12
    assert "历史第 0 轮" in rendered_history
    assert "历史第 11 轮" in rendered_history
    assert messages.index(history_messages[-1]) < messages.index(
        next(message for message in messages if message["name"] == "player_input")
    )


def test_prompt_stays_within_compact_budget_while_retaining_current_turn() -> None:
    long_text = "角色原文。" * 220
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "coreTraits": ["疲惫", "直白"],
            "voiceStyle": {"tone": "短句、干巴巴的玩笑"},
            "stageProfile": {"stage": "friend", "summary": "和玩家熟悉"},
        },
        "modSources": ["vanilla", "female-bachelors"],
        "gameState": {"date": "春 6 日", "location": "牧场"},
        "recentFacts": ["玩家今天去过鸡舍"],
        "history": [
            {"role": "user", "content": f"历史问题 {index} {long_text}"}
            for index in range(12)
        ],
        "speechEvidence": [
            {"sourceMod": "vanilla", "sourceKey": f"Mon{index}", "text": long_text}
            for index in range(6)
        ],
        "styleSamples": [
            {"sourceMod": "vanilla", "sourceKey": f"Tue{index}", "text": long_text}
            for index in range(8)
        ],
        "behaviorExamples": [
            {
                "exampleId": f"shane:{index}",
                "playerInput": f"问题 {index} {long_text}",
                "npcReply": f"回答 {index} {long_text}",
            }
            for index in range(4)
        ],
    }

    messages = PromptBuilder().build(context, "这是当前这一轮的问题")
    rendered = json.dumps(messages, ensure_ascii=False)

    assert len(rendered) < 16000
    assert "Shane" in rendered
    assert "这是当前这一轮的问题" in rendered
    assert "历史问题 11" in rendered


def test_prompt_limits_voice_refs_and_knowledge_facts_in_compact_context() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "voiceStyle": {"tone": "克制、学者式，但会直接回应"},
            "stageProfile": {"stage": "friend", "summary": "和玩家熟悉"},
        },
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "voiceCard": {
            "npcId": "Wizard",
            "features": {f"feature{index}": index for index in range(12)},
            "topicHints": [f"主题 {index}" for index in range(8)],
            "evidenceRefs": [f"source/path/{index}/with/a/long/reference" for index in range(8)],
        },
        "knowledgeFacts": [
            {
                "factId": f"fact-{index}",
                "sourceMod": "vanilla",
                "summary": f"已确认事实 {index}",
                "knowledgeScope": "canon_confirmed",
                "confidence": "high",
            }
            for index in range(8)
        ],
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    rendered = json.dumps(messages, ensure_ascii=False)
    voice_card = json.loads(
        next(message for message in messages if message["name"] == "voice_card")["content"]
    )["voiceCard"]
    knowledge = json.loads(
        next(message for message in messages if message["name"] == "knowledge_facts")["content"]
    )["knowledgeFacts"]

    assert len(voice_card["topicHints"]) <= 3
    assert len(voice_card["evidenceRefs"]) <= 3
    assert len(knowledge) <= 3
    assert len(rendered) < 4000


def test_prompt_message_order_is_fixed_and_excludes_secrets() -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        npc_id="Wizard",
        source_mods=["SVE"],
        date="春 1 日",
        weather="晴",
        location="法师塔",
        friendship=128,
        relationship="朋友",
        recent_facts=["玩家刚刚拜访法师塔"],
        history=[{"role": "assistant", "content": "欢迎。"}],
        api_key="secret-api-key",
    )

    messages = PromptBuilder().build(context, "你好")

    assert [message["role"] for message in messages] == [
        "system",
        "system",
        "system",
        "system",
        "system",
        "assistant",
        "system",
        "system",
        "system",
        "system",
        "system",
        "user",
    ]
    assert [message["name"] for message in messages] == [
        "safety_rules",
        "persona_core",
        "story_state",
        "mod_overlay",
        "game_state",
        "conversation_history",
        "progression_guard",
        "post_history_voice_guard",
        "voice_variation",
        "stage_execution_card",
        "voice_execution_card",
        "player_input",
    ]
    rendered = json.dumps(messages, ensure_ascii=False)
    assert "secret-api-key" not in rendered
    assert "api_key" not in rendered
    assert messages[-1]["content"] == "你好"


def test_compact_prompt_limits_repeated_evidence_history_and_order_metadata() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "coreTraits": ["克制", "直接"],
            "voiceStyle": {
                "tone": "克制、干燥、偶尔温柔",
                "sentencePattern": ["短句", "停顿"],
                "responseRules": ["直接回答", "少用反问"],
                "speechParticleHints": ["嗯", "好吧"],
            },
            "stageProfile": {
                "stage": "dating",
                "topicPool": ["研究", "夜晚"],
                "boundaries": ["尊重同意"],
            },
            "stagePolicy": {
                "stage": "dating",
                "responseShape": "1-3句",
                "initiative": "主动表达",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "responseOrder": ["先回答", "再亲近", "最后安排"],
                    "allowedKinds": ["affection_signal", "specific_plan"],
                    "minimumExpression": "自然表达对玩家的偏爱",
                },
            },
            "storyState": {
                "relationshipStage": "dating",
                "behaviorInstruction": "保持角色语气",
            },
        },
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {"season": "秋", "location": "法师塔"},
        "recentFacts": ["第三组正在复测"],
        "qualityContext": {
            "flirtIntensity": "direct",
            "adultConsensual": True,
            "romanceEligible": True,
            "relationshipContext": "双方已经确认恋爱关系",
            "initiativeExpectation": "proactive",
            "initiativeKind": "affection_signal",
        },
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": [
            {"role": "user", "content": f"历史玩家消息{i}"}
            for i in range(1, 8)
        ]
        + [
            {"role": "assistant", "content": f"历史 NPC 回复{i}"}
            for i in range(1, 8)
        ],
        "voiceCard": {
            "voiceAnchors": [
                {"text": "样本一"},
                {"text": "样本二"},
                {"text": "样本三"},
            ]
        },
        "styleSamples": [{"text": f"语气样本{i}"} for i in range(1, 4)],
        "speechEvidence": [{"text": f"原文样本{i}"} for i in range(1, 4)],
        "behaviorExamples": [
            {
                "exampleId": f"example-{i}",
                "npcId": "Wizard",
                "sourceType": "human_approved",
                "playerInput": f"玩家示范{i}",
                "npcReply": f"NPC示范{i}",
                "topic": "日常",
            }
            for i in range(1, 4)
        ],
        "knowledgeFacts": [{"summary": f"事实{i}", "knowledgeScope": "canon_confirmed"} for i in range(1, 4)],
        "knownCharacters": [
            {"knownNpcId": "Abigail", "summary": "关系摘要"}
        ],
        "storyEvents": [
            {"eventId": "event-1", "summary": "已完成事件"}
        ],
    }

    messages = PromptBuilder().build(context, "最近怎么样？", compact=True)
    rendered = json.dumps(messages, ensure_ascii=False)
    names = [message.get("name") for message in messages]

    assert len(rendered) < len(json.dumps(PromptBuilder().build(context, "最近怎么样？"), ensure_ascii=False))
    assert len(json.loads(next(message["content"] for message in messages if message.get("name") == "speech_evidence"))["speechEvidence"]) <= 1
    assert len(json.loads(next(message["content"] for message in messages if message.get("name") == "style_evidence"))["styleSamples"]) <= 1
    behavior_cards = [
        message for message in messages if message.get("name") == "behavior_examples"
    ]
    if behavior_cards:
        assert len(json.loads(behavior_cards[0]["content"])["examples"]) <= 1
    assert len([name for name in names if name == "conversation_history"]) <= 4
    assert "responseOrder" not in rendered
    assert "player_input" in names


def test_context_and_prompt_redact_sensitive_values_in_allowed_strings() -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        npc_id="Wizard",
        location="WizardTower apiKey=location-key",
        recent_facts=["token: fact-token"],
        history=[
            {
                "role": "assistant",
                "content": "secret: history-secret; authorization: Bearer history-auth",
            }
        ],
    )

    messages = PromptBuilder().build(context, "authorization: Bearer player-key")
    rendered = json.dumps(messages, ensure_ascii=False)
    context_rendered = json.dumps(context, ensure_ascii=False)

    for secret in (
        "location-key",
        "fact-token",
        "history-secret",
        "history-auth",
        "player-key",
    ):
        assert secret not in context_rendered
        assert secret not in rendered


def test_prompt_exposes_positive_original_voice_anchors() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "voiceStyle": {"tone": "像在街边聊天，偶尔爱炫耀"},
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "voiceCard": {
            "npcId": "Alex",
            "features": {"dryHumorMarkers": 2},
            "topicHints": [],
            "voiceAnchors": [
                {
                    "text": "嘿！这地方看起来还不错。",
                    "sourceMod": "vanilla",
                    "sampleId": "alex:daily:1",
                }
            ],
        },
    }

    messages = PromptBuilder().build(context, "今天过得怎么样？")
    voice = json.loads(
        next(message for message in messages if message["name"] == "voice_card")[
            "content"
        ]
    )["voiceCard"]

    assert voice["voiceAnchors"][0]["text"] == "嘿！这地方看起来还不错。"
    assert "优先参考 voiceAnchors" in next(
        message for message in messages if message["name"] == "voice_card"
    )["content"]


def test_prompt_exposes_role_specific_speech_particles_as_optional_material() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "voiceStyle": {
                "tone": "直白、疲惫",
                "openers": ["呃，怎么了？", "哦。还活着。"],
                "closers": ["我先忙这个。", "改天再聊。"],
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [],
        "voiceCard": {"npcId": "Shane", "voiceAnchors": []},
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    persona = json.loads(
        next(message for message in messages if message["name"] == "persona_core")[
            "content"
        ]
    )
    voice_card = next(
        message
        for message in messages
        if message["name"] == "voice_execution_card"
    )
    voice_style = persona["npcIdentity"]["voiceStyle"]

    assert voice_style["speechParticleHints"] == ["呃", "哦"]
    assert "可选" in voice_card["content"]
    assert "默认不用" in voice_card["content"]
    assert "一组三轮对话最多自然使用一次" in voice_card["content"]
    assert "不能连续重复" in voice_card["content"]


def test_prompt_places_voice_execution_card_after_history_before_player_input() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "voiceStyle": {
                "tone": "外向、爱炫耀一点",
                "sentencePattern": ["短句直接"],
                "responseRules": ["先回答玩家这句话"],
                "openers": ["嘿，怎么了？"],
                "closers": ["回头见。"],
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [{"role": "assistant", "content": "今天还行。"}],
    }

    messages = PromptBuilder().build(context, "你今天在忙什么？")
    names = [message["name"] for message in messages]
    card_index = names.index("voice_execution_card")
    history_index = names.index("conversation_history")
    player_index = names.index("player_input")
    card = json.loads(messages[card_index]["content"])

    assert history_index < card_index < player_index
    assert card["speechParticles"] == ["嘿"]
    assert "低优先级" in card["instruction"]
    assert "不能作为固定句首" in card["instruction"]
    assert "默认不用" in card["instruction"]
    assert "一组三轮对话最多自然使用一次" in card["instruction"]
    assert "不要把开场、正文和收尾机械拼接" in card["instruction"]


def test_prompt_uses_voice_anchor_as_neutral_few_shot_pair() -> None:
    """原版短句应作为自然示例回答，不再配一条相互冲突的元指令。"""

    context = {
        "npcIdentity": {"npcId": "Shane", "displayName": "Shane"},
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [],
        "voiceCard": {
            "npcId": "Shane",
            "voiceAnchors": [
                {
                    "sampleId": "shane:daily-anchor",
                    "sourceMod": "vanilla",
                    "text": "不行，我没时间和你聊天。",
                }
            ],
        },
        "speechEvidence": [
            {
                "sampleId": "shane:other-evidence",
                "sourceMod": "vanilla",
                "text": "这条不是优先语气锚点。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "鸡舍今天忙吗？")
    user_examples = [
        message
        for message in messages
        if message["name"] == "original_style_example_user"
    ]
    assistant_examples = [
        message
        for message in messages
        if message["name"] == "original_style_example_assistant"
    ]

    assert not user_examples
    assert assistant_examples
    assert assistant_examples[0]["content"] == "不行，我没时间和你聊天。"


def test_original_style_examples_do_not_use_repeated_synthetic_greeting_inputs() -> None:
    context = {
        "npcIdentity": {"npcId": "Alex", "displayName": "Alex"},
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [],
        "speechEvidence": [
            {
                "sampleId": "alex:weekday",
                "sourceMod": "vanilla",
                "sourceKey": "Mon",
                "text": "今天挺适合打球的，对不对？",
            },
            {
                "sampleId": "alex:relationship",
                "sourceMod": "vanilla",
                "sourceKey": "good_0",
                "text": "你来了？那正好，我正想找个人一起玩。",
            },
        ],
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    rendered = json.dumps(messages, ensure_ascii=False)

    assert not any(
        message["name"] == "original_style_example_user" for message in messages
    )
    assert rendered.count("你好。") == 0
    assert rendered.count("original_style_example_assistant") == 2


def test_prompt_selects_original_style_examples_across_dialogue_structures() -> None:
    """原版语气 few-shot 不能被同一类别的前两条对白占满。"""

    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "voiceStyle": {"tone": "像在街边聊天，偶尔爱炫耀"},
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [],
        "voiceCard": {
            "npcId": "Alex",
            "voiceAnchors": [
                {
                    "sampleId": "alex:introduction",
                    "sourceMod": "vanilla",
                    "sourceKey": "Introduction",
                    "text": "哦，嘿。你就是那个新来的吧？不错不错。",
                },
                {
                    "sampleId": "alex:weekday",
                    "sourceMod": "vanilla",
                    "sourceKey": "Mon",
                    "text": "今天挺适合打球的，对不对？",
                },
            ],
        },
        "speechEvidence": [
            {
                "sampleId": "alex:weekday-variant",
                "sourceMod": "vanilla",
                "sourceKey": "Tue2",
                "text": "海滩那边今天应该不错。",
            },
            {
                "sampleId": "alex:relationship",
                "sourceMod": "vanilla",
                "sourceKey": "good_0",
                "text": "你来了？那正好，我正想找个人一起玩。",
            },
        ],
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    examples = [
        message["content"]
        for message in messages
        if message["name"] == "original_style_example_assistant"
    ]

    assert len(examples) == 4
    assert {
        "哦，嘿。你就是那个新来的吧？不错不错。",
        "今天挺适合打球的，对不对？",
        "海滩那边今天应该不错。",
        "你来了？那正好，我正想找个人一起玩。",
    } <= set(examples)


def test_prompt_reasserts_stage_and_plain_dialogue_rules_after_style_examples() -> None:
    """few-shot 只能教语感，不能覆盖阶段边界和输出格式。"""

    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "stagePolicy": {
                "stage": "stranger",
                "responseShape": "用一句短答",
                "selfDisclosure": "只说表层近况",
                "initiative": "不主动",
                "followUp": "没有可补内容就停下",
                "boundaryMode": "不想聊时直接结束",
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [],
        "speechEvidence": [
            {
                "sampleId": "shane:mon",
                "sourceMod": "vanilla",
                "sourceKey": "Mon",
                "text": "不行，我没时间和你聊天。",
            },
            {
                "sampleId": "shane:good",
                "sourceMod": "vanilla",
                "sourceKey": "good_0",
                "text": "今天还行，至少没有出什么大问题。",
            },
        ],
    }

    messages = PromptBuilder().build(context, "今天天气怎么样？")
    names = [message["name"] for message in messages]
    style_index = names.index("original_style_examples")
    stage_index = names.index("stage_execution_card")
    stage_card = json.loads(messages[stage_index]["content"])

    assert style_index < stage_index < names.index("player_input")
    assert "原版语气示例不得覆盖当前阶段策略" in stage_card["instruction"]
    assert "最多 1 句" in stage_card["instruction"]
    assert "禁止动作旁白" in stage_card["instruction"]


def test_plain_dialogue_does_not_use_topic_bearing_behavior_few_shot() -> None:
    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "wizard:research",
                "topic": "research",
                "topicKeywords": ["最近", "怎么样"],
                "playerInput": "最近怎么样？",
                "npcReply": "我在整理一批符文数据，研究还没有结束。",
            },
            {
                "exampleId": "wizard:daily",
                "topic": "daily_status",
                "topicKeywords": ["最近", "怎么样"],
                "playerInput": "最近过得怎么样？",
                "npcReply": "还行。今天比昨天安静一点。",
            },
        ],
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "整理一批符文数据" not in rendered
    assert "daily_status" in rendered
    assert "今天比昨天安静一点" in rendered


def test_topic_prompt_uses_hidden_empty_trigger_without_a_player_message() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "friend"},
        },
        "interaction": {"intent": "topic"},
        "gameState": {"season": "春", "time": 800},
        "history": [
            {"role": "assistant", "content": "最近塔里的蜡烛烧得很快。"},
        ],
    }

    messages = PromptBuilder().build(context, "")
    names = [message["name"] for message in messages]
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "player_input" not in names
    assert names[-1] == "topic_trigger"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == ""
    assert "topic_response_contract" in names
    assert "主动找一个自然、符合当前情境的话题" in rendered
    assert "请主动找一个自然的话题。" not in rendered


def test_topic_prompt_projects_seed_and_chat_prompt_uses_continuation_contract() -> None:
    topic_context = {
        "npcIdentity": {
            "npcId": "Sebastian",
            "displayName": "Sebastian",
            "stageProfile": {"stage": "dating"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "qualityContext": {
            "topicSeed": "新歌单",
            "topicKeywords": ["歌单", "音乐"],
            "continuationMode": "anchored",
            "flirtIntensity": "direct",
        },
        "history": [],
    }
    topic_messages = PromptBuilder().build(topic_context, "")
    topic_rendered = json.dumps(topic_messages, ensure_ascii=False)

    assert any('"topicSeed": "新歌单"' in message["content"] for message in topic_messages)
    assert any('"topicKeywords": ["歌单", "音乐"]' in message["content"] for message in topic_messages)
    assert any('"continuationMode": "anchored"' in message["content"] for message in topic_messages)
    assert "具体且可以继续聊下去" in topic_rendered

    chat_context = {
        **topic_context,
        "interaction": {"intent": "chat", "channel": "remote"},
        "history": [
            {"role": "assistant", "content": "我刚整理好一张新歌单。"},
        ],
    }
    chat_messages = PromptBuilder().build(chat_context, "你说的是哪种音乐？")
    chat_names = [message["name"] for message in chat_messages]
    chat_rendered = json.dumps(chat_messages, ensure_ascii=False)

    assert "continuation_contract" in chat_names
    assert any("先回答当前玩家输入" in message["content"] for message in chat_messages)
    assert "topic_response_contract" not in chat_names
    assert chat_names[-1] == "player_input"


def test_plain_generic_small_talk_uses_only_the_daily_behavior_few_shot() -> None:
    """泛日常只使用日常行为示范，避免把具体研究事实带入当前回复。"""

    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "wizard:daily",
                "topic": "daily_status",
                "topicKeywords": ["最近", "怎么样"],
                "playerInput": "最近过得怎么样？",
                "npcReply": "比昨天好些。至少今天的记录没有再次失控。",
            }
        ],
        "speechEvidence": [
            {
                "sampleId": "wizard:daily-original",
                "sourceMod": "vanilla",
                "sourceKey": "Tue4",
                "text": "如果没有重要的事，请不要打搅我。我还有好多活要干呢。",
            }
        ],
        "styleSamples": [],
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    names = [message["name"] for message in messages]
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "behavior_examples" in names
    assert "daily_status" in rendered
    assert "behavior_example_user" in names
    assert "behavior_example_assistant" in names
    assert "记录没有再次失控" in rendered


def test_specific_behavior_card_also_provides_a_short_handcrafted_few_shot() -> None:
    """人工行为样本同时提供短问答，帮助模型学习角色的真实节奏。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "voiceStyle": {"tone": "轻柔、谨慎，偶尔停顿"},
        },
        "modSources": ["SVE"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "behaviorExamples": [
            {
                "exampleId": "sophia:vineyard:acquaintance",
                "channels": ["remote"],
                "relationshipStages": ["acquaintance"],
                "speechFunction": "answer_directly",
                "topic": "vineyard",
                "topicKeywords": ["葡萄园"],
                "emotion": "warm_bubbly",
                "playerInput": "今天葡萄园忙不忙？",
                "npcReply": "这句书面化示范不应成为模型的固定说法。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "今天葡萄园忙不忙？")
    names = [message["name"] for message in messages]
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "behavior_examples" in names
    assert "behavior_example_user" in names
    assert "behavior_example_assistant" in names
    assert "这句书面化示范" in rendered


def test_plain_dialogue_keeps_character_voice_anchor_as_style_only() -> None:
    """日常问题不引入魔法事实，但不能因此抹掉 Wizard 的专属语气。"""

    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "voiceCard": {
            "npcId": "Wizard",
            "voiceAnchors": [
                {
                    "sampleId": "wizard:daily-anchor",
                    "sourceMod": "vanilla",
                    "text": "年轻的你，先把问题说清楚。",
                }
            ],
        },
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    voice = json.loads(
        next(message for message in messages if message["name"] == "voice_card")[
            "content"
        ]
    )
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "年轻的你" in voice["voiceCard"]["voiceAnchors"][0]["text"]
    assert "只模仿表达方式，不照搬其中的事实" in rendered
    assert "魔法与星界" not in rendered


def test_plain_dialogue_filters_predictive_magic_voice_semantics() -> None:
    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "history": [],
        "voiceCard": {
            "npcId": "Wizard",
            "voiceAnchors": [
                {
                    "sampleId": "fate",
                    "sourceMod": "vanilla",
                    "text": "未来和未知总会给人报应。",
                },
                {
                    "sampleId": "mundane",
                    "sourceMod": "vanilla",
                    "text": "我还有几页记录要看。",
                },
            ],
        },
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    voice = json.loads(
        next(message for message in messages if message["name"] == "voice_card")[
            "content"
        ]
    )["voiceCard"]
    anchor_texts = [item["text"] for item in voice["voiceAnchors"]]

    assert "未来和未知总会给人报应。" not in anchor_texts
    assert "我还有几页记录要看。" in anchor_texts


def test_explicit_predictive_magic_keeps_predictive_voice_anchor() -> None:
    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "history": [],
        "voiceCard": {
            "npcId": "Wizard",
            "voiceAnchors": [
                {
                    "sampleId": "fate",
                    "sourceMod": "vanilla",
                    "text": "未来和未知总会给人报应。",
                }
            ],
        },
    }

    messages = PromptBuilder().build(context, "你怎么看未来和报应？")
    voice = json.loads(
        next(message for message in messages if message["name"] == "voice_card")[
            "content"
        ]
    )["voiceCard"]

    assert voice["voiceAnchors"][0]["text"] == "未来和未知总会给人报应。"


def test_prompt_marks_previous_openings_as_non_reusable() -> None:
    context = {
        "npcIdentity": {"npcId": "Alex", "displayName": "Alex"},
        "modSources": ["vanilla"],
        "gameState": {},
        "recentFacts": [],
        "history": [
            {"role": "user", "content": "嗨。"},
            {"role": "assistant", "content": "嘿，你！今天怎么样？"},
        ],
    }

    messages = PromptBuilder().build(context, "最近还好吗？")
    guard = next(
        message for message in messages if message["name"] == "post_history_voice_guard"
    )

    assert "不要重复历史中的开场" in guard["content"]
    assert "嘿，你" in guard["content"]


def test_prompt_emits_structured_opening_avoidance_constraints() -> None:
    context = {
        "npcIdentity": {"npcId": "Alex", "displayName": "Alex"},
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [
            {"role": "user", "content": "嗨。"},
            {"role": "assistant", "content": "嘿，你！今天怎么样？"},
        ],
    }

    messages = PromptBuilder().build(context, "最近还好吗？")
    guard = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "post_history_voice_guard"
        )["content"]
    )

    assert guard["avoidOpenings"] == ["嘿，你"]
    assert "嘿" in guard["avoidOpeningPrefixes"]
    assert "不能以 avoidOpeningPrefixes 中的词开头" in guard["instruction"]


def test_prompt_marks_recent_voice_particles_as_non_reusable() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "voiceStyle": {
                "tone": "外向、爱炫耀一点",
                "openers": ["嘿，怎么了？", "当然，怎么了？"],
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [
            {"role": "user", "content": "今天训练得怎么样？"},
            {"role": "assistant", "content": "当然不错！刚跑完一圈。"},
            {"role": "user", "content": "明天还练吗？"},
            {"role": "assistant", "content": "嘿，当然。看你能不能跟上。"},
        ],
    }

    messages = PromptBuilder().build(context, "那下午见？")
    card = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "voice_execution_card"
        )["content"]
    )

    assert card["avoidSpeechParticles"] == ["嘿", "当然"]
    assert "默认不用" in card["instruction"]
    assert "avoidSpeechParticles" in card["instruction"]


def test_voice_execution_card_downgrades_full_openers_to_particle_hints() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "voiceStyle": {
                "tone": "外向、爱炫耀一点",
                "openers": ["嘿，怎么了？"],
                "closers": ["回头见。"],
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "你今天在忙什么？")
    card = next(
        message for message in messages if message["name"] == "voice_execution_card"
    )
    payload = json.loads(card["content"])

    assert "嘿，怎么了？" not in card["content"]
    assert payload["speechParticles"] == ["嘿"]
    assert "低优先级" in payload["instruction"]
    assert "不能作为固定句首" in payload["instruction"]


def test_prompt_recovers_prior_object_for_anaphoric_continuation() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "friend"},
        },
        "modSources": ["SVE"],
        "gameState": {},
        "history": [
            {"role": "user", "content": "我们刚才闻过新酿的葡萄酒。"},
            {"role": "assistant", "content": "那桶酒还需要再放一会儿。"},
        ],
        "behaviorExamples": [
            {
                "topic": "winemaking",
                "topicKeywords": ["酒", "酸味", "上一批"],
                "playerInput": "这批酒的味道怎么样？",
                "npcReply": "比上一批酸一点，但香味更好。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "上一批的酸味是不是更明显？")
    anchor = next(
        message
        for message in messages
        if message["name"] == "current_topic_anchor"
    )

    assert "酒" in json.loads(anchor["content"])["historyAnchors"]


def test_reply_contract_makes_history_object_a_first_class_requirement() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "friend"},
        },
        "modSources": ["Romanceable Rasmodius"],
        "gameState": {},
        "history": [
            {"role": "user", "content": "你先看看第三组。"},
            {"role": "assistant", "content": "我先核对记录。"},
        ],
        "behaviorExamples": [
            {
                "exampleId": "wizard:research-result",
                "channels": ["face_to_face"],
                "relationshipStages": ["friend"],
                "speechFunction": "give_specific_detail",
                "topic": "research_result",
                "topicKeywords": ["第三组", "稳定"],
                "playerInput": "那第三组现在稳定了吗？",
                "npcReply": "第三组稳定了，第二组还得重测。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "那第三组现在稳定了吗？")
    contract = json.loads(
        next(message for message in messages if message["name"] == "reply_contract")[
            "content"
        ]
    )

    assert contract["historyAnchors"] == ["第三组"]
    assert contract["continuity"]["mustMentionOneOf"] == ["第三组"]
    assert "第一句就点名" in contract["instruction"]


def test_prompt_adds_voice_variation_card_after_history_before_player_input() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "stageProfile": {"stage": "acquaintance"},
            "voiceStyle": {
                "speechParticleHints": ["嗯", "哦", "啊"],
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [
            {"role": "user", "content": "今天过得怎么样？"},
            {"role": "assistant", "content": "嗯，凑合。"},
        ],
    }

    messages = PromptBuilder().build(context, "明天还要上班吗？")
    names = [message["name"] for message in messages]
    variation_index = names.index("voice_variation")
    history_indices = [
        index for index, name in enumerate(names) if name == "conversation_history"
    ]

    assert history_indices
    assert history_indices[-1] < variation_index < names.index("player_input")
    variation = next(
        message for message in messages if message["name"] == "voice_variation"
    )
    assert "不必使用" in variation["content"]
    assert "同一语气词不能连续重复" in variation["content"]
    assert "嗯" in variation["content"]


def test_prompt_adds_progression_guard_after_history_before_player_input() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Sebastian",
            "displayName": "Sebastian",
            "stageProfile": {"stage": "married"},
        },
        "modSources": ["vanilla", "female-bachelors"],
        "gameState": {"relationshipStage": "married"},
        "history": [
            {"role": "user", "content": "厨房我来收尾，你去把电脑关了。"},
            {"role": "assistant", "content": "好，厨房交给我。"},
        ],
    }

    messages = PromptBuilder().build(context, "那现在过来陪我坐一会儿？")
    names = [message["name"] for message in messages]
    guard_index = names.index("progression_guard")
    history_indices = [
        index for index, name in enumerate(names) if name == "conversation_history"
    ]

    assert history_indices[-1] < guard_index < names.index("player_input")
    guard = next(message for message in messages if message["name"] == "progression_guard")
    assert "新增一个具体进展" in guard["content"]
    assert "明确收口" in guard["content"]
    assert "不能只改写上一句" in guard["content"]


def test_prompt_adds_affection_initiative_card_for_dating_without_waiting_for_love_words() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "stagePolicy": {
                "stage": "dating",
                "responseShape": "通常 2–3 句",
                "selfDisclosure": "可以分享当天的小事",
                "initiative": "可以主动安排约会",
                "followUp": "确认对方意愿",
                "boundaryMode": "尊重同意",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "allowedIntensities": ["light", "direct"],
                    "allowedKinds": ["affection_signal", "specific_plan"],
                    "maxActions": 1,
                    "channelRules": {
                        "remote": "只能提出待确认安排",
                        "face_to_face": "可以描述当面反应",
                    },
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "qualityContext": {
            "flirtIntensity": "light",
            "adultConsensual": True,
            "romanceEligible": True,
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "今天葡萄园忙不忙？")
    names = [message["name"] for message in messages]
    card = json.loads(
        next(message for message in messages if message["name"] == "affection_initiative")[
            "content"
        ]
    )

    assert names.index("quality_context") < names.index("affection_initiative")
    assert names.index("affection_initiative") < names.index("player_input")
    assert card["affectionInitiative"]["initiativeMode"] == "proactive"
    assert "不需要等待玩家先说情话" in card["instruction"]
    assert "最多一个亲密动作" in card["instruction"]
    assert "远程" in card["instruction"]
    assert card["affectionInitiative"]["minimumExpression"]
    assert "不要先复述、改写或总结玩家原话" in card["instruction"]
    assert "不只礼貌答题" in card["instruction"]
    assert "功能性邀约不够" in card["instruction"]
    assert "为什么想和玩家相处" in card["instruction"]
    assert "明确指向玩家本人" in card["instruction"]
    assert "让爱意在自然位置尽早出现" in card["instruction"]
    assert "不要把每轮回复写成固定顺序" in card["instruction"]


def test_prompt_places_a_final_affection_priority_check_before_the_player_turn() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Sebastian",
            "displayName": "Sebastian",
            "stageProfile": {"stage": "dating"},
            "stagePolicy": {
                "stage": "dating",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "allowedIntensities": ["light", "direct"],
                    "allowedKinds": ["companionship", "specific_plan"],
                    "maxActions": 1,
                    "channelRules": {"remote": "只提出待确认安排"},
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "qualityContext": {
            "flirtIntensity": "direct",
            "romanceEligible": True,
            "adultConsensual": True,
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "你最近在听什么歌？")
    names = [message["name"] for message in messages]
    final_check = next(
        message for message in messages if message["name"] == "affection_priority_final"
    )

    assert names.index("affection_priority_final") < names.index("player_input")
    assert names.index("affection_initiative") < names.index("affection_priority_final")
    assert "爱意在自然位置尽早出现" in final_check["content"]
    assert "不要让天气、地点、工作、物品或安排占满开场" in final_check["content"]
    assert "不要先复述或总结玩家原话" in final_check["content"]


def test_prompt_affection_card_keeps_explicit_consent_and_end_boundaries() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "stageProfile": {"stage": "dating"},
            "stagePolicy": {
                "stage": "dating",
                "affectionInitiative": {
                    "initiativeMode": "guarded",
                    "allowedIntensities": ["light", "direct"],
                    "allowedKinds": ["guarded_care", "conversation_exit"],
                    "maxActions": 1,
                    "channelRules": {"remote": "不写成见面"},
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "qualityContext": {
            "flirtIntensity": "explicit",
            "adultConsensual": False,
            "romanceEligible": True,
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "算了，你先休息，我不打扰了。")
    card = next(
        message for message in messages if message["name"] == "affection_initiative"
    )
    rendered = card["content"]

    assert "explicit" in rendered
    assert "同意" in rendered
    assert "明确结束" in rendered


def test_prompt_direct_reply_does_not_force_a_restatement_before_the_answer() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "stagePolicy": {
                "stage": "dating",
                "responseShape": "通常 2–3 句",
                "selfDisclosure": "可以分享当天的小事",
                "initiative": "可以主动安排约会",
                "followUp": "确认对方意愿",
                "boundaryMode": "尊重同意",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "allowedIntensities": ["light", "direct"],
                    "allowedKinds": ["affection_signal", "specific_plan"],
                    "minimumExpression": "每轮至少自然表达一处爱意",
                    "maxActions": 1,
                    "channelRules": {"remote": "只提出待确认安排"},
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "qualityContext": {"flirtIntensity": "direct"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "今天葡萄园忙不忙？")
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "不要先复述、改写或总结玩家原话" in rendered
    assert "直接接住其意思并推进" in rendered
    assert "不得调情" in rendered
    assert "已经见面" in rendered


def test_topic_prompt_uses_approved_affection_pair_and_concrete_warmth_signal() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "married"},
            "stagePolicy": {
                "stage": "married",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "allowedIntensities": ["light", "direct"],
                    "allowedKinds": ["affection_signal", "shared_evening"],
                    "warmthSignals": [
                        "让玩家明确感到自己被想念或被单独选择",
                        "把陪伴说成因为在乎玩家，而不是事务安排",
                    ],
                    "maxActions": 1,
                    "channelRules": {"remote": "只提出待确认安排"},
                },
            },
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "qualityContext": {
            "flirtIntensity": "direct",
            "romanceEligible": True,
            "adultConsensual": True,
        },
        "behaviorExamples": [
            {
                "exampleId": "wizard:married:evening:02",
                "sourceType": "human_approved",
                "relationshipStages": ["married"],
                "channels": ["face_to_face"],
                "topic": "shared_evening",
                "playerInput": "今晚别把时间都给那些记录，留一点给我，好吗？",
                "npcReply": "可以。把记录先放一边，过来坐一会儿。",
            },
            {
                "exampleId": "draft-do-not-teach",
                "sourceType": "model_draft",
                "relationshipStages": ["married"],
                "channels": ["remote"],
                "playerInput": "你在做什么？",
                "npcReply": "这条草稿不应进入示范。",
            },
        ],
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    names = [message["name"] for message in messages]
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "behavior_example_user" in names
    assert "behavior_example_assistant" in names
    assert "这条草稿不应进入示范" not in rendered
    affection = json.loads(
        next(message for message in messages if message["name"] == "affection_initiative")[
            "content"
        ]
    )
    assert affection["affectionInitiative"]["warmthSignals"]
    assert "被想念" in affection["instruction"]
    assert "仅说共同安排不够" in affection["instruction"]
    assert "功能性邀约不够" in affection["instruction"]
    assert "明确指向玩家本人" in affection["instruction"]
    topic = json.loads(
        next(message for message in messages if message["name"] == "topic_response_contract")[
            "content"
        ]
    )
    assert "爱意" in topic["instruction"]
    assert "至少一处可感知的爱意" in topic["instruction"]
    assert "不要先复述或总结玩家不存在的原话" in topic["instruction"]
    assert "输出前默默检查" in topic["instruction"]
    assert "不能用反问或功能性邀约替代" in topic["instruction"]
    assert "让爱意在前一两句自然出现" in topic["instruction"]
    assert "不能只用功能性邀约暗示" in topic["instruction"]
    assert names[-1] == "topic_trigger"


def test_affection_prompt_allows_natural_early_warmth_without_fixed_three_part_order() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "stagePolicy": {
                "stage": "dating",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "allowedIntensities": ["light", "direct"],
                    "allowedKinds": ["affection_signal", "specific_plan"],
                    "maxActions": 1,
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "qualityContext": {"flirtIntensity": "direct"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "今天在酒窖忙了一天，不过我很想你。")
    affection = json.loads(
        next(message for message in messages if message["name"] == "affection_initiative")[
            "content"
        ]
    )
    final_check = next(
        message for message in messages if message["name"] == "affection_priority_final"
    )

    instruction = affection["instruction"]
    assert "不要把每轮回复写成固定顺序" in instruction
    assert "前一两句" in instruction
    assert "不要每次都用同一套" in instruction
    assert "回复顺序固定为" not in instruction
    assert "第一句先让玩家听见" not in instruction
    assert "不要套固定开场顺序" in final_check["content"]
    assert "前一两句" in final_check["content"]
    assert "第一句直接说出对玩家本人的感受或愿望" not in final_check["content"]
