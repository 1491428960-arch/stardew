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


def test_relationship_world_request_is_projected_without_objective_table_leak() -> None:
    context = ContextBuilder().build(
        {
            "npcId": "Alex",
            "relationshipWorld": {
                "objectiveRelationships": [
                    {"npcId": "Sophia", "relationType": "dating"},
                    {
                        "npcId": "Sebastian",
                        "relationType": "married",
                        "publicEventId": "wedding:sebastian",
                    },
                ],
                "views": [
                    {
                        "ownerNpcId": "Alex",
                        "subjectNpcId": "Sophia",
                        "relationType": "dating",
                        "visibility": "unknown",
                        "source": "none",
                    },
                    {
                        "ownerNpcId": "Alex",
                        "subjectNpcId": "Sebastian",
                        "relationType": "married",
                        "visibility": "known",
                        "source": "wedding",
                    },
                ],
            },
        }
    )
    prompt = PromptBuilder().build(context, "你知道 Sebastian 的婚礼吗？")
    text = "\n".join(message["content"] for message in prompt)

    assert "Sebastian" in text
    assert "Sophia" in text
    assert "objectiveRelationships" not in text
    assert '"visibility": "unknown"' in text


def test_prompt_distinguishes_policy_acceptance_from_personal_acceptance_and_jealousy() -> None:
    messages = PromptBuilder().build(
        ContextBuilder().build(
            {
                "npcId": "Sophia",
                "relationshipStage": "dating",
                "relationshipWorld": {
                    "views": [
                        {
                            "ownerNpcId": "Sophia",
                            "subjectNpcId": "Alex",
                            "relationType": "dating",
                            "visibility": "suspected",
                            "source": "observation",
                        },
                    ],
                    "acceptanceByNpc": {"Sophia": "conditional"},
                    "mediationByNpc": {
                        "Sophia": {
                            "status": "resolved",
                            "outcome": "conditional",
                            "nextStep": "固定周末独处",
                        },
                    },
                    "jealousyByNpc": {
                        "Sophia": {
                            "active": True,
                            "trigger": "time",
                            "intensity": "light",
                            "need": "不要连续失约",
                        },
                    },
                },
            }
        ),
        "我昨晚陪 Alex 训练，你是不是有点在意？",
    )
    text = "\n".join(message["content"] for message in messages)

    assert "法律允许" in text
    assert "个人可以拒绝或暂缓" in text
    assert "suspected" in text
    assert "不要把嫉妒写成否定政策" in text
    assert "不要自动知道其他 NPC 的私密关系" in text
    assert "固定周末独处" not in text
    assert '"nextStep"' not in text


def test_relationship_prompt_keeps_npc_faithful_to_player_relationships() -> None:
    context = ContextBuilder().build(
        {
            "npcId": "Sophia",
            "relationshipWorld": {
                "objectiveRelationships": [
                    {"npcId": "Sophia", "relationType": "married"},
                    {"npcId": "Shane", "relationType": "dating"},
                ],
                "views": [
                    {
                        "ownerNpcId": "Sophia",
                        "subjectNpcId": "Shane",
                        "relationType": "dating",
                        "visibility": "known",
                        "source": "player_statement",
                    },
                ],
                "acceptanceByNpc": {"Sophia": "conditional"},
            },
        }
    )
    messages = PromptBuilder().build(
        context,
        "我想直接告诉你：我也想和 Shane 交往。",
    )
    text = "\n".join(message["content"] for message in messages)

    assert "玩家与多个 NPC 交往" in text
    assert "关系主体固定为玩家" in text
    assert "knowledge 里的其他 NPC 只是玩家的关系对象" in text
    assert "当前 NPC 只与玩家构成恋爱关系" in text
    assert "不能说自己想和其他 NPC 交往" in text
    assert "这个‘我’是玩家" in text
    assert "不要把玩家的其他伴侣改写成当前 NPC 的暧昧对象" in text


def test_relationship_prompt_adds_a_final_no_scheduling_override() -> None:
    context = ContextBuilder().build(
        {
            "npcId": "Sophia",
            "relationshipStage": "dating",
            "relationshipWorld": {
                "views": [
                    {
                        "ownerNpcId": "Sophia",
                        "subjectNpcId": "Alex",
                        "relationType": "dating",
                        "visibility": "known",
                        "source": "player_statement",
                    },
                ],
                "acceptanceByNpc": {"Sophia": "conditional"},
                "jealousyByNpc": {
                    "Sophia": {
                        "active": True,
                        "trigger": "time",
                        "intensity": "light",
                        "need": "不要把我当成可有可无的人",
                    },
                },
            },
        }
    )

    messages = PromptBuilder().build(
        context,
        "我也想和 Alex 交往，但我不想现在讨论怎么分配时间。",
    )
    names = [message["name"] for message in messages]
    final_override = next(
        message for message in messages if message["name"] == "relationship_world_final"
    )

    assert names.index("relationship_world") < names.index("relationship_world_final")
    assert names.index("relationship_world_final") < names.index("player_input")
    assert "覆盖通用的安排、邀约和亲密行动建议" in final_override["content"]
    assert "不要讨论或提出未来时间、排期、预约或时间分配" in final_override["content"]
    for marker in ("今晚", "明天", "晚点", "等会儿", "下次"):
        assert marker in final_override["content"]
    assert "允许 NPC 对自己的记录、笔记、研究、工作或普通事务延期" in final_override[
        "content"
    ]
    assert "允许自然对话收尾" in final_override["content"]
    assert "玩家、共同活动、见面、预约、固定时长或自动履约" in final_override[
        "content"
    ]
    assert "当前轮的感受" in final_override["content"]
    assert "即时动作" in final_override["content"]
    assert "简短收口" in final_override["content"]


def test_relationship_topic_prompt_prioritizes_npc_initiated_jealousy() -> None:
    context = ContextBuilder().build(
        {
            "npcId": "Sebastian",
            "displayName": "Sebastian",
            "relationshipStage": "married",
            "relationshipWorld": {
                "views": [
                    {
                        "ownerNpcId": "Sebastian",
                        "subjectNpcId": "Sophia",
                        "relationType": "dating",
                        "visibility": "known",
                        "source": "wedding",
                    },
                ],
                "jealousyByNpc": {
                    "Sebastian": {
                        "active": True,
                        "trigger": "affection_imbalance",
                        "intensity": "light",
                        "need": "被邀请共享音乐",
                    },
                },
            },
            "intent": "topic",
            "channel": "face_to_face",
        }
    )

    messages = PromptBuilder().build(context, "")
    final_override = next(
        message for message in messages if message["name"] == "relationship_world_final"
    )

    assert "由 NPC 主动谈起" in final_override["content"]
    assert "自己的不安、吃醋或边界" in final_override["content"]
    assert "不等玩家先问" in final_override["content"]
    assert "不替其他 NPC 发言" in final_override["content"]


def test_relationship_jealousy_and_recovery_turns_make_conversation_lead_optional() -> None:
    context = ContextBuilder().build(
        {
            "npcId": "Wizard",
            "relationshipStage": "married",
            "channel": "remote",
            "intent": "chat",
            "qualityContext": {
                "relationshipFocus": "recovery",
            },
            "relationshipWorld": {
                "jealousyByNpc": {
                    "Wizard": {
                        "active": True,
                        "trigger": "affection_imbalance",
                        "intensity": "light",
                        "need": "被认真纳入关系分享",
                    },
                },
            },
        }
    )

    messages = PromptBuilder().build(context, "我听见了，你在意的地方直接告诉我。")
    lead = next(message for message in messages if message["name"] == "conversation_lead")
    payload = json.loads(lead["content"])

    assert payload["conversationLead"]["required"] == "optional"
    assert payload["conversationLead"]["relationshipFocus"] == "recovery"
    assert "允许倾听或简短收口" in payload["instruction"]


def test_face_to_face_prompt_picks_up_current_npc_open_loop_without_scheduling() -> None:
    context = ContextBuilder().build(
        {
            "npcId": "Wizard",
            "relationshipStage": "dating",
            "channel": "face_to_face",
            "relationshipWorld": {
                "openLoops": [
                    {
                        "loopId": "wizard:rune:Spring-14",
                        "npcId": "Wizard",
                        "topic": "rune_review",
                        "originChannel": "remote",
                        "nextChannel": "face_to_face",
                        "status": "open",
                        "shortSummary": "线上留下了核对符文数据的话题",
                        "createdOn": "Spring 14",
                    },
                ],
            },
        }
    )

    messages = PromptBuilder().build(context, "你好")
    relationship_card = next(
        message for message in messages if message["name"] == "relationship_world"
    )
    final_card = next(
        message for message in messages if message["name"] == "relationship_world_final"
    )

    assert "openLoops" in relationship_card["content"]
    assert "主动接回" in relationship_card["content"]
    assert "已经当面" in final_card["content"]
    assert "不要讨论或提出未来时间、排期、预约或时间分配" in final_card["content"]


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


@pytest.mark.parametrize(
    ("npc_id", "display_name", "asset_name"),
    [
        ("Alex", "爱丽克斯", "Alex"),
        ("Elliott", "埃琳娜", "Elena"),
        ("Harvey", "哈丽特", "Harriet"),
        ("Sam", "萨姆", "Sam"),
        ("Sebastian", "塞布瑞娜", "Sabrina"),
        ("Shane", "珊恩", "Shane"),
    ],
)
def test_female_bachelor_overlay_uses_mod_display_name_aliases_and_feminine_pronouns(
    npc_id: str,
    display_name: str,
    asset_name: str,
) -> None:
    persona = PersonaStore(PERSONAS_DIR).get_persona(
        npc_id,
        source_mods=["female-bachelors"],
    )

    assert persona["displayName"] == display_name
    assert persona["pronouns"] == {
        "subject": "she",
        "object": "her",
        "possessive": "her",
    }
    assert asset_name in persona["aliases"]
    assert npc_id in persona["aliases"]


def test_female_bachelor_runtime_compatibility_name_does_not_replace_mod_name() -> None:
    context = ContextBuilder().build(
        {
            "npcId": "Sebastian",
            "displayName": "Sebastian",
            "sourceMods": ["vanilla", "female-bachelors"],
        }
    )

    assert context["npcIdentity"]["displayName"] == "塞布瑞娜"
    assert context["npcIdentity"]["pronouns"]["subject"] == "she"
    assert "Sabrina" in context["npcIdentity"]["aliases"]


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


@pytest.mark.parametrize(
    ("npc_id", "subject"),
    (
        ("Victor", "he"),
        ("Olivia", "she"),
        ("Andy", "he"),
        ("Lance", "he"),
        ("Claire", "she"),
        ("Morris", "he"),
    ),
)
def test_normal_sve_roles_project_normal_identity_without_female_overlay(
    npc_id: str,
    subject: str,
) -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        npc_id,
        source_mods=["SVE"],
        friendshipHearts=6,
    )

    identity = context["npcIdentity"]

    assert identity["npcId"] == npc_id
    assert identity["displayName"] == npc_id
    assert identity["pronouns"]["subject"] == subject
    assert "genderPresentation" not in identity
    assert "female-bachelors" not in json.dumps(identity, ensure_ascii=False)


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
    from stardew_ai_bridge.stage_policy import build_stage_policy

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

    assert "15–80 字" in safety_message["content"]
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


def test_prompt_marks_completed_event_dialogue_as_background_material() -> None:
    context = {
        "npcIdentity": {"npcId": "Sophia", "displayName": "Sophia"},
        "modSources": ["SVE"],
        "gameState": {"completedEventIds": ["8185290"]},
        "history": [],
        "speechEvidence": [
            {
                "npcId": "Sophia",
                "sourceMod": "SVE",
                "sourceKey": "8185290/f Sophia 1200",
                "eventId": "8185290",
                "evidenceKind": "event_dialogue",
                "text": "我还记得那天的风。",
            }
        ],
    }

    messages = PromptBuilder().build(context, "你还记得那天吗？")
    speech = next(message for message in messages if message["name"] == "speech_evidence")

    assert "event_dialogue" in speech["content"]
    assert "已完成事件" in speech["content"]
    assert "背景素材" in speech["content"]


def test_natural_topic_keeps_completed_event_background_card_when_style_cards_are_light() -> None:
    context = {
        "npcIdentity": {"npcId": "Alex", "displayName": "Alex"},
        "modSources": ["SVE"],
        "gameState": {"completedEventIds": ["1000001"]},
        "history": [{"role": "user", "content": "你刚才提到铁路。"}],
        "interaction": {"intent": "topic", "channel": "remote"},
        "qualityContext": {"naturalMode": True},
        "speechEvidence": [
            {
                "sourceMod": "SVE",
                "sourceKey": "1000001/f Alex 1750",
                "eventId": "1000001",
                "evidenceKind": "event_dialogue",
                "text": "还记得这个地方的入口被封锁的时候吗？",
            }
        ],
    }

    messages = PromptBuilder().build(context, "", compact=False)
    names = [message["name"] for message in messages]

    assert "completed_event_background" in names


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


@pytest.mark.parametrize(
    ("stage", "expected_required"),
    [("friend", "optional"), ("close", "usually"), ("dating", "usually"), ("married", "usually")],
)
def test_high_stage_chat_prompt_includes_conversation_lead_contract(
    stage: str,
    expected_required: str,
) -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stageProfile": {"stage": stage},
            "stagePolicy": build_stage_policy("Alex", stage),
        },
        "gameState": {"relationshipStage": stage, "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "今天训练得怎么样？")
    lead = next(message for message in messages if message["name"] == "conversation_lead")
    payload = json.loads(lead["content"])

    assert payload["conversationLead"]["required"] == expected_required
    assert "specific_follow_up" in payload["conversationLead"]["allowedKinds"]
    assert payload["conversationLead"]["intent"] == "chat"
    assert payload["conversationLead"]["npcId"] == "Alex"
    assert payload["conversationLead"]["initiativeMode"]
    assert "先回答当前输入" in payload["instruction"]
    assert "你呢" in payload["instruction"]
    if expected_required == "optional":
        assert "可以按话题自然递出" in payload["instruction"]
    else:
        assert "再自然递出" in payload["instruction"]


def test_natural_mode_makes_high_stage_conversation_lead_optional() -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Sebastian",
            "displayName": "Sebastian",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Sebastian", "married"),
        },
        "qualityContext": {"naturalMode": True, "flirtIntensity": "explicit"},
        "gameState": {"relationshipStage": "married", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "我坐你旁边了。手给我？")
    leads = [message for message in messages if message["name"] == "conversation_lead"]
    if leads:
        payload = json.loads(leads[0]["content"])
        assert payload["conversationLead"]["required"] == "optional"
        assert "不要强行同时解释、表达情绪、追问和安排" in payload["instruction"]


def test_natural_detail_turn_does_not_request_a_conversation_lead() -> None:
    """轻承接回合不能被 conversation lead 卡重新写成提问或安排。"""

    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Elliott", "married"),
        },
        "qualityContext": {
            "naturalMode": True,
            "initiativeExpectation": "responsive",
            "initiativeKind": "none",
            "turnPlan": {"mode": "answer_plus_detail", "intensity": "light"},
        },
        "gameState": {"relationshipStage": "married", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "remote"},
        "history": [],
    }

    names = [
        message["name"]
        for message in PromptBuilder().build(context, "那页后来留着吗？")
    ]

    assert "conversation_lead" not in names


@pytest.mark.parametrize(
    ("npc_id", "required_fragments"),
    [
        (
            "Wizard",
            ("不要停在泛泛的‘你想聊什么’", "法师塔、研究记录、符文读数"),
        ),
        (
            "Sophia",
            ("保留玩家点名的核心对象和数量", "酒窖、酒或一杯"),
        ),
        (
            "Sebastian",
            ("只有玩家明确提出拥抱、想抱或抱一下时", "普通靠近、分耳机、听歌或回房间时不强制拥抱"),
        ),
        (
            "Alex",
            ("按玩家的动作方向回应", "保持自信、轻松、行动派"),
        ),
    ],
)
def test_chat_prompt_projects_role_specific_conversation_lead_guidance(
    npc_id: str,
    required_fragments: tuple[str, ...],
) -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": npc_id,
            "displayName": npc_id,
            "stageProfile": {"stage": "dating"},
            "stagePolicy": build_stage_policy(npc_id, "dating"),
        },
        "gameState": {"relationshipStage": "dating", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": [],
    }

    lead = next(
        message
        for message in PromptBuilder().build(context, "你最近怎么样？")
        if message["name"] == "conversation_lead"
    )
    payload = json.loads(lead["content"])

    assert all(
        fragment in payload["conversationLead"]["roleGuidance"]
        for fragment in required_fragments
    )
    assert all(fragment in payload["instruction"] for fragment in required_fragments)


@pytest.mark.parametrize("npc_id", ("Wizard", "Sophia", "Shane", "Sebastian", "Alex"))
def test_high_stage_prompt_projects_one_role_move_instead_of_a_full_script(
    npc_id: str,
) -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    stage_policy = build_stage_policy(npc_id, "dating")
    context = {
        "npcIdentity": {
            "npcId": npc_id,
            "displayName": npc_id,
            "stageProfile": {"stage": "dating"},
            "stagePolicy": stage_policy,
        },
        "gameState": {"relationshipStage": "dating", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "最近怎么样？")
    stage = next(
        message for message in messages if message["name"] == "stage_execution_card"
    )
    lead = next(
        message for message in messages if message["name"] == "conversation_lead"
    )
    stage_text = stage["content"]
    lead_text = lead["content"]
    fingerprint = stage_policy["voiceFingerprint"]

    assert "直接回答后最多追加一个角色化动作" in stage_text
    assert "不要强行同时解释、表达情绪、追问和安排" in stage_text
    assert fingerprint in stage_text
    assert "直接回答后最多追加一个角色化动作" in lead_text
    assert "不要强行同时解释、表达情绪、追问和安排" in lead_text
    assert fingerprint in lead_text


def test_compact_sebastian_chat_prompt_keeps_hug_boundary_and_variation_rule() -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Sebastian",
            "displayName": "Sebastian",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Sebastian", "married"),
        },
        "gameState": {"relationshipStage": "married", "friendshipHearts": 14},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "qualityContext": {
            "flirtIntensity": "direct",
            "romanceEligible": True,
            "adultConsensual": True,
        },
        "history": [],
    }

    messages = PromptBuilder().build(
        context,
        "别笑，我就是想让你靠近一点，听清楚这首。",
        compact=True,
    )
    lead = json.loads(
        next(message for message in messages if message["name"] == "conversation_lead")[
            "content"
        ]
    )
    stage = json.loads(
        next(message for message in messages if message["name"] == "stage_execution_card")[
            "content"
        ]
    )
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "只有玩家明确提出拥抱、想抱或抱一下时" in lead["conversationLead"]["roleGuidance"]
    assert "普通靠近、分耳机、听歌或回房间时不强制拥抱" in stage["conversationLead"]["roleGuidance"]
    assert "最近一轮已经出现拥抱时" in rendered
    assert "回复必须直接出现‘抱、抱一下、抱住、抱着’中的一种" not in rendered


def test_high_affection_prompt_projects_pacing_contract_in_full_and_compact_forms() -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Wizard", "married"),
        },
        "gameState": {"relationshipStage": "married", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": [],
    }

    for compact in (False, True):
        messages = PromptBuilder().build(
            context,
            "记录先放一放，过来坐一会儿。",
            compact=compact,
        )
        affection = json.loads(
            next(
                message
                for message in messages
                if message["name"] == "affection_initiative"
            )["content"]
        )
        assert affection["affectionInitiative"]["pacing"]["maxStrongSignals"] == 1
        assert "当前话题" in affection["instruction"]
        assert "强专属" in affection["instruction"]
        assert "玩家明确索要" in affection["instruction"]


def _wizard_married_prompt_context(history: list[dict[str, str]]) -> dict[str, object]:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    return {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Wizard", "married"),
        },
        "gameState": {"relationshipStage": "married", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": history,
    }


def test_prompt_marks_strong_affection_cooldown_after_recent_strong_replies() -> None:
    context = _wizard_married_prompt_context(
        [
            {"role": "user", "content": "记录先放一放。"},
            {"role": "assistant", "content": "从来只有你，能让我合上记录。"},
            {"role": "user", "content": "那就陪我坐一会儿。"},
            {"role": "assistant", "content": "今晚的时间都留给你。"},
        ]
    )

    messages = PromptBuilder().build(context, "炉火还暖着，我们坐近一点。")
    affection = json.loads(
        next(message for message in messages if message["name"] == "affection_initiative")[
            "content"
        ]
    )

    assert affection["affectionInitiative"]["pacing"]["recentStrongCount"] == 2
    assert "本轮不要再使用强专属情话" in affection["instruction"]
    assert "当前话题、具体照顾或共同小行动" in affection["instruction"]


def test_prompt_allows_one_strong_expression_when_player_explicitly_requests_love_words() -> None:
    context = _wizard_married_prompt_context([])
    messages = PromptBuilder().build(
        context,
        "别只安排事情，直接说一句你最想对我说的情话。",
    )
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "玩家明确索要" in rendered
    assert "本轮可单次升档" in rendered
    assert "下一轮回到具体话题或轻微温度" in rendered


def test_final_affection_check_no_longer_requires_strong_personal_reason_every_round() -> None:
    context = _wizard_married_prompt_context([])
    messages = PromptBuilder().build(context, "把茶端过来，我们看看今晚的记录。")
    final = next(message for message in messages if message["name"] == "affection_priority_final")

    assert "优先接住当前话题" in final["content"]
    assert "不要求每轮使用强专属情话" in final["content"]
    assert "因为是你" not in final["content"]


def test_topic_response_contract_uses_turn_plan_before_high_affection_defaults() -> None:
    context = _wizard_married_prompt_context([])
    context["interaction"] = {"intent": "topic", "channel": "face_to_face"}
    context["qualityContext"] = {
        "flirtIntensity": "direct",
        "romanceEligible": True,
        "adultConsensual": True,
    }

    messages = PromptBuilder().build(context, "")
    topic = json.loads(
        next(message for message in messages if message["name"] == "topic_response_contract")[
            "content"
        ]
    )

    assert "具体且可以继续聊下去" in topic["instruction"]
    assert "让爱意在自然位置尽早出现" not in topic["instruction"]
    assert "首轮必须出现至少一处可感知的爱意" not in topic["instruction"]


def test_topic_response_contract_does_not_force_affection_for_none_initiative_turn() -> None:
    context = _wizard_married_prompt_context([])
    context["interaction"] = {"intent": "topic", "channel": "face_to_face"}
    context["qualityContext"] = {
        "initiativeExpectation": "none",
        "initiativeKind": "none",
        "topicSeed": "嫉妒后的边界",
        "topicKeywords": ["边界", "不安"],
        "flirtIntensity": "direct",
        "romanceEligible": True,
        "adultConsensual": True,
    }

    messages = PromptBuilder().build(context, "")
    topic = json.loads(
        next(message for message in messages if message["name"] == "topic_response_contract")[
            "content"
        ]
    )

    assert topic["topicSeed"] == "嫉妒后的边界"
    assert "具体且可以继续聊下去" in topic["instruction"]
    assert "让爱意在自然位置尽早出现" not in topic["instruction"]
    assert "首轮必须出现至少一处可感知的爱意" not in topic["instruction"]


def test_topic_response_contract_none_turn_without_pacing_still_avoids_strong_affection() -> None:
    context = _wizard_married_prompt_context([])
    context["npcIdentity"]["stagePolicy"]["affectionInitiative"].pop("pacing", None)
    context["interaction"] = {"intent": "topic", "channel": "face_to_face"}
    context["qualityContext"] = {
        "initiativeExpectation": "none",
        "initiativeKind": "none",
        "topicSeed": "研究记录",
        "flirtIntensity": "direct",
        "romanceEligible": True,
        "adultConsensual": True,
    }

    messages = PromptBuilder().build(context, "")
    topic = json.loads(
        next(message for message in messages if message["name"] == "topic_response_contract")[
            "content"
        ]
    )

    assert "首轮必须出现至少一处可感知的爱意" not in topic["instruction"]
    assert "至少把安排和对玩家的爱意" not in topic["instruction"]


@pytest.mark.parametrize("stage", ["stranger", "acquaintance"])
def test_early_stage_chat_prompt_does_not_force_conversation_lead(stage: str) -> None:
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stageProfile": {"stage": stage},
        },
        "gameState": {"relationshipStage": stage},
        "interaction": {"intent": "chat", "channel": "remote"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "最近怎么样？")

    assert not any(message["name"] == "conversation_lead" for message in messages)


def test_topic_prompt_keeps_topic_contract_without_chat_lead_contract() -> None:
    context = {
        "npcIdentity": {"npcId": "Alex", "displayName": "Alex"},
        "gameState": {"relationshipStage": "married"},
        "interaction": {"intent": "topic", "channel": "remote"},
        "qualityContext": {"topicSeed": "训练", "topicKeywords": ["训练"]},
        "history": [],
    }

    messages = PromptBuilder().build(context, "内部触发不应进入消息")
    names = [message["name"] for message in messages]

    assert "topic_response_contract" in names
    assert "conversation_lead" not in names
    assert messages[-1] == {"role": "user", "name": "topic_trigger", "content": ""}


def test_item_prompt_does_not_project_the_chat_conversation_lead_contract() -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stageProfile": {"stage": "dating"},
            "stagePolicy": build_stage_policy("Alex", "dating"),
        },
        "gameState": {"relationshipStage": "dating", "friendshipHearts": 10},
        "interaction": {"intent": "item", "channel": "face_to_face"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "我带了训练饮料给你。")

    assert not any(message["name"] == "conversation_lead" for message in messages)


def test_item_prompt_treats_consumption_as_game_state_not_automatic_eating() -> None:
    context = {
        "npcIdentity": {"npcId": "Dwarf", "displayName": "Dwarf"},
        "gameState": {"relationshipStage": "friend", "friendshipHearts": 4},
        "interaction": {
            "intent": "item",
            "itemContext": {
                "itemId": "(O)80",
                "displayName": "石英",
                "category": "矿石",
                "quality": 0,
                "action": "share",
                "giftTaste": 2,
                "itemKind": "mineral",
                "consumesItem": True,
                "friendshipAwarded": 5,
                "specialInteraction": "mineral_tasting",
            },
        },
        "history": [],
    }

    messages = PromptBuilder().build(context, "和你分享这个石英。")
    interaction = next(message for message in messages if message["name"] == "interaction")
    content = interaction["content"]

    assert '"itemKind": "mineral"' in content
    assert '"consumesItem": true' in content
    assert '"friendshipAwarded": 5' in content
    assert "不等于一定要吃" in content
    assert "不能修改背包或好感度" in content


def test_prompt_history_does_not_project_an_invalid_prior_conversation_lead() -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "stagePolicy": build_stage_policy("Sophia", "dating"),
        },
        "gameState": {"relationshipStage": "dating", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "remote"},
        "history": [
            {"role": "user", "content": "葡萄酒稳定了吗？"},
            {"role": "assistant", "content": "酒窖里有两种香气，你想先听哪一种？"},
        ],
    }

    messages = PromptBuilder().build(context, "那酒现在到底稳定了吗？")
    lead = next(message for message in messages if message["name"] == "conversation_lead")
    payload = json.loads(lead["content"])

    assert "previousKind" not in payload["conversationLead"]
    assert "previousOpening" not in payload["conversationLead"]


def test_chat_prompt_projects_previous_conversation_lead_from_history() -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "stagePolicy": build_stage_policy("Sophia", "dating"),
        },
        "gameState": {"relationshipStage": "dating", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "remote"},
        "history": [
            {
                "role": "user",
                "content": "葡萄酒稳定了吗？",
                "intent": "chat",
                "relationshipStage": "dating",
            },
            {
                "role": "assistant",
                "content": "葡萄酒稳定了。你想先听哪一种香气？",
                "intent": "chat",
                "relationshipStage": "dating",
            },
        ],
    }

    messages = PromptBuilder().build(context, "那就说说香气吧。")
    lead = next(message for message in messages if message["name"] == "conversation_lead")
    payload = json.loads(lead["content"])

    assert payload["conversationLead"]["previousKind"] == "choice_prompt"
    assert payload["conversationLead"]["previousOpening"] == "葡萄酒稳定了"
    assert payload["conversationLead"]["previousAnchor"] == "葡萄酒"


def test_chat_prompt_projects_relationship_stage_progress_for_lead_variation() -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "stagePolicy": build_stage_policy("Sophia", "dating"),
        },
        "gameState": {"relationshipStage": "dating", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "remote"},
        "history": [
            {
                "role": "user",
                "content": "葡萄酒稳定了吗？",
                "intent": "chat",
                "relationshipStage": "close",
            },
            {
                "role": "assistant",
                "content": "葡萄酒稳定了。你想先听哪一种香气？",
                "intent": "chat",
                "relationshipStage": "close",
            },
        ],
    }

    messages = PromptBuilder().build(context, "那就说说香气吧。")
    lead = next(message for message in messages if message["name"] == "conversation_lead")
    history = [message for message in messages if message["name"] == "conversation_history"]
    payload = json.loads(lead["content"])

    assert payload["conversationLead"]["relationshipStage"] == "dating"
    assert payload["conversationLead"]["previousRelationshipStage"] == "close"
    assert all(set(message) == {"role", "name", "content"} for message in history)


@pytest.mark.parametrize(
    ("history_intent", "history_stage"),
    [
        ("topic", "married"),
        ("item", "married"),
        ("chat", "acquaintance"),
    ],
)
def test_context_history_does_not_seed_chat_lead_from_non_chat_or_low_stage_turn(
    history_intent: str,
    history_stage: str,
) -> None:
    context = ContextBuilder().build({
        "npcId": "Sophia",
        "relationshipStage": "dating",
        "friendshipHearts": 10,
        "intent": "chat",
        "channel": "remote",
        "history": [
            {
                "role": "user",
                "content": "葡萄酒稳定了吗？",
                "intent": history_intent,
                "relationshipStage": history_stage,
            },
            {
                "role": "assistant",
                "content": "葡萄酒稳定了。你想先听哪一种香气？",
                "intent": history_intent,
                "relationshipStage": history_stage,
            },
        ],
    })

    messages = PromptBuilder().build(context, "那就说说香气吧。")
    lead = next(message for message in messages if message["name"] == "conversation_lead")
    payload = json.loads(lead["content"])

    assert "previousKind" not in payload["conversationLead"]
    assert "previousOpening" not in payload["conversationLead"]


def test_context_history_without_provenance_keeps_context_but_does_not_seed_chat_lead() -> None:
    context = ContextBuilder().build({
        "npcId": "Sophia",
        "relationshipStage": "dating",
        "friendshipHearts": 10,
        "intent": "chat",
        "channel": "remote",
        "history": [
            {"role": "user", "content": "葡萄酒稳定了吗？"},
            {
                "role": "assistant",
                "content": "葡萄酒稳定了。你想先听哪一种香气？",
            },
        ],
    })

    messages = PromptBuilder().build(context, "那就说说香气吧。")
    history = [message for message in messages if message["name"] == "conversation_history"]
    lead = next(message for message in messages if message["name"] == "conversation_lead")
    payload = json.loads(lead["content"])

    assert [message["content"] for message in history] == [
        "葡萄酒稳定了吗？",
        "葡萄酒稳定了。你想先听哪一种香气？",
    ]
    assert "previousKind" not in payload["conversationLead"]
    assert "previousOpening" not in payload["conversationLead"]


@pytest.mark.parametrize(
    ("history_intent", "history_stage"),
    [
        ("topic", "married"),
        ("item", "married"),
        ("chat", "acquaintance"),
    ],
)
def test_chat_lead_skips_nonparticipating_history_and_keeps_prior_valid_lead(
    history_intent: str,
    history_stage: str,
) -> None:
    context = ContextBuilder().build({
        "npcId": "Sophia",
        "relationshipStage": "dating",
        "friendshipHearts": 10,
        "intent": "chat",
        "channel": "remote",
        "history": [
            {
                "role": "user",
                "content": "葡萄酒稳定了吗？",
                "intent": "chat",
                "relationshipStage": "dating",
            },
            {
                "role": "assistant",
                "content": "葡萄酒稳定了。你想先听哪一种香气？",
                "intent": "chat",
                "relationshipStage": "dating",
            },
            {
                "role": "user",
                "content": "顺便说说别的事。",
                "intent": history_intent,
                "relationshipStage": history_stage,
            },
            {
                "role": "assistant",
                "content": "这件事我已经记下了。",
                "intent": history_intent,
                "relationshipStage": history_stage,
            },
        ],
    })

    messages = PromptBuilder().build(context, "那就说说香气吧。")
    lead = next(message for message in messages if message["name"] == "conversation_lead")
    payload = json.loads(lead["content"])

    assert payload["conversationLead"]["previousKind"] == "choice_prompt"
    assert payload["conversationLead"]["previousOpening"] == "葡萄酒稳定了"
    assert payload["conversationLead"]["previousAnchor"] == "葡萄酒"


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


def test_natural_mode_treats_required_terms_as_soft_topic_hints() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
        },
        "qualityContext": {"naturalMode": True, "flirtIntensity": "direct"},
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
    rendered = json.dumps(messages, ensure_ascii=False)
    quality = json.loads(
        next(message for message in messages if message["name"] == "quality_context")[
            "content"
        ]
    )
    anchor = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "current_topic_anchor"
        )["content"]
    )
    contract = json.loads(
        next(message for message in messages if message["name"] == "reply_contract")[
            "content"
        ]
    )

    assert "naturalMode" not in quality
    assert "styleCalibration" not in quality
    assert "turnPlan" not in quality
    assert anchor["requiredTerms"] == ["酒", "味道"]
    assert "requiredTerms 只作软提示" in anchor["instruction"]
    assert "必须原样使用 requiredTerms" not in anchor["instruction"]
    assert contract["topicHints"] == ["酒", "味道"]
    assert "mustMention" not in contract
    assert "不要求逐字命中" in contract["instruction"]
    natural_contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )
    assert "每轮最多推进一层" in natural_contract["content"]
    assert "requiredTerms 只是话题软提示" in natural_contract["content"]
    assert "不自动安排下一步" in natural_contract["content"]
    assert "回复必须原样包含" not in rendered


def test_natural_topic_contract_prefers_colloquial_speech_over_literary_flourish() -> None:
    """找话题的自然模式应压低散文、情诗和古风腔，而不是只放宽关键词。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {"naturalMode": True, "flirtIntensity": "direct"},
        "modSources": ["SVE"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
    }

    messages = PromptBuilder().build(context, "酒窖里今天还顺利吗？")
    natural_contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )
    content = natural_contract["content"]

    assert "自然口语" in content
    assert "散文" in content
    assert "比喻只在角色或当前话题本来需要时使用" in content
    assert "不自动安排下一步" in content


def test_natural_contract_allows_one_emotion_texture_reaction_without_labeling_it() -> None:
    """自然模式应允许停顿、改口等局部反应，但不把情绪标签变成台词任务。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "tone": "温柔、容易害羞",
                "emotionTexture": ["被戳中时先改口，热情露出后短暂躲开"],
            },
        },
        "qualityContext": {"naturalMode": True, "flirtIntensity": "direct"},
        "modSources": ["SVE"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
    }

    messages = PromptBuilder().build(context, "你再这样看，我就挨过去了。")
    natural_contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )
    content = natural_contract["content"]

    assert "微反应" in content
    assert "改口" in content
    assert "停顿" in content
    assert "情绪标签" in content
    assert any(
        phrase in content
        for phrase in ("不要直接说出情绪标签", "不要把情绪标签说出口")
    )


def test_voice_card_preserves_emotion_texture_for_natural_dialogue() -> None:
    """语气卡压缩时不能丢掉当前角色专属的情绪纹理。"""

    texture = {"reaction": "先嘴硬，再漏出半句关心"}
    context = {
        "npcIdentity": {"npcId": "Shane", "displayName": "Shane"},
        "qualityContext": {"naturalMode": True, "flirtIntensity": "direct"},
        "modSources": ["vanilla", "female-bachelors"],
        "gameState": {},
        "recentFacts": [],
        "history": [],
        "voiceCard": {
            "npcId": "Shane",
            "features": {"dryHumorMarkers": 2},
            "topicHints": ["克制的干燥幽默"],
            "emotionTexture": texture,
        },
    }

    messages = PromptBuilder().build(context, "我没躲。你问一声就行。")
    voice_message = next(
        message for message in messages if message["name"] == "voice_card"
    )
    voice_card = json.loads(voice_message["content"])["voiceCard"]

    assert voice_card["emotionTexture"] == texture


def test_natural_sophia_prompt_keeps_stage_energy_and_two_voice_anchors() -> None:
    """Sophia 的自然轻回合应带阶段能量与一冷一热两条原文锚点。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "tone": "温柔，但喜欢的事会突然说快",
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "emotionRange": ["温和", "害羞", "受压时克制", "信任后热烈"],
                "energyProfile": {
                    "stranger": "先小声确认，惊到时先说半句再道歉",
                    "married": "婚后仍会因喜欢的事突然兴奋，连说两句后自己收回来",
                },
                "emotionTexture": ["先反应，再把兴奋说完整一点"],
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {
                    "sourceKey": "Rain",
                    "voiceEnergy": "low",
                    "text": "今天酒窖里很安静。",
                },
                {
                    "sourceKey": "Good_0",
                    "voiceEnergy": "high",
                    "text": "嘿，小傻瓜！再靠近一点……！！！爱你哟！",
                },
            ],
        },
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    role_message = next(
        message for message in messages if message["name"] == "natural_role_texture"
    )
    payload = json.loads(role_message["content"])

    assert "energyMode" in payload
    assert "兴奋" in payload["energyMode"]
    assert [item["sourceKey"] for item in payload["voiceAnchors"]] == [
        "Rain",
        "Good_0",
    ]
    assert payload["speechParticleHints"][:2] == ["嘿", "哇"]
    assert "emotionRange" in payload
    assert "信任后热烈" in payload["emotionRange"]
    assert "energyTrigger" in payload
    assert "被夸" in payload["energyTrigger"]
    assert any("兴奋展开" in item for item in payload["liveliness"]["behavioralMoves"])
    assert any("即时小动作" in item for item in payload["liveliness"]["behavioralMoves"])
    assert "不是固定句式" in payload["instruction"]


def test_natural_sophia_topic_allows_triggered_reaction_before_fact() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "voiceStyle": {
                "tone": "温柔，但喜欢的事会突然说快",
                "emotionRange": ["温和", "害羞", "受压时克制", "信任后热烈"],
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "dating": "喜欢或被夸时可以先热烈回应，连说两句后害羞地改口",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "topicSeed": "收工时发现一小串葡萄裂开了",
            "topicKeywords": ["葡萄", "收工"],
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {
                    "sourceKey": "Good_4",
                    "voiceEnergy": "high",
                    "text": "耶，葡萄终于变甜了呀！",
                }
            ],
        },
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    topic_message = next(
        message for message in messages if message["name"] == "topic_response_contract"
    )
    topic_text = topic_message["content"]
    assert "先露出一个短反应" in topic_text
    assert "短反应" in topic_text
    assert "answer_only 仍然不追问、邀约或安排" in topic_text


def test_natural_sophia_topic_requires_visible_liveliness_when_topic_matches() -> None:
    """Sophia 的喜欢话题不能把原文里的活泼反应全部降成可选纹理。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "tone": "轻柔，但喜欢的事会突然说快",
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "married": "婚后仍会因喜欢的事突然兴奋，连说两句后自己收回来",
                },
                "livelinessProfile": [
                    "真正兴奋时会明显说快，连续抛出两三个同主题念头",
                    "开心时会把热情直接递给对方，带一点夸张的感叹",
                    "先把喜欢说出来，意识到太直白后才短暂停顿或改口",
                ],
                "emotionTexture": [
                    "喜欢的事先露出反应，再把兴奋说完整",
                ],
                "rhythmProfile": {
                    "opening": "从眼前的感官细节开口",
                    "development": "喜欢的事补一处感受",
                    "closing": "停在当前感受，把选择权留给对方",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only"},
            "topicSeed": "刚画完一小块被夸过的夕阳颜色",
        },
        "interaction": {"intent": "topic", "channel": "face_to_face"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {
                    "sourceKey": "Rain",
                    "voiceEnergy": "low",
                    "text": "今天酒窖里很安静。",
                },
                {
                    "sourceKey": "Good_0",
                    "voiceEnergy": "high",
                    "text": "嘿，小傻瓜！再靠近一点……！！！爱你哟！",
                },
            ],
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    role_payload = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "natural_role_texture"
        )["content"]
    )
    topic_payload = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "natural_topic_role_override"
        )["content"]
    )

    assert "liveliness" in role_payload
    assert "liveliness" in topic_payload
    assert "至少保留一组可见的活泼递送节奏" in topic_payload["instruction"]
    assert any(
        phrase in topic_payload["instruction"]
        for phrase in ("liveliness", "可见信号")
    )
    assert any(
        any(
            phrase in signal
            for phrase in ("短惊呼", "语气颗粒", "说快半句", "连续补一句")
        )
        for signal in topic_payload["liveliness"]["visibleSignals"]
    )
    assert any("行为变化" in move for move in topic_payload["liveliness"]["behavioralMoves"])
    assert any("即时小动作" in move for move in topic_payload["liveliness"]["behavioralMoves"])
    assert topic_payload["liveliness"]["deliveryProfile"]
    assert any("连续抛出" in item for item in topic_payload["liveliness"]["deliveryProfile"])
    assert "安静观察式" in topic_payload["instruction"]
    assert "首轮" in topic_payload["instruction"]
    assert "点明眼前对象" in topic_payload["instruction"]
    assert "不要每轮复用同一个词" in topic_payload["instruction"]


def test_natural_sophia_topic_requires_spoken_impulse_not_polished_observation() -> None:
    """Sophia 的活泼要改变说话的冲动和跳拍，不能只是把景物描写拆开。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "dating": "喜欢或被夸时可以先热烈回应，连说两句后害羞地改口",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "topicSeed": "收工时发现一小串葡萄裂开了",
            "topicKeywords": ["葡萄", "收工"],
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    turn_plan = json.loads(
        next(message for message in messages if message["name"] == "turn_plan")[
            "content"
        ]
    )
    natural_contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )["content"]
    topic_contract = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "topic_response_contract"
        )["content"]
    )
    final = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )

    turn_instruction = turn_plan["instruction"]
    assert "口头冲动" in turn_instruction
    assert "抢着追加" in turn_instruction
    assert "俏皮偏转或自我收回" in turn_instruction
    assert "不是把景物描写拆开" in turn_instruction
    assert "口头冲动三拍" in natural_contract
    assert "不套用普通的一句短答" in natural_contract
    assert "口头冲动三拍" in topic_contract["instruction"]
    assert "不是把景物描写拆开" in final["instruction"]


def test_natural_sophia_contract_does_not_downgrade_liveliness_to_optional() -> None:
    """公共自然契约不能用“可选微反应”覆盖 Sophia 的原文节奏。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "married": "婚后仍会因喜欢的事突然兴奋，连说两句后自己收回来",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "topicSeed": "酒窖里那张标签贴歪了",
            "topicKeywords": ["酒窖", "标签"],
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "face_to_face"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    content = next(
        message["content"]
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )

    assert "不必刻意表现微反应" not in content
    assert "内容需要时可以出现一次微反应" not in content
    assert "Sophia" in content
    assert "活泼" in content


def test_natural_sophia_keeps_original_bubbly_burst_not_one_micro_signal() -> None:
    """喜欢的话题要保留原文的连续兴奋递送，而不是只加一个微反应。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "dating": "喜欢或被夸时可以先热烈回应，连说两句后害羞地改口",
                },
                "livelinessProfile": [
                    "真正兴奋时会明显说快，连续抛出两三个同主题念头",
                    "开心时会把热情直接递给对方，带一点夸张的感叹",
                ],
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "topicSeed": "收工时发现一小串葡萄裂开了",
            "topicKeywords": ["葡萄", "收工"],
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {
                    "sourceKey": "Mon10",
                    "voiceEnergy": "high",
                    "text": "我想找个时间去爬山！我们也可以去野餐！哦！我们还可以牵手。",
                }
            ],
        },
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    natural_contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )["content"]
    role = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "natural_role_texture"
        )["content"]
    )
    final = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )

    assert "连续节拍" in natural_contract
    assert "2到3个短节拍" in natural_contract
    assert "先亮出第一反应，再追加同主题念头" in natural_contract
    assert "bubblyCadence" in role["liveliness"]
    assert "bubblyCadence" in final
    assert "每轮只选一处" not in natural_contract


def test_natural_sophia_continuation_keeps_liveliness_after_history() -> None:
    """有历史时也要把 Sophia 的活泼节奏放在最终生成优先级。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "dating": "喜欢或被夸时可以先热烈回应，连说两句后害羞地改口",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [
            {"role": "user", "content": "你先尝一颗看看。"},
            {"role": "assistant", "content": "嗯，还真甜。"},
        ],
    }

    messages = PromptBuilder().build(context, "那你再尝一颗。")
    names = [message["name"] for message in messages]
    card = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )

    assert names.index("turn_plan") < names.index("sophia_liveliness_final")
    assert names.index("sophia_liveliness_final") < names.index("player_input")
    assert card["requiredVisibleSignal"] is True
    assert "嗯" in card["excludedAsLiveliness"]
    assert "改口" in card["signalFamilies"]
    assert "不要把它变成固定口头禅" in card["instruction"]


def test_natural_sophia_continuation_carries_concrete_liveliness_references() -> None:
    """后续回合不能只剩抽象活泼规则，要保留当前阶段的原文节奏证据。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "married": "婚后仍会因喜欢的事突然兴奋，连说两句后自己收回来",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {
                    "sourceKey": "Good_4",
                    "voiceEnergy": "high",
                    "energySignals": {
                        "excitementMarkers": 1,
                        "exclamationMarkers": 2,
                        "continuationMarkers": 0,
                    },
                    "text": "嘿，小傻瓜！今晚想喝什么年份的蓝月葡萄酒？",
                },
                {
                    "sourceKey": "Good_6",
                    "voiceEnergy": "high",
                    "energySignals": {
                        "excitementMarkers": 0,
                        "exclamationMarkers": 1,
                        "continuationMarkers": 0,
                    },
                    "text": "也许我可以换个颜色？嗯……不，我要让它保持棉花糖粉！",
                },
            ],
        },
        "history": [
            {"role": "user", "content": "那幅画还在吗？"},
            {"role": "assistant", "content": "还在桌上。"},
        ],
    }

    messages = PromptBuilder().build(context, "我去拿。")
    card = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )

    assert [item["text"] for item in card["livelinessExamples"]] == [
        "嘿，小傻瓜！今晚想喝什么年份的蓝月葡萄酒？",
        "也许我可以换个颜色？嗯……不，我要让它保持棉花糖粉！",
    ]
    assert all("只学节奏" in item["instruction"] for item in card["livelinessExamples"])
    assert "先反应，再把当前事实说完整" in card["instruction"]


def test_natural_sophia_keeps_multiple_original_liveliness_shapes_after_history() -> None:
    """有历史时仍保留多种原文活泼结构，不能只剩一个语气词。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "married": "婚后仍会因喜欢的事突然兴奋，连说两句后自己收回来",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {"sourceKey": "Mon10", "voiceEnergy": "high", "text": "我想找个时间去爬山！我们也可以去野餐！哦！我们还可以牵手。"},
                {"sourceKey": "Fri2", "voiceEnergy": "high", "text": "噫！你吓到我了！呃，你好。你想聊聊天吗？抱，抱歉。我……我有点忙。"},
                {"sourceKey": "Good_6", "voiceEnergy": "high", "text": "也许我可以换个颜色？嗯……不，我要让它保持棉花糖粉！"},
                {"sourceKey": "Indoor_Day_2", "voiceEnergy": "high", "text": "耶！你终于起来了！早餐想吃点什么吗？"},
            ],
        },
        "history": [
            {"role": "user", "content": "你先看看这张。"},
            {"role": "assistant", "content": "我看到了。"},
        ],
    }

    messages = PromptBuilder().build(context, "那你觉得呢？")
    role = json.loads(
        next(message for message in messages if message["name"] == "natural_role_texture")[
            "content"
        ]
    )
    final = json.loads(
        next(message for message in messages if message["name"] == "sophia_liveliness_final")[
            "content"
        ]
    )

    assert [item["sourceKey"] for item in role["voiceAnchors"]] == [
        "Mon10",
        "Fri2",
        "Good_6",
        "Indoor_Day_2",
    ]
    assert [item["text"] for item in final["livelinessExamples"]] == [
        "我想找个时间去爬山！我们也可以去野餐！哦！我们还可以牵手。",
        "噫！你吓到我了！呃，你好。你想聊聊天吗？抱，抱歉。我……我有点忙。",
        "也许我可以换个颜色？嗯……不，我要让它保持棉花糖粉！",
        "耶！你终于起来了！早餐想吃点什么吗？",
    ]
    assert final["signalFamilies"][0] == "先短惊呼再补具体信息"
    assert "突然想到新东西后连说一小句" in final["instruction"]


def test_sophia_liveliness_final_keeps_same_traceable_high_energy_batch_first_and_followup() -> None:
    """首轮和续聊的最终活泼卡必须继续指向同一批高能量原文。"""

    anchors = [
        {
            "sourceKey": "Mon10",
            "sourceMod": "FlashShifter.StardewValleyExpandedCP",
            "evidenceKind": "dialogue",
            "voiceEnergy": "high",
            "text": "我想找个时间去爬山！我们也可以去野餐！哦！我们还可以牵手。",
        },
        {
            "sourceKey": "Fri2",
            "sourceMod": "FlashShifter.StardewValleyExpandedCP",
            "evidenceKind": "dialogue",
            "voiceEnergy": "high",
            "text": "噫！你吓到我了！呃，你好。抱，抱歉。我……我有点忙。",
        },
        {
            "sourceKey": "Good_6",
            "sourceMod": "FlashShifter.StardewValleyExpandedCP",
            "evidenceKind": "dialogue",
            "voiceEnergy": "high",
            "text": "也许我可以换个颜色？嗯……不，我要让它保持棉花糖粉！",
        },
        {
            "sourceKey": "Indoor_Day_Sophia",
            "sourceMod": "FlashShifter.StardewValleyExpandedCP",
            "evidenceKind": "marriage_dialogue",
            "voiceEnergy": "high",
            "text": "嘿，小傻瓜！早上好。你睡得好吗？我在想也许我很快就会出演一个新的角色扮演！",
        },
    ]
    base_context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "married": "婚后仍会因喜欢的事突然兴奋，连说两句后自己收回来",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "voiceCard": {"npcId": "Sophia", "voiceAnchors": anchors},
    }

    for history in (
        [],
        [
            {"role": "user", "content": "那幅画还在吗？"},
            {"role": "assistant", "content": "还在桌上。"},
        ],
    ):
        context = {**base_context, "history": history}
        messages = PromptBuilder().build(context, "我去拿。")
        role = json.loads(
            next(
                message
                for message in messages
                if message["name"] == "natural_role_texture"
            )["content"]
        )
        final = json.loads(
            next(
                message
                for message in messages
                if message["name"] == "sophia_liveliness_final"
            )["content"]
        )

        expected_keys = [item["sourceKey"] for item in role["voiceAnchors"]]
        assert expected_keys == [item["sourceKey"] for item in anchors]
        final_keys = [item["sourceKey"] for item in final["livelinessExamples"]]
        assert len(final_keys) == len(expected_keys)
        assert set(final_keys) == set(expected_keys)
        assert all(
            item["voiceEnergy"] == "high" for item in final["livelinessExamples"]
        )


def test_sophia_liveliness_examples_expose_structural_shapes_before_particles() -> None:
    """原文的活泼形状要单独标出，不能让模型只轮换开头语气词。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "married": "婚后仍会因喜欢的事突然兴奋，连说两句后自己收回来",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {"sourceKey": "Mon10", "voiceEnergy": "high", "text": "我想找个时间去爬山！我们也可以去野餐！哦！我们还可以牵手。"},
                {"sourceKey": "Fri2", "voiceEnergy": "high", "text": "噫！你吓到我了！呃，你好。你想聊聊天吗？抱，抱歉。我……我有点忙。"},
                {"sourceKey": "Good_6", "voiceEnergy": "high", "text": "也许我可以换个颜色？嗯……不，我要让它保持棉花糖粉！"},
            ],
        },
        "history": [],
    }

    final = json.loads(
        next(
            message
            for message in PromptBuilder().build(context, "那你觉得呢？")
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )

    shapes = [item["shape"] for item in final["livelinessExamples"]]
    assert len(set(shapes)) >= 3
    assert "连续追加" in shapes
    assert "说到一半改口/收回" in shapes
    assert "语气词只能附着在结构上" in final["instruction"]
    assert "不要用‘嘿’‘哇’‘哦哦哦’单独撑起活泼" in final["instruction"]


def test_sophia_liveliness_requires_behavioral_moves_beyond_particles() -> None:
    """活泼必须改变回应动作，不能只在句首替换语气词。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "married": "婚后仍会因喜欢的事突然兴奋，连说两句后自己收回来",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {
                    "sourceKey": "Indoor_Day_2",
                    "voiceEnergy": "high",
                    "text": "耶！你终于起来了！早餐想吃点什么吗？",
                },
                {
                    "sourceKey": "Good_6",
                    "voiceEnergy": "high",
                    "text": "也许我可以换个颜色？嗯……不，我要让它保持棉花糖粉！",
                },
                {
                    "sourceKey": "Mon10",
                    "voiceEnergy": "high",
                    "text": "我想找个时间去爬山！我们也可以去野餐！哦！我们还可以牵手。",
                },
            ],
        },
        "history": [],
    }

    final = json.loads(
        next(
            message
            for message in PromptBuilder().build(context, "我看到了。")
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )

    assert "behavioralMoves" in final
    assert any("兴奋展开" in move for move in final["behavioralMoves"])
    assert any("即时小动作" in move for move in final["behavioralMoves"])
    assert all(item.get("behavioralMove") for item in final["livelinessExamples"])
    assert "行为变化" in final["instruction"]


def test_sophia_liveliness_keeps_bubbly_source_delivery_not_only_actions() -> None:
    """Sophia 的活泼还要保留原文的明亮、连冲和害羞回收。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "married": "婚后仍会因喜欢的事突然兴奋，连说两句后自己收回来",
                },
                "livelinessProfile": [
                    "真正兴奋时会明显说快，连续抛出两三个同主题念头",
                    "开心时会把热情直接递给对方，带一点夸张的感叹",
                    "先把喜欢说出来，意识到太直白后才短暂停顿或改口",
                ],
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {
                    "sourceKey": "Mon10",
                    "voiceEnergy": "high",
                    "text": "我想找个时间去爬山！我们也可以去野餐！哦！我们还可以牵手。",
                }
            ],
        },
        "history": [],
    }

    messages = PromptBuilder().build(context, "我也觉得不错。")
    role = json.loads(
        next(message for message in messages if message["name"] == "natural_role_texture")[
            "content"
        ]
    )
    final = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )

    assert role["liveliness"]["deliveryProfile"]
    assert any("连续抛出" in item for item in role["liveliness"]["deliveryProfile"])
    assert any("害羞" in item or "改口" in item for item in role["liveliness"]["deliveryProfile"])
    assert final["deliveryProfile"]
    assert any("连续抛出" in item for item in final["deliveryProfile"])
    assert any("递给对方" in item for item in final["deliveryProfile"])
    assert "明亮" in final["instruction"]
    assert "安静观察式" in final["instruction"]


def test_sophia_liveliness_requires_independent_short_sentence_burst() -> None:
    """喜欢的话题要恢复原文的短句连冲，不能只生成一个长句加微反应。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "dating": "喜欢或被夸时可以先热烈回应，连说两句后害羞地改口",
                },
                "livelinessProfile": [
                    "真正兴奋时会明显说快，连续抛出两三个同主题念头",
                    "开心时会把热情直接递给对方，带一点夸张的感叹",
                ],
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {
                    "sourceKey": "Mon10",
                    "voiceEnergy": "high",
                    "text": "我想找个时间去爬山！我们也可以去野餐！哦！我们还可以牵手。",
                },
                {
                    "sourceKey": "Good_6",
                    "voiceEnergy": "high",
                    "text": "也许我可以换个颜色？嗯……不，我要让它保持棉花糖粉！",
                },
            ],
        },
        "history": [
            {"role": "user", "content": "那你再说说。"},
            {"role": "assistant", "content": "嗯，还在看。"},
        ],
    }

    messages = PromptBuilder().build(context, "我也想听。")
    final = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )
    original_examples = [
        message["content"]
        for message in messages
        if message["name"] == "original_style_example_assistant"
    ]

    assert "independentShortSentenceBurst" in final
    assert final["independentShortSentenceBurst"]["minimumSentences"] >= 2
    assert "句号或感叹号" in final["instruction"]
    assert "不要用破折号把整段串成一个长句" in final["instruction"]
    assert any("爬山" in example for example in original_examples)


def test_sophia_liveliness_keeps_playful_spill_not_polished_narration() -> None:
    """活泼要有突然蹦出、俏皮偏转和收回，不能只把散文拆成几句。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "dating": "喜欢或被夸时可以先热烈回应，连说两句后害羞地改口",
                },
                "livelinessProfile": [
                    "真正兴奋时会明显说快，连续抛出两三个同主题念头",
                ],
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {
                    "sourceKey": "Mon10",
                    "voiceEnergy": "high",
                    "text": "我想找个时间去爬山！我们也可以去野餐！哦！我们还可以牵手。",
                },
            ],
        },
        "history": [],
    }

    final = json.loads(
        next(
            message
            for message in PromptBuilder().build(context, "我也觉得不错。")
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )

    spark = final["playfulSpark"]
    assert spark["minimumBeats"] >= 2
    assert any("突然想到" in item for item in spark["moves"])
    assert any("俏皮" in item or "夸张" in item for item in spark["moves"])
    assert any("工整说明长句" in item for item in spark["deliveryRules"])
    assert "不要把活泼翻译成温柔说明" in final["instruction"]
    assert "直呼玩家" in final["instruction"]


def test_sophia_adaptive_examples_keep_impulse_and_self_correction_shapes() -> None:
    """adaptive 的少量原文 few-shot 不能被普通问候挤掉。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "dating": "喜欢或被夸时可以先热烈回应，连说两句后害羞地改口",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {
                    "sourceKey": "Mon8",
                    "voiceEnergy": "high",
                    "text": "嘿，你好。很高兴见到你！",
                },
                {
                    "sourceKey": "Mon10",
                    "voiceEnergy": "high",
                    "text": "我想找个时间去爬山！我们也可以去野餐！哦！我们还可以牵手。",
                },
                {
                    "sourceKey": "Good_6",
                    "voiceEnergy": "high",
                    "text": "也许我可以换个颜色？嗯……不，我要让它保持棉花糖粉！",
                },
                {
                    "sourceKey": "Sun8",
                    "voiceEnergy": "high",
                    "text": "嘿！祝你拥有高效的一天？",
                },
            ],
        },
        "history": [],
    }

    messages = PromptBuilder().build(context, "我也想听。")
    examples = [
        message["content"]
        for message in messages
        if message["name"] == "original_style_example_assistant"
    ]

    assert len(examples) == 2
    assert any("爬山" in example for example in examples)
    assert any("棉花糖粉" in example for example in examples)


def test_sophia_liveliness_starts_from_subjective_impulse_not_scenery_report() -> None:
    """喜欢的话题要先露出她自己的冲动，再补对象和新念头。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "dating": "喜欢或被夸时可以先热烈回应，连说两句后害羞地改口",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "topicSeed": "刚发现一串葡萄裂开了",
            "topicKeywords": ["葡萄"],
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    turn_plan = json.loads(
        next(message for message in messages if message["name"] == "turn_plan")[
            "content"
        ]
    )
    final = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )

    assert "主观冲动" in turn_plan["instruction"]
    assert "先说她此刻的反应" in final["instruction"]
    assert "不要先做客观景物报告" in final["instruction"]


def test_sophia_liveliness_prioritizes_colloquial_interaction_over_scene_prose() -> None:
    """Sophia 的活泼应先改变她和玩家说话的方式，而不是增加景物描写。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "married": "婚后仍会因喜欢的事突然兴奋，连说两句后自己收回来",
                },
                "livelinessProfile": [
                    "真正兴奋时会明显说快，连续抛出两三个同主题念头",
                    "开心时会把热情直接递给对方，带一点夸张的感叹",
                ],
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "topicSeed": "刚发现一串葡萄裂开了",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "face_to_face"},
        "voiceCard": {
            "npcId": "Sophia",
            "voiceAnchors": [
                {
                    "sourceKey": "Mon10",
                    "voiceEnergy": "high",
                    "text": "我想找个时间去爬山！我们也可以去野餐！哦！我们还可以牵手。",
                },
            ],
        },
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    final = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )

    delivery = final["colloquialDelivery"]
    assert delivery["priority"] == "口头互动优先"
    assert delivery["targetSentences"] == "2到3个短句"
    assert delivery["maxSensoryDetails"] == 1
    assert any("递给玩家" in item for item in delivery["mustShowOneOf"])
    assert any("突然改口" in item for item in delivery["mustShowOneOf"])
    assert any("不要先交代背景" in item for item in delivery["avoid"])
    assert any("不要连续描写" in item for item in delivery["avoid"])
    assert "口语互动" in final["instruction"]


def test_sophia_liveliness_has_spoken_intent_gate_against_process_explanation() -> None:
    """活泼不能只把景物和处理步骤说完整，必须留下口头意图。"""

    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "dating"},
            "voiceStyle": {
                "speechParticleHints": ["嘿", "哇", "哦哦哦"],
                "energyProfile": {
                    "dating": "喜欢的事会先兴奋地说出来，想到新东西就抢着补一句",
                },
                "livelinessProfile": [
                    "真正兴奋时会明显说快，连续抛出同主题念头",
                ],
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "topicSeed": "收工时发现一串葡萄裂开了",
            "topicKeywords": ["葡萄", "收工"],
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    final = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )

    gate = final["spokenIntentGate"]
    assert gate["required"] is True
    assert any("个人冲动" in item or "玩家" in item for item in gate["qualifyingMoves"])
    assert any("处理流程" in item or "原因和结果" in item for item in gate["doesNotQualify"])
    assert "说到够像当面接话就停" in gate["stopRule"]


def _sophia_endearment_final_card(
    relationship_stage: str,
    *,
    history: list[dict[str, str]] | None = None,
    player_input: str = "",
    intent: str = "topic",
) -> dict[str, object]:
    context = ContextBuilder().build(
        {
            "npcId": "Sophia",
            "sourceMods": ["SVE"],
            "relationshipStage": relationship_stage,
            "qualityContext": {
                "naturalMode": True,
                "turnPlan": {"mode": "answer_only"},
            },
            "intent": intent,
            "channel": "remote",
            "history": history or [],
        }
    )
    messages = PromptBuilder().build(context, player_input)
    return json.loads(
        next(
            message
            for message in messages
            if message["name"] == "sophia_liveliness_final"
        )["content"]
    )


@pytest.mark.parametrize(
    ("relationship_stage", "expected_terms"),
    [
        ("dating", ["小傻瓜"]),
        ("married", ["小傻瓜", "亲爱的"]),
    ],
)
def test_sophia_intimate_stages_expose_optional_fixed_endearment_policy(
    relationship_stage: str,
    expected_terms: list[str],
) -> None:
    card = _sophia_endearment_final_card(relationship_stage)

    policy = card["endearmentPolicy"]
    assert policy["terms"] == expected_terms
    assert policy["required"] is False
    assert "低频" in policy["cadence"]
    assert "不是每轮必用" in card["instruction"]
    assert "明确命中适用场景时优先选一个候选" in policy["instruction"]
    assert "同一回复里叠加多个爱称" in policy["instruction"]


@pytest.mark.parametrize("relationship_stage", ["acquaintance", "friend"])
def test_sophia_non_intimate_stages_do_not_expose_romantic_endearments(
    relationship_stage: str,
) -> None:
    card = _sophia_endearment_final_card(relationship_stage)

    assert "endearmentPolicy" not in card
    assert "小傻瓜" not in json.dumps(card, ensure_ascii=False)


def test_sophia_endearment_policy_suppresses_a_recently_used_term() -> None:
    card = _sophia_endearment_final_card(
        "married",
        history=[
            {"role": "user", "content": "你今天看起来很开心。"},
            {"role": "assistant", "content": "嘿，小傻瓜，我只是刚想到一件好玩的事。"},
        ],
    )

    policy = card["endearmentPolicy"]
    assert policy["recentlyUsedTerms"] == ["小傻瓜"]
    assert "本轮不要重复" in policy["instruction"]
    assert "尚未用过的其他候选" in policy["instruction"]


def test_sophia_endearment_policy_marks_a_clear_affection_trigger_only() -> None:
    triggered = _sophia_endearment_final_card(
        "married",
        player_input="你特意把我喜欢的颜色留在画里，我很喜欢，给我看看嘛。",
        intent="chat",
    )
    triggered_policy = triggered["endearmentPolicy"]
    assert triggered_policy["preferredThisTurn"] == "小傻瓜"
    assert "本轮玩家明确回应亲密时必须自然使用 preferredThisTurn 一次" in triggered_policy[
        "instruction"
    ]

    ordinary = _sophia_endearment_final_card(
        "married",
        player_input="酒窖那张标签贴歪了，我先把它摆正。",
        intent="chat",
    )
    assert "preferredThisTurn" not in ordinary["endearmentPolicy"]


def test_sophia_endearment_policy_marks_warm_playful_response_as_optional_candidate() -> None:
    card = _sophia_endearment_final_card(
        "married",
        player_input="留着就留着呗，我又没笑你。",
        intent="chat",
    )

    policy = card["endearmentPolicy"]
    assert policy["candidateThisTurn"] == "小傻瓜"
    assert "preferredThisTurn" not in policy
    assert "语气自然时可以使用 candidateThisTurn 一次" in policy["instruction"]


def test_sophia_endearment_policy_also_reaches_the_regular_persona_prompt() -> None:
    context = ContextBuilder().build(
        {
            "npcId": "Sophia",
            "sourceMods": ["SVE"],
            "relationshipStage": "married",
        }
    )
    messages = PromptBuilder().build(context, "今天还好吗？")
    persona = json.loads(
        next(message for message in messages if message["name"] == "persona_core")[
            "content"
        ]
    )

    policy = persona["npcIdentity"]["stageProfile"]["endearmentPolicy"]
    assert policy["terms"] == ["小傻瓜", "亲爱的"]
    assert "endearmentPolicy" not in json.dumps(
        PromptBuilder().build(
            ContextBuilder().build(
                {
                    "npcId": "Sophia",
                    "sourceMods": ["SVE"],
                    "relationshipStage": "friend",
                }
            ),
            "今天还好吗？",
        ),
        ensure_ascii=False,
    )


def test_natural_non_sophia_topic_does_not_inherit_sophia_liveliness_contract() -> None:
    """Sophia 的活泼要求不能变成所有角色的公共格式。"""

    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "rhythmProfile": {
                    "opening": "先给一个判断",
                    "development": "补一条事实",
                    "closing": "用边界收住",
                }
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only"},
            "topicSeed": "塔灯今天亮得很稳",
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    payload = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "natural_topic_role_override"
        )["content"]
    )

    assert "liveliness" not in payload
    assert "至少保留一处可见的活泼反应" not in payload["instruction"]


def test_natural_non_sophia_prompt_does_not_inherit_sophia_energy_fields() -> None:
    """Sophia 的阶段能量证据不能泄漏到其他角色。"""

    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {"tone": "短促、疲惫"},
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "voiceCard": {
            "npcId": "Shane",
            "voiceAnchors": [
                {"sourceKey": "Mon", "text": "今天也就这样。"},
            ],
        },
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    role_message = next(
        message for message in messages if message["name"] == "natural_role_texture"
    )
    payload = json.loads(role_message["content"])

    assert "energyMode" not in payload
    assert "speechParticleHints" not in payload
    assert "Good_0" not in json.dumps(payload, ensure_ascii=False)


def test_default_context_without_emotion_texture_keeps_legacy_prompt_contract() -> None:
    """没有纹理的普通角色不应被默认注入自然模式或新的情绪字段。"""

    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        "Caroline",
        source_mods=["vanilla"],
        friendshipHearts=4,
    )
    messages = PromptBuilder().build(context, "今天过得怎么样？")
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "emotionTexture" not in context["npcIdentity"].get("voiceStyle", {})
    assert "emotionTexture" not in rendered
    assert not any(
        message["name"] == "natural_dialogue_contract" for message in messages
    )


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
    # turn_plan 是新增的单回合契约，允许少量固定开销；字段裁剪仍由上面的
    # voice/knowledge 断言保证，避免用旧的整段字符串阈值锁死消息结构。
    assert len(rendered) < 4300


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
        "final_role_voice_contract",
        "player_echo_guard",
        "turn_plan",
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
    # openers 兜底只认可真正的语气叹词：这里的「嘿」「哦」会被切成颗粒，
    # 而「当然」这类实义短语不再当作语气颗粒（见 _speech_particle_hints）。
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "voiceStyle": {
                "tone": "外向、爱炫耀一点",
                "openers": ["嘿，怎么了？", "哦，嘿。"],
            },
        },
        "modSources": ["vanilla"],
        "gameState": {},
        "history": [
            {"role": "user", "content": "今天训练得怎么样？"},
            {"role": "assistant", "content": "哦，还好！刚跑完一圈。"},
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

    assert card["avoidSpeechParticles"] == ["嘿", "哦"]
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


def test_prompt_projects_personal_signals_and_rejects_support_actions_as_love() -> None:
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
                    "personalSignals": [
                        "exclusive_share",
                        "player_caused_anticipation",
                    ],
                    "supportSignals": ["companionship", "specific_plan"],
                    "variationRule": "连续轮次换一种亲近形状。",
                    "maxActions": 1,
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "qualityContext": {
            "flirtIntensity": "direct",
            "adultConsensual": True,
            "romanceEligible": True,
        },
        "gameState": {},
        "history": [],
    }

    card = json.loads(
        next(
            message
            for message in PromptBuilder().build(context, "你最近在听什么歌？")
            if message["name"] == "affection_initiative"
        )["content"]
    )

    assert card["affectionInitiative"]["personalSignals"] == [
        "exclusive_share",
        "player_caused_anticipation",
    ]
    assert card["affectionInitiative"]["supportSignals"] == [
        "companionship",
        "specific_plan",
    ]
    assert card["affectionInitiative"]["variationRule"] == "连续轮次换一种亲近形状。"
    assert "陪伴和安排不能单独充当爱意" in card["instruction"]


def test_prompt_affection_card_uses_current_turn_initiative_expectation() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Wizard",
            "stageProfile": {"stage": "married"},
            "stagePolicy": {
                "stage": "married",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "allowedKinds": ["affection_signal"],
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "qualityContext": {
            "initiativeExpectation": "none",
            "initiativeKind": "none",
            "flirtIntensity": "light",
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "我听见了")
    quality_context = json.loads(
        next(message for message in messages if message["name"] == "quality_context")[
            "content"
        ]
    )
    affection_card = json.loads(
        next(
            message for message in messages if message["name"] == "affection_initiative"
        )["content"]
    )

    assert quality_context["initiativeExpectation"] == "none"
    assert quality_context["initiativeKind"] == "none"
    assert affection_card["affectionInitiative"]["initiativeMode"] == "none"


def test_prompt_affection_card_keeps_proactive_current_turn_expectation() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Wizard",
            "stageProfile": {"stage": "married"},
            "stagePolicy": {
                "stage": "married",
                "affectionInitiative": {
                    "initiativeMode": "none",
                    "allowedKinds": ["affection_signal"],
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "qualityContext": {
            "initiativeExpectation": "proactive",
            "initiativeKind": "affection_signal",
            "flirtIntensity": "light",
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "我听见了")
    affection_card = json.loads(
        next(
            message for message in messages if message["name"] == "affection_initiative"
        )["content"]
    )

    assert affection_card["affectionInitiative"]["initiativeMode"] == "proactive"


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


def test_compact_prompt_keeps_a_short_final_personal_affection_check() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stagePolicy": {
                "stage": "married",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "personalSignals": ["player_directed_preference"],
                    "supportSignals": ["companionship", "specific_plan"],
                    "warmthSignals": ["用共同音乐或安静习惯表达偏爱"],
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "qualityContext": {
            "flirtIntensity": "direct",
            "romanceEligible": True,
            "adultConsensual": True,
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "今晚想先聊会儿吗？", compact=True)
    names = [message["name"] for message in messages]
    final_check = next(
        message for message in messages if message["name"] == "affection_priority_final"
    )

    assert names.index("affection_initiative") < names.index("affection_priority_final")
    assert names.index("affection_priority_final") < names.index("player_input")
    assert "拥抱或回房间等亲密安排" in final_check["content"]
    assert "为何是玩家" in final_check["content"]
    assert "陪伴或安排不足" in final_check["content"]
    assert "共同音乐或安静习惯" in final_check["content"]
    assert "比较、因果或专属选择" in final_check["content"]
    assert len(final_check["content"]) <= 160


def test_compact_affection_card_keeps_only_a_short_hard_priority_contract() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stagePolicy": {
                "stage": "married",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "personalSignals": [
                        "player_directed_preference",
                        "vulnerable_disclosure",
                    ],
                    "supportSignals": ["companionship", "specific_plan"],
                    "minimumExpression": "这段很长的最低表达要求不该进入 compact 行为卡。" * 8,
                    "variationRule": "这段很长的变化规则不该进入 compact 行为卡。" * 8,
                    "warmthSignals": [
                        "不舍得把和玩家的时间压缩成直接回房间，先用带笑的自信打趣说出偏爱",
                        "第二条角色化落点不该和第一条一起塞进 compact 行为卡",
                    ],
                    "channelRules": {
                        "face_to_face": "当前当面聊天可以描述此刻反应，但不能写成发消息。"
                    },
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "qualityContext": {
            "flirtIntensity": "direct",
            "romanceEligible": True,
            "adultConsensual": True,
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "比赛结束了，陪我回房间待会儿？", compact=True)
    card = next(message for message in messages if message["name"] == "affection_initiative")
    rendered = card["content"]

    assert "为何是玩家" in rendered
    assert "单独‘陪你’‘一起’‘坐近’‘回房间’或事务安排无效" in rendered
    assert "勿复用上一轮亲近形状" in rendered
    assert "当前当面聊天可以描述此刻反应" in rendered
    assert "最低表达要求不该进入" not in rendered
    assert "变化规则不该进入" not in rendered
    assert "第二条角色化落点" not in rendered
    assert len(rendered) <= 600


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


def test_compact_affection_card_keeps_remote_guarded_consent_and_end_boundaries() -> None:
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

    messages = PromptBuilder().build(context, "算了，你先休息，我不打扰了。", compact=True)
    card = next(
        message for message in messages if message["name"] == "affection_initiative"
    )
    rendered = card["content"]

    assert "explicit" in rendered
    assert "同意" in rendered
    assert "明确结束" in rendered
    assert "不写成见面" in rendered


def test_compact_guarded_card_handles_player_low_mood_without_a_follow_up_question() -> None:
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
            "flirtIntensity": "direct",
            "adultConsensual": True,
            "romanceEligible": True,
            "initiativeExpectation": "guarded",
            "initiativeKind": "guarded_care",
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(
        context,
        "别逼我说这种话，今天真的没心情。",
        compact=True,
    )
    card = next(message for message in messages if message["name"] == "affection_initiative")
    rendered = card["content"]

    assert "没心情" in rendered
    assert "不要反问" in rendered
    assert "需要空间" in rendered


def test_compact_proactive_card_requires_a_personal_reason_for_companionship_actions() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stageProfile": {"stage": "married"},
            "stagePolicy": {
                "stage": "married",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "allowedIntensities": ["light", "direct", "explicit"],
                    "allowedKinds": ["affection_signal", "specific_plan"],
                    "maxActions": 1,
                    "warmthSignals": ["先选玩家，再用带笑的自信打趣说出偏爱"],
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "qualityContext": {
            "flirtIntensity": "explicit",
            "adultConsensual": True,
            "romanceEligible": True,
            "initiativeExpectation": "proactive",
            "initiativeKind": "affection_signal",
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(
        context,
        "先陪你，当然。坐近一点，我还有话跟你说。",
        compact=True,
    )
    card = next(message for message in messages if message["name"] == "affection_initiative")
    rendered = card["content"]

    assert "因为是你" in rendered
    assert "舍不得" in rendered
    assert "想听你说" in rendered


def test_compact_shared_evening_card_rejects_exclusive_room_as_a_standalone_reason() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Sophia",
            "displayName": "Sophia",
            "stageProfile": {"stage": "married"},
            "stagePolicy": {
                "stage": "married",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "allowedIntensities": ["light", "direct", "explicit"],
                    "allowedKinds": ["shared_evening", "specific_plan"],
                    "maxActions": 1,
                    "warmthSignals": ["在酒窖里，酒杯再好看也更想看玩家"],
                },
            },
        },
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "qualityContext": {
            "flirtIntensity": "explicit",
            "adultConsensual": True,
            "romanceEligible": True,
            "initiativeExpectation": "proactive",
            "initiativeKind": "shared_evening",
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(
        context,
        "再喝一口，然后陪我去里面坐会儿，好吗？",
        compact=True,
    )
    card = next(message for message in messages if message["name"] == "affection_initiative")
    rendered = card["content"]

    assert "共享时光" in rendered
    assert "这里只有我们" in rendered
    assert "因为你在这里" in rendered


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
    assert "爱意" not in topic["instruction"]
    assert "至少一处可感知的爱意" not in topic["instruction"]
    assert "不要等待或回应不存在的玩家句子" in topic["instruction"]
    assert "输出前默默检查" not in topic["instruction"]
    assert "不能用反问或功能性邀约替代" not in topic["instruction"]
    assert "让爱意在前一两句自然出现" not in topic["instruction"]
    assert "不能只用功能性邀约暗示" not in topic["instruction"]
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


def test_high_relationship_final_card_prioritizes_current_choice_before_new_schedule() -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    policy = build_stage_policy("Alex", "married")
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stageProfile": {"stage": "married"},
            "stagePolicy": policy,
        },
        "gameState": {"relationshipStage": "married", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "qualityContext": {
            "initiativeExpectation": "proactive",
            "initiativeKind": "affection_signal",
            "flirtIntensity": "direct",
        },
        "history": [],
    }

    messages = PromptBuilder().build(
        context,
        "先陪我聊一会儿，还是直接去房间？",
    )
    names = [message["name"] for message in messages]
    final_check = next(
        message
        for message in messages
        if message["name"] == "affection_priority_final"
    )

    assert names.index("affection_priority_final") < names.index("player_input")
    assert "先回答玩家已经给出的选项或当前动作" in final_check["content"]
    assert "亲密信号只能嵌在同一话题" in final_check["content"]
    assert "不得另起未提到的未来社交安排" in final_check["content"]
    assert "不要把递入口理解成新的排期" in final_check["content"]


def test_prompt_adds_final_role_voice_contract_before_player_input() -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    policy = build_stage_policy("Alex", "married")
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stageProfile": {"stage": "married"},
            "stagePolicy": policy,
            "voiceStyle": {
                "tone": "直接、热情",
                "sentencePattern": ["短句"],
                "responseRules": ["落到具体行动"],
                "avoid": ["教练式说教"],
            },
        },
        "gameState": {"relationshipStage": "married", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "今天训练累不累？")
    names = [message["name"] for message in messages]
    contract = next(
        message
        for message in messages
        if message["name"] == "final_role_voice_contract"
    )

    assert names.index("final_role_voice_contract") < names.index("player_input")
    assert "当前话题" in contract["content"]
    assert "Alex" in contract["content"]
    assert "教练式说教" in contract["content"]
    assert "玩家明确点名当前动作、地点或选择时，先回答这一项" in contract["content"]
    assert "不把当前动作改写成未来日期、预约或固定时长" in contract["content"]


def test_prompt_adds_player_echo_guard_after_role_contract() -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    policy = build_stage_policy("Alex", "married")
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stageProfile": {"stage": "married"},
            "stagePolicy": policy,
        },
        "gameState": {"relationshipStage": "married", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "今天在葡萄园忙不忙？")
    names = [message["name"] for message in messages]
    guard = next(message for message in messages if message["name"] == "player_echo_guard")

    assert names.index("final_role_voice_contract") < names.index("player_echo_guard")
    assert names.index("player_echo_guard") < names.index("player_input")
    assert "禁止把玩家的问题原样回显后再回答" in guard["content"]
    assert "只保留必要对象词" in guard["content"]
    assert "今天在葡萄园忙不忙" in guard["content"]


def test_elliott_natural_prompt_prioritizes_original_voice_over_behavior_card() -> None:
    """Elliott 的原版句子应成为自然模式的主语气锚点。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "tone": "有文学感，但会落回眼前的具体事",
                "sentencePattern": ["偶尔完整，偶尔短收"],
            },
        },
        "modSources": ["vanilla", "female-bachelors"],
        "qualityContext": {"naturalMode": True, "flirtIntensity": "none"},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "gameState": {},
        "history": [],
        "speechEvidence": [
            {
                "sourceMod": "vanilla",
                "sourceKey": "Mon",
                "text": "我只比你早一年搬到这里。",
            }
        ],
        "styleSamples": [
            {
                "sourceMod": "vanilla",
                "sourceKey": "Tue",
                "text": "纸与笔那美妙的摩擦声可是治愈我灵魂的音乐啊。",
            }
        ],
        "behaviorExamples": [
            {
                "exampleId": "elliott:writing:approved",
                "sourceType": "human_approved",
                "topic": "writing",
                "topicKeywords": ["稿子", "写"],
                "playerInput": "稿子写得怎么样？",
                "npcReply": "进展不错。你想听我说说吗？",
            }
        ],
    }

    messages = PromptBuilder().build(context, "稿子写得怎么样？")
    names = [message["name"] for message in messages]
    behavior_index = names.index("behavior_examples")

    assert names.index("speech_evidence") < behavior_index
    assert names.index("style_evidence") < behavior_index
    assert names.index("original_style_examples") < behavior_index


def test_elliott_original_rhythm_drops_non_vanilla_marriage_voice_evidence() -> None:
    """Elliott 原文校准不能把其他角色覆盖层的婚后对白当成语气样本。"""

    class _ProfileIndex:
        def voice_card(
            self,
            npc_id: str,
            source_mods: list[str],
            *,
            relationship_stage: str = "",
        ) -> dict[str, object]:
            del relationship_stage
            del npc_id, source_mods
            return {
                "voiceAnchors": [
                    {
                        "sourceMod": "invatorzen.idcsm",
                        "text": "自从我们在一起后，我就学会了怎么好好照顾自己。",
                    },
                    {
                        "sourceMod": "vanilla",
                        "text": "我住在海边的小屋里。",
                    },
                ]
            }

        def speech_evidence(
            self,
            npc_id: str,
            source_mods: list[str],
            *,
            relationship_stage: str = "",
            player_input: str = "",
            limit: int = 6,
            completed_event_ids: list[str] | tuple[str, ...] = (),
        ) -> list[dict[str, object]]:
            del npc_id, source_mods, player_input, limit, completed_event_ids
            if relationship_stage == "friend":
                return [
                    {
                        "sourceMod": "vanilla",
                        "evidenceKind": "dialogue",
                        "text": "今天海风还不错。",
                    }
                ]
            return [
                {
                    "sourceMod": "invatorzen.idcsm",
                    "evidenceKind": "marriage_dialogue",
                    "text": "自从我们在一起后，我就学会了怎么好好照顾自己。",
                },
                {
                    "sourceMod": "vanilla",
                    "evidenceKind": "dialogue",
                    "text": "我刚把那一页写完。",
                },
            ]

        def style_samples(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            del args, kwargs
            return [
                {
                    "sourceMod": "invatorzen.idcsm",
                    "text": "错误覆盖层语气",
                },
                {
                    "sourceMod": "vanilla",
                    "text": "原版语气",
                },
            ]

        def behavior_examples(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            del args, kwargs
            return []

        def knowledge_facts(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            del args, kwargs
            return []

        def story_events(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            del args, kwargs
            return []

        def known_characters(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            del args, kwargs
            return []

    context = ContextBuilder(profile_index=_ProfileIndex()).build(
        "Elliott",
        source_mods=["vanilla", "female-bachelors"],
        relationshipStage="married",
        qualityContext={
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
        },
        intent="topic",
        channel="remote",
        gameState={"relationshipStage": "married"},
    )

    evidence = context.get("speechEvidence", [])
    style_samples = context.get("styleSamples", [])
    anchors = context.get("voiceCard", {}).get("voiceAnchors", [])
    assert all(item.get("sourceMod") == "vanilla" for item in evidence)
    assert all(item.get("sourceMod") == "vanilla" for item in style_samples)
    assert all(item.get("sourceMod") == "vanilla" for item in anchors)


def test_elliott_natural_topic_adds_short_vanilla_rhythm_samples() -> None:
    """婚后校准还要带几条短日常原文，避免只学到长篇婚后独白。"""

    class _ProfileIndex:
        def voice_card(
            self,
            npc_id: str,
            source_mods: list[str],
            *,
            relationship_stage: str = "",
        ) -> dict[str, object]:
            del relationship_stage
            del npc_id, source_mods
            return {
                "voiceAnchors": [
                    {
                        "sourceMod": "vanilla",
                        "sourceKey": "Introduction",
                        "text": "啊，我们一直翘首以盼的新农民来啦……",
                    }
                ]
            }

        def speech_evidence(
            self,
            npc_id: str,
            source_mods: list[str],
            *,
            relationship_stage: str = "",
            player_input: str = "",
            limit: int = 6,
            completed_event_ids: list[str] | tuple[str, ...] = (),
        ) -> list[dict[str, object]]:
            del npc_id, source_mods, player_input, limit, completed_event_ids
            if relationship_stage == "acquaintance":
                return [
                    {
                        "sourceMod": "vanilla",
                        "sourceKey": "Fri4",
                        "evidenceKind": "dialogue",
                        "text": "嘿……别拿着个火把离我头发这么近……",
                    },
                    {
                        "sourceMod": "vanilla",
                        "sourceKey": "Sat4",
                        "evidenceKind": "dialogue",
                        "text": "请原谅我这里这么乱。",
                    },
                ]
            return [
                {
                    "sourceMod": "vanilla",
                    "sourceKey": "OneKid_0",
                    "evidenceKind": "marriage_dialogue",
                    "text": "我得花一点时间照顾小孩。",
                }
            ]

        def style_samples(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            del args, kwargs
            return []

        def behavior_examples(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            del args, kwargs
            return []

        def knowledge_facts(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            del args, kwargs
            return []

        def story_events(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            del args, kwargs
            return []

        def known_characters(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            del args, kwargs
            return []

    context = ContextBuilder(profile_index=_ProfileIndex()).build(
        "Elliott",
        source_mods=["vanilla", "female-bachelors"],
        relationshipStage="married",
        qualityContext={
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "turnPlan": {"mode": "answer_plus_lead"},
        },
        intent="topic",
        channel="remote",
        gameState={"relationshipStage": "married"},
    )

    messages = PromptBuilder().build(context, "")
    examples = [
        message["content"]
        for message in messages
        if message["name"] == "original_style_example_assistant"
    ]

    assert "嘿……别拿着个火把离我头发这么近……" in examples
    assert "请原谅我这里这么乱。" in examples
    assert "我得花一点时间照顾小孩。" in examples


def test_natural_topic_prompt_drops_scene_filler_from_generation_context() -> None:
    """找话题评测只保留关系阶段，避免模型把背景卡写成环境小作文。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "turnPlan": {"mode": "answer_plus_lead", "intensity": "light"},
            "relationshipContext": "婚后阶段：在海边画室里从未完成的稿子转到靠近和共同阅读。",
            "topicSeed": "未完成的稿子",
        },
        "interaction": {"intent": "topic", "channel": "face_to_face"},
        "gameState": {
            "relationshipStage": "married",
            "location": "海边画室",
            "season": "秋",
            "date": "秋 18 日",
            "time": 1930,
            "weather": "晴天",
        },
        "recentFacts": ["画室灯亮着，稿纸和两把椅子都在眼前。"],
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    state = json.loads(
        next(message for message in messages if message["name"] == "game_state")[
            "content"
        ]
    )
    quality = json.loads(
        next(message for message in messages if message["name"] == "quality_context")[
            "content"
        ]
    )

    assert state["gameState"] == {"relationshipStage": "married"}
    assert state["recentFacts"] == []
    assert "relationshipContext" not in quality


def test_elliott_natural_contract_keeps_role_voice_without_hard_affection_shape() -> None:
    """公共自然模式保留角色习惯，Elliott 的文学感由局部校准卡承接。"""

    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Elliott", "married"),
            "voiceStyle": {
                "tone": "有文学感和审美，但说话落地、克制",
                "responseRules": ["先回应眼前的事，再决定是否展开"],
            },
        },
        "modSources": ["vanilla", "female-bachelors"],
        "qualityContext": {
            "naturalMode": True,
            "flirtIntensity": "direct",
            "initiativeExpectation": "proactive",
            "initiativeKind": "affection_signal",
            "romanceEligible": True,
            "adultConsensual": True,
        },
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "稿子今天写得顺吗？")
    natural_contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )
    content = natural_contract["content"]

    assert "保留角色已有的说话习惯" in content
    assert "不把日常扩写成统一的书面或散文模板" in content
    assert "保留角色已有的文学感" not in content
    assert "不必把每轮写成完整的" in content
    assert "主动亲密是可选表达，不是每轮必须满足的格式" in content


def test_natural_contract_does_not_assign_literary_voice_to_non_elliott_roles() -> None:
    """公共自然契约应保留角色习惯，文学感只能由 Elliott 的局部卡提供。"""

    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only", "intensity": "light"},
        },
        "gameState": {"relationshipStage": "married"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "今天还好吗？")
    contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )["content"]

    assert "保留角色已有的说话习惯" in contract
    assert "保留角色已有的文学感" not in contract
    assert "比喻只在角色或当前话题本来需要时使用" in contract


def test_elliott_natural_contract_treats_metaphor_as_optional_and_non_repeating() -> None:
    """文学感应是可选语气，不能变成每轮都要交付的修辞任务。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "turnPlan": {"mode": "answer_plus_detail"},
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "稿子写得怎么样？")
    natural_contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )
    rhythm_card = next(
        message for message in messages if message["name"] == "elliott_rhythm_card"
    )

    assert "比喻只在角色或当前话题本来需要时使用" in natural_contract["content"]
    assert "比喻不是每轮必需" not in natural_contract["content"]
    assert "不要复述玩家刚用过的完整比喻" in natural_contract["content"]
    assert "普通闲聊默认不主动使用比喻" in rhythm_card["content"]
    assert "最多使用一个比喻" not in rhythm_card["content"]


def test_elliott_original_rhythm_prefers_short_pause_samples_after_marriage_anchor() -> None:
    """Elliott 的婚后校准应以一条婚后原文配短、会停住的日常原文。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "modSources": ["vanilla", "female-bachelors"],
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "turnPlan": {"mode": "answer_plus_detail"},
        },
        "gameState": {},
        "history": [],
        "speechEvidence": [
            {
                "sampleId": "vanilla:marriage:Rainy_Day_1",
                "sourceKey": "Rainy_Day_1",
                "evidenceKind": "marriage_dialogue",
                "sourceMod": "vanilla",
                "text": "雨声让我想起海边的小屋。",
            },
            {
                "sampleId": "vanilla:Thu6",
                "sourceKey": "Thu6",
                "evidenceKind": "dialogue",
                "sourceMod": "vanilla",
                "text": "有时我觉得自己可能是太膨胀了，其实我并没有什么本事……不，不……",
            },
            {
                "sampleId": "vanilla:Fri4",
                "sourceKey": "Fri4",
                "evidenceKind": "dialogue",
                "sourceMod": "vanilla",
                "text": "嘿……别拿着个火把离我头发这么近……",
            },
            {
                "sampleId": "vanilla:Thu2",
                "sourceKey": "Thu2",
                "evidenceKind": "dialogue",
                "sourceMod": "vanilla",
                "text": "我找不到小说开头的灵感啊……",
            },
            {
                "sampleId": "vanilla:Sat4",
                "sourceKey": "Sat4",
                "evidenceKind": "dialogue",
                "sourceMod": "vanilla",
                "text": "请原谅我这里这么乱。",
            },
        ],
        "styleSamples": [],
        "voiceCard": {
            "voiceAnchors": [
                {
                    "sourceKey": "Introduction",
                    "sourceMod": "vanilla",
                    "text": "啊，我们一直翘首以盼的新农民来啦……",
                }
            ]
        },
    }

    messages = PromptBuilder().build(context, "那句后来改了吗？")
    examples = [
        message["content"]
        for message in messages
        if message["name"] == "original_style_example_assistant"
    ]

    assert examples[0] == "雨声让我想起海边的小屋。"
    assert "嘿……别拿着个火把离我头发这么近……" in examples
    assert "我找不到小说开头的灵感啊……" in examples
    assert "请原谅我这里这么乱。" in examples
    assert "啊，我们一直翘首以盼的新农民来啦……" not in examples


def test_elliott_natural_rhythm_filters_long_voice_card_anchors() -> None:
    """自然 Elliott 不应继续把介绍和节庆长句当作普通闲聊的语气锚点。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
        },
        "voiceCard": {
            "voiceAnchors": [
                {
                    "sourceKey": "Introduction",
                    "sourceMod": "vanilla",
                    "text": "啊，我们一直翘首以盼的新农民来啦……",
                },
                {
                    "sourceKey": "SquidFest",
                    "sourceMod": "vanilla",
                    "text": "你知道吗？海滩上的鱿鱼真的很罕见。",
                },
                {
                    "sourceKey": "Fri4",
                    "sourceMod": "vanilla",
                    "text": "嘿……别拿着个火把离我头发这么近……",
                },
                {
                    "sourceKey": "Sat4",
                    "sourceMod": "vanilla",
                    "text": "请原谅我这里这么乱。",
                },
                {
                    "sourceKey": "Thu6",
                    "sourceMod": "vanilla",
                    "text": "不，不……我只是有点累。",
                },
            ]
        },
        "gameState": {"relationshipStage": "married"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "今天写得顺吗？")
    voice_message = next(
        message for message in messages if message["name"] == "voice_card"
    )
    voice_card = json.loads(voice_message["content"])["voiceCard"]
    keys = [item.get("sourceKey") for item in voice_card["voiceAnchors"]]

    assert keys == ["Fri4", "Sat4", "Thu6"]


def test_elliott_rhythm_card_prefers_plain_chat_over_scene_and_timeline_fillers() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "turnPlan": {"mode": "answer_plus_detail"},
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "信写给谁的？")
    contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )["content"]
    rhythm = next(
        message for message in messages if message["name"] == "elliott_rhythm_card"
    )["content"]

    assert "普通闲聊默认不主动使用比喻" in rhythm
    assert "只有玩家明确谈作品、句子、海风或光线时才允许" in rhythm
    assert "不把普通分享写成警句" in rhythm
    assert "不要复述玩家刚用过的完整比喻" in contract


def test_elliott_rhythm_card_returns_from_imagery_to_the_current_object() -> None:
    """Elliott 可以有意象，但不能把具体一句话升级成格言。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "turnPlan": {"mode": "answer_plus_detail"},
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "那句到底写了什么？")
    rhythm = next(
        message for message in messages if message["name"] == "elliott_rhythm_card"
    )["content"]

    assert "如果用了比喻，马上回到当前的人、物件或动作" in rhythm
    assert "不要把具体句子总结成普遍道理" in rhythm
    assert "不要用‘有时候……更……’这类格言式收束" in rhythm


def test_elliott_rhythm_card_does_not_assign_a_fixed_imagery_landing() -> None:
    """Elliott 的文学感应是可选语气，不能把每轮都引向固定意象。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "turnPlan": {"mode": "answer_plus_detail"},
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "稿子今天写得顺吗？")
    rhythm_card = next(
        message for message in messages if message["name"] == "elliott_rhythm_card"
    )
    content = rhythm_card["content"]

    assert "普通闲聊默认不主动使用比喻" in content
    assert "只有玩家明确谈作品、句子、海风或光线时才允许" in content
    assert "随后落回纸、稿子、海风、窗边或手边动作" not in content


def test_natural_compact_topic_drops_affection_card_for_detail_turns() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": {
                "stage": "married",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "allowedIntensities": ["light", "direct"],
                    "allowedKinds": ["creative_share", "affection_signal"],
                    "personalSignals": ["player_directed_preference"],
                    "warmthSignals": ["把当天一件小事告诉玩家"],
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "initiativeExpectation": "responsive",
            "initiativeKind": "none",
            "flirtIntensity": "light",
            "turnPlan": {"mode": "answer_plus_detail", "intensity": "light"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "你刚才那句改好了吗？", compact=True)
    assert "affection_initiative" not in {
        message["name"] for message in messages
    }


def test_natural_detail_turn_prefers_plain_facts_over_new_metaphors() -> None:
    """adaptive 后续轻承接应优先口语事实，不能把细节重新写成修辞任务。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "initiativeExpectation": "responsive",
            "initiativeKind": "none",
            "turnPlan": {"mode": "answer_plus_detail", "intensity": "light"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "那句你后来改了吗？")
    turn_plan = next(
        message for message in messages if message["name"] == "turn_plan"
    )

    assert "普通续聊直接说事实、动作或短感受" in turn_plan["content"]
    assert "不要自行写新比喻" in turn_plan["content"]
    assert not any(
        message["name"] == "natural_detail_override" for message in messages
    )


def test_natural_topic_drops_affection_booster_and_softens_quality_instruction() -> None:
    """自然找话题的轻回合不能同时收到亲密加速卡和阶段升温暗示。"""

    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Elliott", "married"),
        },
        "qualityContext": {
            "naturalMode": True,
            "flirtIntensity": "light",
            "turnPlan": {"mode": "answer_only", "intensity": "light"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "", compact=True)
    names = [message["name"] for message in messages]
    quality = json.loads(
        next(message for message in messages if message["name"] == "quality_context")[
            "content"
        ]
    )

    assert "affection_initiative" not in names
    assert "关系已经成立时，可以自然主动接近一步" not in quality["instruction"]
    assert "当前自然对白只执行本轮的当前目标" in quality["instruction"]
    stage = json.loads(
        next(message for message in messages if message["name"] == "stage_execution_card")[
            "content"
        ]
    )
    assert "表达预算：直接回答后最多追加一个角色化动作" not in stage["instruction"]


def test_natural_topic_opener_does_not_require_a_polished_handoff_or_fresh_quote() -> None:
    """自然开场可以停在一件小事，不应为了交棒而写成提问或新引文。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "turnPlan": {"mode": "answer_plus_lead", "intensity": "light"},
            "topicSeed": "未完成的稿子",
        },
        "interaction": {"intent": "topic", "channel": "face_to_face"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    topic_contract = next(
        message
        for message in messages
        if message["name"] == "topic_response_contract"
    )["content"]
    natural_contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )["content"]

    assert "不要为了把话题交出去硬加问题、二选一或安排" in topic_contract
    assert "除非玩家明确问原句或内容，不要主动展示新写的句子、完整引文或散文段落" in natural_contract


def test_natural_topic_contract_does_not_prescribe_a_fixed_message_shape() -> None:
    """自然找话题不能同时给模型固定句数和完整的开场任务。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "topicSeed": "未完成的稿子",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    topic_contract = next(
        message
        for message in messages
        if message["name"] == "topic_response_contract"
    )["content"]

    assert "1–3 句" not in topic_contract
    assert "通常一到两句" not in topic_contract
    assert "具体且可以继续聊下去的话头" not in topic_contract
    assert "一件眼前小事" in topic_contract


def test_natural_topic_contract_drops_automatic_handoff_and_phrase_echo() -> None:
    """自然找话题不能把事实润色成邀请，也不能把玩家短语换序复述。"""

    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "dating"},
        },
        "qualityContext": {
            "naturalMode": True,
            "topicSeed": "月光与研究记录",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    topic_contract = next(
        message
        for message in messages
        if message["name"] == "topic_response_contract"
    )["content"]

    assert "不要自动追加‘如果你想看/有空来/要不要/我可以给你’" in topic_contract
    assert "不要把玩家最后一句的核心短语原样再说一遍" in topic_contract


def test_natural_topic_keeps_role_rhythm_after_public_topic_contract() -> None:
    """角色专属开场节奏要在公共找话题契约之后再次生效。"""

    def render(npc_id: str, source_mods: list[str]) -> str:
        context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
            npc_id,
            source_mods=source_mods,
            gameState={"relationshipStage": "married"},
            qualityContext={
                "naturalMode": True,
                "topicSeed": "眼前的一件小事",
                "turnPlan": {"mode": "answer_only"},
            },
            intent="topic",
            channel="face_to_face",
        )
        messages = PromptBuilder().build(context, "")
        names = [message["name"] for message in messages]
        assert names.index("natural_topic_role_override") > names.index(
            "topic_response_contract"
        )
        assert names.index("natural_topic_role_override") > names.index("turn_plan")
        assert names.index("natural_topic_role_override") < names.index("topic_trigger")
        return next(
            message["content"]
            for message in messages
            if message["name"] == "natural_topic_role_override"
        )

    ras = render("Wizard", ["Romanceable Rasmodius"])
    sophia = render("Sophia", ["Stardew Valley Expanded"])

    assert ras != sophia
    assert "判断、事实或限制" in ras
    assert "感官细节" in sophia
    assert "不要把公共找话题指令当成固定顺序" in ras
    assert "不要把公共找话题指令当成固定顺序" in sophia


def test_natural_dialogue_contract_avoids_short_phrase_echo() -> None:
    """自然续聊没有新信息时应收口，不能只换主语重说玩家短语。"""

    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "那就留一份吧。")
    natural_contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )["content"]

    assert "不要把玩家最后一句的核心短语换个主语或语序重说" in natural_contract
    assert "没有新信息就直接短收口" in natural_contract
    assert "不要以‘嗯，+玩家原句’开头" in natural_contract


def test_natural_contract_does_not_turn_every_reply_into_a_two_step_template() -> None:
    """自然模式允许一句收束，不能把补细节和微反应变成每轮任务。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "turnPlan": {"mode": "answer_plus_detail"},
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "那封信写完了吗？")
    natural_contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )
    content = natural_contract["content"]

    assert "不必每轮同时完成‘回答＋细节’" in content
    assert "不必刻意表现微反应" in content
    assert "先接住一个最具体的点，再按角色习惯补一个小反应" not in content
    assert "每轮最多表现一个微反应" not in content


def test_natural_topic_without_explicit_plan_can_stop_after_one_small_fact() -> None:
    """自然找话题不能因为 topic intent 自动套上交棒式开场。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "initiativeExpectation": "none",
            "initiativeKind": "none",
            "topicSeed": "未完成的稿子",
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    turn_plan = json.loads(
        next(message for message in messages if message["name"] == "turn_plan")[
            "content"
        ]
    )

    assert turn_plan["mode"] == "answer_only"
    assert "一句就停" in turn_plan["instruction"]
    assert "继续入口" not in turn_plan["instruction"]


@pytest.mark.parametrize("natural_mode", [False, True])
def test_topic_opening_may_be_spontaneous_but_must_explain_new_context(
    natural_mode: bool,
) -> None:
    """主动找话题可以自带新话题，但不能把未铺垫的前情当作玩家已知。

    来源句是硬要求（不是「三选一交代一项」），并且要点名禁止「X 不会…／X 还是…」
    这类预设对方已知的开头；结尾的接话点必须是玩家能接的口子（真问题／把玩家
    拉进来的具体事／玩家已知的共同对象），不再允许只给 NPC 单方面的物。
    """

    context = {
        "npcIdentity": {
            "npcId": "Sebastian",
            "displayName": "Sebastian",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": natural_mode,
            "topicSeed": "一张最近翻出来的唱片",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "face_to_face"},
        "gameState": {"relationshipStage": "married", "location": "地下室"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    contract = next(
        message
        for message in messages
        if message["name"] == "topic_response_contract"
    )["content"]

    assert "允许从角色自己的近况、记忆、兴趣或眼前观察主动开启新话题" in contract
    assert "必须在同一条消息给出最小背景" in contract
    assert "不要只说‘那件事、那首歌、最近那个" in contract
    assert "玩家不需要知道此前未说过的前提" in contract
    assert "无论话题从哪来，都必须有一句来源句" in contract
    assert "不要用‘X 不会…’‘X 还是…’这类预设对方已知的句式开头" in contract
    assert "三选一：一个真问题、一件把玩家拉进来的具体事、或一个玩家已知的共同对象" in contract
    assert "只留一个口子就够，不要堆问题，也不要用命令或提醒代替口子" in contract
    assert "记录簿不会长腿跑掉" in contract
    assert "我刚把今天的记录簿合上" in contract
    assert "至少交代其中一项" not in contract
    assert "不强制追问、邀约或安排" not in contract


def test_natural_topic_without_explicit_plan_downgrades_stage_execution_card() -> None:
    """自然找话题即使带完整阶段卡，也不能泄漏主动亲密和交棒契约。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": {
                "stage": "married",
                "responseShape": "可用 2–3 句回应并补一个继续入口",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "minimumExpression": "正常轮次保留一处具体偏爱",
                },
                "conversationLead": {
                    "required": "usually",
                    "allowedKinds": ["question", "specific_plan"],
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "initiativeExpectation": "none",
            "initiativeKind": "none",
            "topicSeed": "未完成的稿子",
        },
        "interaction": {"intent": "topic", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    stage_card = json.loads(
        next(message for message in messages if message["name"] == "stage_execution_card")[
            "content"
        ]
    )

    assert "affectionInitiative" not in stage_card
    assert "conversationLead" not in stage_card
    assert stage_card["responseShape"] == (
        "先直接回答当前输入；只有自然相关时才补一个眼前细节，没有可补内容就停下"
    )
    assert "不要求主动亲密" in stage_card["instruction"]


def test_natural_mode_keeps_full_stage_policy_out_of_persona_core() -> None:
    """自然模式只使用投影后的阶段卡，角色卡不能再泄漏整套阶段策略。"""

    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Elliott", "married"),
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    persona = json.loads(
        next(
            message
            for message in PromptBuilder().build(context, "那页稿子还在吗？")
            if message["name"] == "persona_core"
        )["content"]
    )

    assert "stagePolicy" not in persona["npcIdentity"]


def test_natural_answer_only_does_not_add_progression_guard() -> None:
    """自然轻续聊没有真实新信息时，不应被强制要求写出新进展。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only"},
            "continuationMode": "anchored",
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [
            {"role": "user", "content": "我刚把信重新抄了一遍。"},
            {"role": "assistant", "content": "刚才那句读起来不太顺。"},
        ],
    }

    names = [
        message["name"]
        for message in PromptBuilder().build(context, "嗯，改完顺多了吧？")
    ]

    assert "progression_guard" not in names


def test_natural_continuation_contract_allows_a_plain_acknowledgement() -> None:
    """自然续聊只需接住当前输入，不能把“新增进展”变成固定写作任务。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [
            {"role": "user", "content": "我刚把信重新抄了一遍。"},
            {"role": "assistant", "content": "刚才那句读起来不太顺。"},
        ],
    }

    continuation = json.loads(
        next(
            message
            for message in PromptBuilder().build(context, "嗯，改完顺多了吧？")
            if message["name"] == "continuation_contract"
        )["content"]
    )

    assert "接住当前输入即可" in continuation["instruction"]
    assert "只新增一个眼前进展" not in continuation["instruction"]


def test_natural_continuation_hides_case_topic_metadata() -> None:
    """自然续聊不应继续携带首轮案例的 topicSeed 和关键词清单。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "topicSeed": "共同阅读",
            "topicKeywords": ["章节", "读"],
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [
            {"role": "assistant", "content": "我刚翻到昨晚卡住的那一页。"},
        ],
    }

    continuation = json.loads(
        next(
            message
            for message in PromptBuilder().build(context, "你后来读下去了吗？")
            if message["name"] == "continuation_contract"
        )["content"]
    )

    assert "topicSeed" not in continuation
    assert "topicKeywords" not in continuation


def test_natural_light_turn_drops_voice_variation_task() -> None:
    """自然轻续聊不应为了“变化”刻意改造起句和句式。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "voiceStyle": {
                "speechParticleHints": ["嗯", "好"],
                "sentencePattern": ["短句直接"],
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [
            {"role": "user", "content": "那页还在吗？"},
            {"role": "assistant", "content": "还在桌上。"},
        ],
    }

    names = [
        message["name"]
        for message in PromptBuilder().build(context, "我去拿。")
    ]

    assert "voice_variation" not in names


def test_natural_adaptive_first_turn_keeps_one_small_voice_sample_window() -> None:
    """自然 adaptive 首轮可以用少量原文建立声线，但不能重复投影控制卡。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "speechEvidence": [
            {"sourceKey": "Thu6", "text": "不，不……我只是有点累。"},
            {"sourceKey": "Sat6", "text": "有些人比较羞涩。"},
            {"sourceKey": "Sun6", "text": "见到你太高兴了。"},
        ],
        "styleSamples": [
            {"sourceKey": "Thu2", "text": "我找不到小说开头的灵感啊……"},
            {"sourceKey": "Sat4", "text": "请原谅我这里这么乱。"},
        ],
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "我去拿。")
    names = [message["name"] for message in messages]

    assert "speech_evidence" not in names
    assert "style_evidence" not in names
    assert names.count("original_style_examples") == 1
    assert len(
        [
            message
            for message in messages
            if message["name"] == "original_style_example_assistant"
        ]
    ) <= 1


def test_natural_adaptive_first_turn_limits_voice_card_anchors() -> None:
    """自然 adaptive 首轮只保留少量声线锚点，避免把示例叠成写作模板。"""

    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "face_to_face"},
        "voiceCard": {
            "voiceAnchors": [
                {"sourceKey": "a", "text": "第一条。"},
                {"sourceKey": "b", "text": "第二条。"},
                {"sourceKey": "c", "text": "第三条。"},
                {"sourceKey": "d", "text": "第四条。"},
            ]
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    voice_message = next(
        message for message in messages if message["name"] == "voice_card"
    )
    voice_card = json.loads(voice_message["content"])["voiceCard"]

    assert len(voice_card["voiceAnchors"]) <= 2


def test_natural_adaptive_continuation_drops_repeated_voice_cards_after_history() -> None:
    """自然 adaptive 续聊应信任当前历史，不要每轮重放语气执行清单。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
            "styleCalibration": "elliott_original_rhythm",
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "speechEvidence": [
            {"sourceKey": "Thu6", "text": "不，不……我只是有点累。"},
            {"sourceKey": "Sat6", "text": "有些人比较羞涩。"},
        ],
        "styleSamples": [
            {"sourceKey": "Thu2", "text": "我找不到小说开头的灵感啊……"},
        ],
        "gameState": {},
        "history": [
            {"role": "user", "content": "那页后来改了吗？"},
            {"role": "assistant", "content": "还在桌上。"},
        ],
    }

    names = [
        message["name"]
        for message in PromptBuilder().build(context, "我去拿。")
    ]

    assert "post_history_voice_guard" not in names
    assert "original_style_examples" not in names
    assert "original_style_example_assistant" not in names


def test_natural_adaptive_continuation_drops_elliott_rhythm_card_after_history() -> None:
    """有真实对白后，Elliott 不应每轮重新收到文学化节奏说明。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
            "styleCalibration": "elliott_original_rhythm",
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [
            {"role": "user", "content": "那封信后来改了吗？"},
            {"role": "assistant", "content": "还在桌上。"},
        ],
    }

    names = [
        message["name"]
        for message in PromptBuilder().build(context, "我去拿。")
    ]

    assert "elliott_rhythm_card" not in names
    assert "continuation_contract" in names
    assert "turn_plan" in names


def test_natural_stage_execution_card_does_not_name_removed_stage_controls() -> None:
    """自然阶段卡只描述实际投影的边界，不给模型残留字段名。"""

    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Elliott", "married"),
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [{"role": "assistant", "content": "还在桌上。"}],
    }

    stage = json.loads(
        next(
            message
            for message in PromptBuilder().build(context, "那页还在吗？")
            if message["name"] == "stage_execution_card"
        )["content"]
    )
    instruction = stage["instruction"]

    assert "responseShape" in instruction
    assert "boundaryMode" in instruction
    assert "selfDisclosure" not in instruction
    assert "initiative" not in instruction
    assert "followUp" not in instruction


def test_natural_adaptive_continuation_does_not_turn_player_overlap_into_echo_terms() -> None:
    """普通短语重叠不能再变成要求模型回显的历史关键词。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [
            {
                "role": "assistant",
                "content": "刚把信折好，封口那点蜡油还是软的。",
            },
            {
                "role": "user",
                "content": "那就再焐一会儿吧，反正它跑不掉。",
            },
        ],
    }

    messages = PromptBuilder().build(context, context["history"][-1]["content"])
    names = [message["name"] for message in messages]

    assert "current_topic_anchor" not in names
    assert "reply_contract" not in names


def test_natural_history_anchors_ignore_mundane_overlap_words() -> None:
    """“一遍”“突然”等普通重叠词不能变成模型必须回显的历史对象。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [
            {"role": "user", "content": "我刚把信重新抄了一遍。"},
            {"role": "assistant", "content": "刚才那句读起来不太顺。"},
        ],
    }

    messages = PromptBuilder().build(context, "怎么突然又抄一遍？")
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "historyAnchors" not in rendered
    assert "mustMentionOneOf" not in rendered


def test_natural_responsive_chat_without_plan_defaults_to_direct_answer() -> None:
    """自然续聊没有显式计划时，不应默认生成回答加细节的两段式。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "initiativeExpectation": "responsive",
            "initiativeKind": "none",
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "那页你还留着吗？")
    turn_plan = json.loads(
        next(message for message in messages if message["name"] == "turn_plan")[
            "content"
        ]
    )

    assert turn_plan["mode"] == "answer_only"
    assert "补一句" not in turn_plan["instruction"]


def test_natural_contract_allows_adjacent_turns_to_change_length_and_shape() -> None:
    """自然模式应明确允许相邻回合各自决定一句、两句或收口。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {"naturalMode": True},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "你今天还在写吗？")
    natural_contract = next(
        message
        for message in messages
        if message["name"] == "natural_dialogue_contract"
    )["content"]

    assert "相邻回合不要默认保持同样句数或结构" in natural_contract
    assert "每轮独立决定一句就停、补一句或交还话头" in natural_contract


def test_elliott_rhythm_card_does_not_request_performed_pauses_or_fixed_length() -> None:
    """Elliott 的停顿和句长应来自内容，不能由节奏卡硬造。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "turnPlan": {"mode": "answer_plus_detail"},
        },
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "你刚才改的是哪一句？")
    rhythm_card = next(
        message for message in messages if message["name"] == "elliott_rhythm_card"
    )
    content = rhythm_card["content"]

    assert "有具体细节时再补一句" in content
    assert "不要刻意停顿或改口" in content
    assert "通常一到两句，允许一次停顿或改口" not in content


def test_natural_detail_turn_does_not_add_a_second_affection_self_check() -> None:
    """轻承接回合已有自然边界时，不再叠加末尾亲密自检。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": {
                "stage": "married",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "allowedKinds": ["creative_share", "affection_signal"],
                    "allowedIntensities": ["light", "direct"],
                    "warmthSignals": ["把当天一件小事告诉玩家"],
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "initiativeExpectation": "responsive",
            "initiativeKind": "none",
            "flirtIntensity": "light",
            "turnPlan": {"mode": "answer_plus_detail", "intensity": "light"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "那页你还留着吗？")
    names = [message["name"] for message in messages]

    assert "affection_priority_final" not in names


def test_natural_detail_turn_does_not_reintroduce_personal_affection_requirement() -> None:
    """turn_plan 的轻承接目标应压过阶段卡的强亲密最低项。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": {
                "stage": "married",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "personalSignals": ["因为玩家而想分享"],
                    "warmthSignals": ["把当天的小事告诉玩家"],
                    "minimumExpression": "正常轮次保留一处具体偏爱",
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_plus_detail"},
            "initiativeExpectation": "responsive",
            "initiativeKind": "creative_share",
            "flirtIntensity": "light",
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "稿子写得怎么样？")
    assert "affection_initiative" not in {
        message["name"] for message in messages
    }


def test_natural_light_turn_sanitizes_stage_affection_defaults() -> None:
    """自然轻回合不能把婚后阶段的主动亲密默认值再次交给模型。"""

    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Elliott", "married"),
        },
        "qualityContext": {
            "naturalMode": True,
            "initiativeExpectation": "responsive",
            "initiativeKind": "none",
            "flirtIntensity": "light",
            "turnPlan": {"mode": "answer_plus_detail", "intensity": "light"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    stage = json.loads(
        next(
            message
            for message in PromptBuilder().build(context, "那页你还留着吗？")
            if message["name"] == "stage_execution_card"
        )["content"]
    )

    affection = stage.get("affectionInitiative", {})
    assert affection.get("initiativeMode") != "proactive"
    assert "minimumExpression" not in affection
    assert "本轮以自然轻承接为唯一行为目标" in stage["instruction"]


def test_natural_light_turn_replaces_full_affection_card_even_without_compact_prompt() -> None:
    """完整 Prompt 的自然轻回合也不能保留主动亲密长卡。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": {
                "stage": "married",
                "affectionInitiative": {
                    "initiativeMode": "proactive",
                    "minimumExpression": "每轮至少自然表达一处爱意",
                    "warmthSignals": ["把当天一件小事告诉玩家"],
                },
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "initiativeExpectation": "responsive",
            "initiativeKind": "none",
            "flirtIntensity": "light",
            "turnPlan": {"mode": "answer_plus_detail", "intensity": "light"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    names = [
        message["name"]
        for message in PromptBuilder().build(context, "你还在写那页吗?")
    ]

    assert "affection_initiative" not in names


def test_natural_light_turn_keeps_distinct_role_texture_for_ras_and_sophia() -> None:
    """自然轻回合仍要给模型一张短的角色纹理卡，避免 Ras 与 Sophia 退化成同一套句式。"""

    from stardew_ai_bridge.stage_policy import build_stage_policy

    def render(npc_id: str, display_name: str, source_mods: list[str]) -> dict[str, object]:
        context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
            npc_id,
            source_mods=source_mods,
            relationshipStage="married",
            friendshipHearts=10,
            gameState={"relationshipStage": "married"},
            qualityContext={
                "naturalMode": True,
                "flirtIntensity": "light",
                "turnPlan": {"mode": "answer_only", "intensity": "light"},
            },
            interaction={"intent": "chat", "channel": "face_to_face"},
            history=[
                {"role": "user", "content": "你最近忙什么？"},
                {"role": "assistant", "content": "还在处理手头的事。"},
            ],
        )
        # 保证测试关注自然轻回合的 Prompt 分支，而不是依赖评测案例的阶段卡。
        context["npcIdentity"]["displayName"] = display_name
        context["npcIdentity"]["stagePolicy"] = build_stage_policy(npc_id, "married")
        messages = PromptBuilder().build(context, "那你先忙。")
        return json.loads(
            next(
                message
                for message in messages
                if message["name"] == "natural_role_texture"
            )["content"]
        )

    ras = render("Wizard", "Rasmodia", ["Romanceable Rasmodius"])
    sophia = render("Sophia", "Sophia", ["Stardew Valley Expanded"])

    assert ras["npcId"] == "Wizard"
    assert sophia["npcId"] == "Sophia"
    assert ras["voiceFingerprint"] != sophia["voiceFingerprint"]
    assert "不把普通话题说成预言" in ras["voiceFingerprint"]
    assert "葡萄、酿造或画面细节" in sophia["voiceFingerprint"]
    assert any("先直接回应玩家" in item for item in ras["responseRules"])
    assert any("先轻声回应眼前的话题" in item for item in sophia["responseRules"])
    assert any("魔法当作事实" in item for item in ras["avoid"])
    assert any("紧张时允许" in item for item in sophia["responseRules"])
    assert ras["responseRules"] != sophia["responseRules"]
    assert ras["avoid"] != sophia["avoid"]


def test_natural_role_texture_exposes_non_overlapping_signature_moves() -> None:
    """自然轻回合必须把两人的句首和收束动作分开，不能只靠主题词区分。"""

    from stardew_ai_bridge.stage_policy import build_stage_policy

    def render(npc_id: str, source_mods: list[str]) -> dict[str, object]:
        context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
            npc_id,
            source_mods=source_mods,
            relationshipStage="married",
            friendshipHearts=10,
            gameState={"relationshipStage": "married"},
            qualityContext={"naturalMode": True, "turnPlan": {"mode": "answer_only"}},
            interaction={"intent": "chat", "channel": "face_to_face"},
        )
        context["npcIdentity"]["stagePolicy"] = build_stage_policy(npc_id, "married")
        return json.loads(
            next(
                message
                for message in PromptBuilder().build(context, "你最近在忙什么？")
                if message["name"] == "natural_role_texture"
            )["content"]
        )

    ras = render("Wizard", ["Romanceable Rasmodius"])
    sophia = render("Sophia", ["Stardew Valley Expanded"])

    assert ras["signatureMoves"]
    assert sophia["signatureMoves"]
    assert set(ras["signatureMoves"]).isdisjoint(sophia["signatureMoves"])
    # 特征词只用来证明「两人的签名动作不同」，跟着 persona 文案走，
    # 不锁定某一版具体措辞。
    assert any("判断" in item and "嗯" in item for item in ras["signatureMoves"])
    assert any("第一反应" in item and "追加" in item for item in sophia["signatureMoves"])


def test_natural_role_texture_exposes_role_specific_rhythm_profiles() -> None:
    """Ras 与 Sophia 还需要不同的开口、展开和收束倾向，不能只换主题词。"""

    from stardew_ai_bridge.stage_policy import build_stage_policy

    def render(npc_id: str, source_mods: list[str]) -> dict[str, object]:
        context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
            npc_id,
            source_mods=source_mods,
            relationshipStage="married",
            friendshipHearts=10,
            gameState={"relationshipStage": "married"},
            qualityContext={"naturalMode": True, "turnPlan": {"mode": "answer_only"}},
            interaction={"intent": "chat", "channel": "face_to_face"},
        )
        context["npcIdentity"]["stagePolicy"] = build_stage_policy(npc_id, "married")
        return json.loads(
            next(
                message
                for message in PromptBuilder().build(context, "你最近在忙什么？")
                if message["name"] == "natural_role_texture"
            )["content"]
        )

    ras = render("Wizard", ["Romanceable Rasmodius"])
    sophia = render("Sophia", ["Stardew Valley Expanded"])

    assert ras["rhythmProfile"] != sophia["rhythmProfile"]
    assert "opening" in ras["rhythmProfile"]
    assert "closing" in sophia["rhythmProfile"]
    assert "判断" in ras["rhythmProfile"]["opening"]
    assert "感官" in sophia["rhythmProfile"]["opening"]
    assert "提醒" in ras["rhythmProfile"]["closing"]
    assert "选择权" in sophia["rhythmProfile"]["closing"]


def test_natural_role_texture_keeps_original_anchors_for_non_sophia_continuation() -> None:
    """自然续聊也要保留少量当前角色原文，不能只剩抽象 persona 规则。"""

    context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "stageProfile": {"stage": "close"},
            "voiceStyle": {
                "tone": "直白、疲惫，习惯用干巴巴的玩笑挡一下脆弱",
                "sentencePattern": ["先给短答再决定是否展开"],
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "voiceCard": {
            "npcId": "Shane",
            "voiceAnchors": [
                {
                    "sourceKey": "Mon10",
                    "sourceMod": "vanilla",
                    "text": "我只是想确认你没把自己累垮。就这样。",
                },
                {
                    "sourceKey": "Tue8",
                    "sourceMod": "vanilla",
                    "text": "我今天没心情解释太多。",
                },
            ],
        },
        "history": [
            {"role": "user", "content": "你还在鸡舍吗？"},
            {"role": "assistant", "content": "嗯，还在。"},
        ],
    }

    messages = PromptBuilder().build(context, "那你先忙。")
    role = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "natural_role_texture"
        )["content"]
    )

    assert [item["sourceKey"] for item in role["voiceAnchors"]] == [
        "Mon10",
        "Tue8",
    ]
    assert "originalTextFit" in role
    assert "只借一个表达动作" in role["originalTextFit"]["selection"]
    assert not any(
        message["name"] == "sophia_liveliness_final" for message in messages
    )


def test_natural_role_texture_falls_back_to_filtered_style_samples_when_voice_card_is_empty() -> None:
    """阶段校准过滤掉整张 voiceCard 时，仍要保留角色自己的短原文。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
            "turnPlan": {"mode": "answer_only"},
        },
        "interaction": {"intent": "topic", "channel": "face_to_face"},
        "voiceCard": {"npcId": "Elliott", "voiceAnchors": []},
        "styleSamples": [
            {
                "sourceKey": "Fri4",
                "sourceMod": "vanilla",
                "text": "嘿……别拿着个火把离我头发这么近……",
            },
            {
                "sourceKey": "Sat4",
                "sourceMod": "vanilla",
                "text": "请原谅我这里这么乱。",
            },
        ],
        "history": [],
    }

    messages = PromptBuilder().build(context, "")
    role = json.loads(
        next(
            message
            for message in messages
            if message["name"] == "natural_role_texture"
        )["content"]
    )

    assert [item["sourceKey"] for item in role["voiceAnchors"]] == [
        "Fri4",
        "Sat4",
    ]
    assert "originalTextFit" in role


def test_natural_contract_defers_sentence_shape_to_role_signature_moves() -> None:
    """公共自然契约不能再把所有角色压成同一套开头和展开顺序。"""

    context = {
        "npcIdentity": {"npcId": "Wizard", "displayName": "Rasmodia"},
        "qualityContext": {"naturalMode": True, "turnPlan": {"mode": "answer_only"}},
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    natural_contract = next(
        message
        for message in PromptBuilder().build(context, "你最近在忙什么？")
        if message["name"] == "natural_dialogue_contract"
    )["content"]

    assert "公共契约只定义边界，不规定句式" in natural_contract
    assert "signatureMoves" in natural_contract


def test_natural_mode_removes_fixed_length_and_redundant_generation_cards() -> None:
    """自然模式应把输出交给当前话题，不能再叠加格式预算和重复尾卡。"""

    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Elliott", "married"),
            "voiceStyle": {
                "tone": "安静、具体",
                "sentencePattern": ["偶尔短收"],
                "responseRules": ["先回答眼前的话"],
            },
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_plus_detail"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {},
        "history": [],
    }

    messages = PromptBuilder().build(context, "那页稿子后来改完了吗？")
    names = [message["name"] for message in messages]
    safety = next(message for message in messages if message["name"] == "safety_rules")[
        "content"
    ]

    assert "中文 1–3 句" not in safety
    assert "通常 15–80 字" not in safety
    assert "按当前内容自然收住" in safety
    assert "voice_execution_card" not in names
    assert "final_role_voice_contract" not in names
    assert "player_echo_guard" not in names
    assert "natural_detail_override" not in names


def test_prompt_exposes_the_current_turn_plan_before_player_input() -> None:
    """当前回合只应把一个明确的行为目标交给模型。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "initiativeExpectation": "proactive",
            "initiativeKind": "affection_signal",
            "turnPlan": {"mode": "answer_plus_warmth", "intensity": "light"},
        },
        "gameState": {},
        "recentFacts": [],
        "history": [],
    }

    messages = PromptBuilder().build(context, "你今天怎么这么安静？")
    names = [message["name"] for message in messages]
    turn_plan = next(message for message in messages if message["name"] == "turn_plan")
    payload = json.loads(turn_plan["content"])

    assert payload["mode"] == "answer_plus_warmth"
    assert names.index("turn_plan") < names.index("player_input")


def test_elliott_adaptive_calibration_adds_local_original_rhythm_card() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
        },
        "gameState": {"relationshipStage": "married"},
        "history": [],
    }

    messages = PromptBuilder().build(context, "稿子写得怎么样？")
    names = [message["name"] for message in messages]
    rhythm_card = next(
        message for message in messages if message["name"] == "elliott_rhythm_card"
    )

    assert names.index("elliott_rhythm_card") < names.index("player_input")
    assert "先回答眼前对象" in rhythm_card["content"]
    assert "不要刻意停顿或改口" in rhythm_card["content"]
    assert "不把普通分享写成警句" in rhythm_card["content"]


def test_elliott_rhythm_card_is_opt_in_and_does_not_change_other_natural_cases() -> None:
    base_context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {"naturalMode": True},
        "gameState": {"relationshipStage": "married"},
        "history": [],
    }
    other_context = {
        **base_context,
        "npcIdentity": {**base_context["npcIdentity"], "npcId": "Alex", "displayName": "Alex"},
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
        },
    }

    base_names = [message["name"] for message in PromptBuilder().build(base_context, "你好")]
    other_names = [
        message["name"] for message in PromptBuilder().build(other_context, "你好")
    ]

    assert "elliott_rhythm_card" not in base_names
    assert "elliott_rhythm_card" not in other_names


def test_elliott_rhythm_card_blocks_unanchored_objects_intimacy_and_plans() -> None:
    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
        },
        "gameState": {"relationshipStage": "married"},
        "history": [],
    }

    rhythm_card = next(
        message
        for message in PromptBuilder().build(context, "嗯，我在听。")
        if message["name"] == "elliott_rhythm_card"
    )

    assert "不要凭空切换新物件、亲密动作或未来安排" in rhythm_card["content"]


def test_natural_passive_chat_drops_redundant_relationship_cards() -> None:
    """自然轻续聊不能把同一条收口要求重复塞进三张关系卡。"""

    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Elliott", "married"),
        },
        "qualityContext": {
            "naturalMode": True,
            "initiativeExpectation": "responsive",
            "initiativeKind": "none",
            "turnPlan": {"mode": "answer_only", "intensity": "light"},
            "continuationMode": "anchored",
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {"relationshipStage": "married"},
        "history": [],
    }

    names = [
        message["name"]
        for message in PromptBuilder().build(context, "那页后来留着吗？")
    ]

    assert "stage_execution_card" in names
    assert "affection_initiative" not in names
    assert "conversation_lead" not in names
    assert "affection_priority_final" not in names


def test_natural_continuation_discourages_unprompted_future_arrangements() -> None:
    """自然续聊不能把玩家的当前动作扩写成等待承诺或未来邀约。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "continuationMode": "anchored",
            "topicSeed": "共同阅读",
            "topicKeywords": ["章节", "读"],
            "turnPlan": {"mode": "answer_only", "intensity": "light"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {"relationshipStage": "married"},
        "history": [],
    }

    contract = json.loads(
        next(
            message
            for message in PromptBuilder().build(context, "嗯，那我先不翻。")
            if message["name"] == "continuation_contract"
        )["content"]
    )

    assert "除非玩家明确询问或提出安排" in contract["instruction"]
    assert "未来承诺" in contract["instruction"]
    assert "不要把玩家上一句改成‘那正好……’" in contract["instruction"]


def test_natural_answer_only_keeps_a_concrete_acknowledgement_anchor() -> None:
    """自然短答可以很短，但不能只留下无对象的空确认。"""

    context = {
        "npcIdentity": {
            "npcId": "Elliott",
            "displayName": "Elliott",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {
            "naturalMode": True,
            "turnPlan": {"mode": "answer_only", "intensity": "light"},
        },
        "interaction": {"intent": "chat", "channel": "remote"},
        "gameState": {"relationshipStage": "married"},
        "history": [],
    }

    turn_plan = json.loads(
        next(
            message
            for message in PromptBuilder().build(
                context, "那我先去倒杯水，你等我一下？"
            )
            if message["name"] == "turn_plan"
        )["content"]
    )

    assert "不能只回无对象的‘嗯’‘好’‘行’" in turn_plan["instruction"]
    assert "当前对象、动作或明确态度" in turn_plan["instruction"]


def test_natural_literary_style_is_local_to_elliott_rhythm_card() -> None:
    """公共自然对白契约不应把文学感要求扩散到其他角色。"""

    shane_context = {
        "npcIdentity": {
            "npcId": "Shane",
            "displayName": "Shane",
            "stageProfile": {"stage": "married"},
        },
        "qualityContext": {"naturalMode": True},
        "gameState": {"relationshipStage": "married"},
        "history": [],
    }
    shane_contract = next(
        message
        for message in PromptBuilder().build(shane_context, "今天还好吗？")
        if message["name"] == "natural_dialogue_contract"
    )["content"]

    elliott_context = {
        **shane_context,
        "npcIdentity": {
            **shane_context["npcIdentity"],
            "npcId": "Elliott",
            "displayName": "Elliott",
        },
        "qualityContext": {
            "naturalMode": True,
            "styleCalibration": "elliott_original_rhythm",
        },
    }
    elliott_card = next(
        message
        for message in PromptBuilder().build(elliott_context, "今天还好吗？")
        if message["name"] == "elliott_rhythm_card"
    )["content"]

    assert "保留角色已有的文学感" not in shane_contract
    assert "具体意象" in elliott_card
    assert "比喻" in elliott_card
