from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "data" / "personas" / "behavior-quality-scenarios.json"


def _load_cli_module():
    path = ROOT / "scripts" / "generate_behavior_examples.py"
    spec = importlib.util.spec_from_file_location(
        "generate_behavior_examples",
        path,
    )
    if spec is None or spec.loader is None:
        pytest.fail("无法加载行为样本生成 CLI")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_scenarios(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "scenarios": [
                    {
                        "scenarioId": "shane-acquaintance-coop",
                        "npcId": "Shane",
                        "displayName": "Shane",
                        "sourceMods": ["vanilla"],
                        "relationshipStage": "acquaintance",
                        "channel": "face_to_face",
                        "topic": "chicken",
                        "speechFunction": "answer_directly",
                        "emotion": "tired_dry_humor",
                        "playerInput": "鸡舍今天忙吗？",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class DeterministicGenerator:
    def __init__(self, reply: str = "还行。没着火，就算顺利。") -> None:
        self.reply = reply
        self.calls: list[list[dict[str, str]]] = []

    def generate(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        name = messages[0]["name"]
        if name == "draft":
            return json.dumps(
                {
                    "exampleId": "draft-001",
                    "npcReply": self.reply,
                },
                ensure_ascii=False,
            )
        if name == "review":
            return json.dumps(
                {
                    "stardewVoice": 2,
                    "characterDistinctiveness": 2,
                    "relationshipFit": 2,
                    "channelFit": 2,
                    "topicResponse": 2,
                    "contextContinuity": 2,
                    "naturalChinese": 2,
                    "boundarySafety": 2,
                    "hardErrors": [],
                    "tags": [],
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"测试生成器收到未知消息：{name}")


def test_cli_does_not_write_approved_samples_without_explicit_ids(
    tmp_path: Path,
) -> None:
    module = _load_cli_module()
    scenario_path = tmp_path / "scenarios.json"
    output_dir = tmp_path / "run"
    _write_scenarios(scenario_path)

    result = module.run_cli(
        scenario_path=scenario_path,
        output_dir=output_dir,
        generator=DeterministicGenerator(),
    )

    assert result.approved == []
    assert (output_dir / "candidates.jsonl").is_file()
    assert (output_dir / "reviews.jsonl").is_file()
    assert (output_dir / "revisions.jsonl").is_file()
    assert (output_dir / "run-summary.json").is_file()
    assert not (output_dir / "approved.json").exists()
    assert not (ROOT / "data" / "personas" / "behavior-examples.json").samefile(
        output_dir / "candidates.jsonl"
    )


def test_cli_writes_approved_samples_only_for_explicit_reviewed_ids(
    tmp_path: Path,
) -> None:
    module = _load_cli_module()
    scenario_path = tmp_path / "scenarios.json"
    output_dir = tmp_path / "run"
    _write_scenarios(scenario_path)

    result = module.run_cli(
        scenario_path=scenario_path,
        output_dir=output_dir,
        generator=DeterministicGenerator(),
        approve_ids=("draft-001",),
    )

    assert [item["exampleId"] for item in result.approved] == ["draft-001"]
    approved_path = output_dir / "approved.json"
    assert approved_path.is_file()
    approved = json.loads(approved_path.read_text(encoding="utf-8"))
    assert [item["exampleId"] for item in approved] == ["draft-001"]


def test_cli_artifacts_never_contain_secret_values_or_full_prompt(
    tmp_path: Path,
) -> None:
    module = _load_cli_module()
    scenario_path = tmp_path / "scenarios.json"
    output_dir = tmp_path / "run"
    _write_scenarios(scenario_path)

    module.run_cli(
        scenario_path=scenario_path,
        output_dir=output_dir,
        generator=DeterministicGenerator(
            "apiKey=secret-token token=secret-token prompt=secret-prompt"
        ),
    )

    rendered = "".join(
        path.read_text(encoding="utf-8")
        for path in output_dir.iterdir()
        if path.is_file()
    )
    assert "secret-token" not in rendered
    assert "secret-prompt" not in rendered
    assert '"request"' not in rendered


def test_scenario_catalog_uses_five_profiles_and_one_wizard_identity() -> None:
    module = _load_cli_module()
    catalog = module.load_scenarios(SCENARIOS)

    assert {
        scenario["profileKey"]
        for scenario in catalog
    } == {
        "wizard_rasmodia",
        "sophia",
        "shane",
        "sebastian",
        "alex",
    }
    wizard_ids = {
        scenario["npcId"]
        for scenario in catalog
        if scenario["profileKey"] == "wizard_rasmodia"
    }
    assert wizard_ids == {"Wizard"}


def test_repository_behavior_examples_cover_high_affection_for_all_eight_roles() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = payload["examples"]
    major_npcs = {
        "Wizard",
        "Sophia",
        "Shane",
        "Sebastian",
        "Alex",
        "Elliott",
        "Harvey",
        "Sam",
    }

    for npc_id in major_npcs:
        high_stage = [
            example
            for example in examples
            if example.get("npcId") == npc_id
            and set(example.get("relationshipStages", []))
            & {"dating", "married"}
        ]
        assert {stage for example in high_stage for stage in example["relationshipStages"]} >= {
            "dating",
            "married",
        }, npc_id

    for npc_id in {"Shane", "Sebastian", "Alex", "Elliott", "Harvey", "Sam"}:
        overlay_examples = [
            example
            for example in examples
            if example.get("npcId") == npc_id
            and set(example.get("relationshipStages", []))
            & {"dating", "married"}
        ]
        assert overlay_examples
        assert all(
            "female-bachelors" in example.get("sourceMods", [])
            for example in overlay_examples
        ), npc_id


def test_repository_behavior_examples_cover_the_first_normal_vanilla_batch() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = payload["examples"]
    new_roles = {"Abigail", "Emily", "Haley", "Leah"}

    for npc_id in new_roles:
        role_examples = [
            example for example in examples if example.get("npcId") == npc_id
        ]
        assert len(role_examples) >= 2, npc_id
        assert all(example.get("sourceMods") == ["vanilla"] for example in role_examples)
        assert all(
            example.get("sourceType") == "handcrafted_example"
            for example in role_examples
        )
        assert all("female-bachelors" not in example.get("sourceMods", []) for example in role_examples)
        assert all(example.get("playerInput") and example.get("npcReply") for example in role_examples)


def test_repository_behavior_examples_cover_the_second_normal_vanilla_batch() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = payload["examples"]
    new_roles = {"Penny", "Maru", "Jodi", "Robin"}

    for npc_id in new_roles:
        role_examples = [
            example for example in examples if example.get("npcId") == npc_id
        ]
        assert len(role_examples) >= 2, npc_id
        assert all(example.get("sourceMods") == ["vanilla"] for example in role_examples)
        assert all(
            example.get("sourceType") == "handcrafted_example"
            for example in role_examples
        )
        assert all("female-bachelors" not in example.get("sourceMods", []) for example in role_examples)
        assert all(example.get("playerInput") and example.get("npcReply") for example in role_examples)
        assert all(
            not any(marker in example["npcReply"] for marker in ("未来", "预约", "排期", "日程"))
            for example in role_examples
        )


def test_repository_behavior_examples_cover_the_third_normal_vanilla_batch() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = payload["examples"]
    new_roles = {"Clint", "Demetrius", "Evelyn", "George"}

    for npc_id in new_roles:
        role_examples = [
            example for example in examples if example.get("npcId") == npc_id
        ]
        assert len(role_examples) >= 2, npc_id
        assert all(example.get("sourceMods") == ["vanilla"] for example in role_examples)
        assert all(
            example.get("sourceType") == "handcrafted_example"
            for example in role_examples
        )
        assert all("female-bachelors" not in example.get("sourceMods", []) for example in role_examples)
        assert all(example.get("playerInput") and example.get("npcReply") for example in role_examples)
        assert all(
            not any(marker in example["npcReply"] for marker in ("未来", "预约", "排期", "日程"))
            for example in role_examples
        )


def test_repository_behavior_examples_cover_the_fourth_normal_vanilla_batch() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = payload["examples"]
    new_roles = {"Gus", "Kent", "Lewis", "Pam"}

    for npc_id in new_roles:
        role_examples = [
            example for example in examples if example.get("npcId") == npc_id
        ]
        assert len(role_examples) >= 2, npc_id
        assert all(example.get("sourceMods") == ["vanilla"] for example in role_examples)
        assert all(
            example.get("sourceType") == "handcrafted_example"
            for example in role_examples
        )
        assert all("female-bachelors" not in example.get("sourceMods", []) for example in role_examples)
        assert all(example.get("playerInput") and example.get("npcReply") for example in role_examples)
        assert all(
            not any(marker in example["npcReply"] for marker in ("未来", "预约", "排期", "日程"))
            for example in role_examples
        )


def test_repository_behavior_examples_cover_the_fifth_normal_vanilla_batch() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = payload["examples"]
    new_roles = {"Pierre", "Sandy", "Willy", "Dwarf"}

    for npc_id in new_roles:
        role_examples = [
            example for example in examples if example.get("npcId") == npc_id
        ]
        assert len(role_examples) >= 2, npc_id
        assert all(example.get("sourceMods") == ["vanilla"] for example in role_examples)
        assert all(
            example.get("sourceType") == "handcrafted_example"
            for example in role_examples
        )
        assert all("female-bachelors" not in example.get("sourceMods", []) for example in role_examples)
        assert all(example.get("playerInput") and example.get("npcReply") for example in role_examples)
        assert all(
            not any(marker in example["npcReply"] for marker in ("未来", "预约", "排期", "日程"))
            for example in role_examples
        )


def test_repository_behavior_examples_cover_the_sixth_normal_vanilla_batch() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = payload["examples"]
    new_roles = {"Krobus", "Jas", "Vincent"}

    for npc_id in new_roles:
        role_examples = [
            example for example in examples if example.get("npcId") == npc_id
        ]
        assert len(role_examples) >= 2, npc_id
        assert all(example.get("sourceMods") == ["vanilla"] for example in role_examples)
        assert all(
            example.get("sourceType") == "handcrafted_example"
            for example in role_examples
        )
        assert all("female-bachelors" not in example.get("sourceMods", []) for example in role_examples)
        assert all(example.get("playerInput") and example.get("npcReply") for example in role_examples)
        assert all(
            not any(marker in example["npcReply"] for marker in ("未来", "预约", "排期", "日程"))
            for example in role_examples
        )


def test_repository_behavior_examples_cover_the_special_vanilla_batch() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = payload["examples"]
    new_roles = {"Leo", "Gunther", "Marlon", "Birdie"}

    for npc_id in new_roles:
        role_examples = [
            example for example in examples if example.get("npcId") == npc_id
        ]
        assert len(role_examples) >= 2, npc_id
        assert all(example.get("sourceMods") == ["vanilla"] for example in role_examples)
        assert all(
            example.get("sourceType") == "handcrafted_example"
            for example in role_examples
        )
        assert all("female-bachelors" not in example.get("sourceMods", []) for example in role_examples)
        assert all(example.get("playerInput") and example.get("npcReply") for example in role_examples)
        assert all(
            not any(marker in example["npcReply"] for marker in ("未来", "预约", "排期", "日程"))
            for example in role_examples
        )


def test_existing_normal_vanilla_roles_have_handcrafted_behavior_examples() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = payload["examples"]

    for npc_id in {"Caroline", "Marnie", "Linus"}:
        role_examples = [
            example for example in examples if example.get("npcId") == npc_id
        ]
        assert len(role_examples) >= 2, npc_id
        assert all(example.get("sourceMods") == ["vanilla"] for example in role_examples)
        assert all(example.get("sourceType") == "handcrafted_example" for example in role_examples)


def test_high_stage_behavior_examples_make_affection_explicit_without_recap_template() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    high_stage = [
        example
        for example in payload["examples"]
        if set(example.get("relationshipStages", [])) & {"dating", "married"}
    ]
    warmth_markers = (
        "想你",
        "想和你",
        "想让你",
        "陪你",
        "陪我",
        "给你留",
        "留给你",
        "留给我",
        "靠近一点",
        "高兴",
        "在意",
        "喜欢",
        "期待",
        "最想听你的",
    )
    recap_markers = ("你说得", "你说的", "听起来你", "所以你的意思")

    assert high_stage
    assert all(
        any(marker in example["npcReply"] for marker in warmth_markers)
        for example in high_stage
    )
    assert all(
        not any(marker in example["npcReply"] for marker in recap_markers)
        for example in high_stage
    )


def test_repository_contains_one_short_voice_distinctiveness_example_per_role() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = {example["exampleId"]: example for example in payload["examples"]}
    expected = {
        "wizard:voice-distinctiveness:01": ("Wizard", "简短判断"),
        "sophia:voice-distinctiveness:01": ("Sophia", "具体细节"),
        "shane:voice-distinctiveness:01": ("Shane", "自嘲"),
        "sebastian:voice-distinctiveness:01": ("Sebastian", "冷幽默"),
        "alex:voice-distinctiveness:01": ("Alex", "轻微挑战"),
        "elliott:voice-distinctiveness:01": ("Elliott", "具体物件"),
        "harvey:voice-distinctiveness:01": ("Harvey", "实际照料"),
        "sam:voice-distinctiveness:01": ("Sam", "音乐行动"),
        "victor:voice-distinctiveness:01": ("Victor", "工程细节"),
        "olivia:voice-distinctiveness:01": ("Olivia", "生活判断"),
        "andy:voice-distinctiveness:01": ("Andy", "务实行动"),
        "lance:voice-distinctiveness:01": ("Lance", "冒险见闻"),
        "claire:voice-distinctiveness:01": ("Claire", "谨慎新生"),
        "morris:voice-distinctiveness:01": ("Morris", "经营结果"),
    }

    assert set(expected) <= set(examples)
    for example_id, (npc_id, _voice_move) in expected.items():
        example = examples[example_id]
        assert example["npcId"] == npc_id
        assert example["sourceType"] in {"handcrafted_example", "human_approved"}
        assert example["playerInput"]
        assert example["npcReply"]
        assert example["topicKeywords"]
        assert len(example["npcReply"]) <= 60
        assert not any(marker in example["npcReply"] for marker in ("未来", "排期", "预约"))


def test_normal_sve_batch_behavior_examples_keep_normal_source_and_gender() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = {
        example["npcId"]: example
        for example in payload["examples"]
        if example.get("exampleId", "").endswith(":voice-distinctiveness:01")
        and example.get("npcId") in {"Victor", "Olivia", "Andy"}
    }

    assert set(examples) == {"Victor", "Olivia", "Andy"}
    for example in examples.values():
        assert example["sourceMods"] == ["SVE"]
        assert example["sourceType"] == "handcrafted_example"
        assert set(example["relationshipStages"]) <= {"acquaintance", "friend", "close"}
        assert "female-bachelors" not in example["sourceMods"]
        assert example["npcReply"]
        assert not any(marker in example["npcReply"] for marker in ("未来", "排期", "预约"))


def test_second_normal_sve_batch_behavior_examples_keep_normal_source_and_gender() -> None:
    payload = json.loads(
        (ROOT / "data" / "personas" / "behavior-examples.json").read_text(
            encoding="utf-8"
        )
    )
    examples = {
        example["npcId"]: example
        for example in payload["examples"]
        if example.get("exampleId", "").endswith(":voice-distinctiveness:01")
        and example.get("npcId") in {"Lance", "Claire", "Morris"}
    }

    assert set(examples) == {"Lance", "Claire", "Morris"}
    for example in examples.values():
        assert example["sourceMods"] == ["SVE"]
        assert example["sourceType"] == "handcrafted_example"
        assert set(example["relationshipStages"]) <= {"acquaintance", "friend", "close"}
        assert "female-bachelors" not in example["sourceMods"]
        assert example["npcReply"]
        assert not any(marker in example["npcReply"] for marker in ("未来", "排期", "预约"))


def test_quality_scenarios_cover_high_stage_multiturn_story_metadata() -> None:
    payload = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"]
    major_npcs = {"Wizard", "Sophia", "Shane", "Sebastian", "Alex"}
    high_stage = [
        scenario
        for scenario in scenarios
        if scenario.get("npcId") in major_npcs
        and scenario.get("relationshipStage") in {"dating", "married"}
    ]

    assert {scenario["npcId"] for scenario in high_stage} == major_npcs
    assert all(scenario.get("friendshipHearts", 0) >= 8 for scenario in high_stage)
    assert all(len(scenario.get("turns", [])) == 3 for scenario in high_stage)
    assert all(scenario.get("relationshipContext") for scenario in high_stage)
    assert any(scenario.get("completedEventIds") for scenario in high_stage)
    assert all(
        scenario.get("genderPresentation") == "female-bachelors"
        for scenario in high_stage
        if scenario["npcId"] in {"Shane", "Sebastian", "Alex"}
    )
    assert all(
        scenario.get("initiativeExpectation") in {"proactive", "guarded"}
        and scenario.get("initiativeKind")
        for scenario in high_stage
    )


def test_quality_scenarios_include_shane_guarded_conversation_exit() -> None:
    payload = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    scenario = next(
        item
        for item in payload["scenarios"]
        if item.get("scenarioId") == "shane-dating-remote-exit"
    )

    assert scenario["initiativeExpectation"] == "guarded"
    assert scenario["initiativeKind"] == "conversation_exit"
    assert scenario["channel"] == "remote"
