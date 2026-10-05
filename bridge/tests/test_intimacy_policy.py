"""亲密表达的角色化配置（`intimacyPolicy`）。

2026-10-03：`explicit_intimacy` 指令原先写死「不补写未发生的露骨细节」，且所有角色的
`married` 档只有 `addressing/openness/topicPool/boundaries`，而 `boundaries` 全是收敛项
（「不让漂亮话代替对疲惫的回应」这类），没有任何「这个人怎么表达亲密」的正向描述。
结果是不论角色性格，亲密场景都被压成同一套克制腔。

这里锁三件事：
1. `_compact_stage_profile` 必须透传 `intimacyPolicy`（白名单机制，漏了就等于没写）。
2. 只对 `dating` / `married` 放行 —— 其他阶段不该冒出亲密策略。
3. 数据层：兜底档案与 12 个可攻略角色都要有。
"""

from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.personas import _DEFAULT_STAGE_PROFILES
from stardew_ai_bridge.prompts import _compact_stage_profile

WORKTREE = Path(__file__).resolve().parents[2]
PERSONA_DIR = WORKTREE / "data" / "personas"

ROMANCEABLE = (
    "Alex",
    "Elliott",
    "Harvey",
    "Sam",
    "Sebastian",
    "Shane",
    "Abigail",
    "Emily",
    "Haley",
    "Leah",
    "Maru",
    "Penny",
)

SAMPLE_POLICY = {
    "style": "按这个角色一贯的语气表达，不突然换成通用甜言模板",
    "pace": "一次推进一层",
    "avoidWhen": ["对方没有继续的意思"],
}


def _profile(stage: str, policy: object = SAMPLE_POLICY) -> dict:
    body: dict = {
        "stage": stage,
        "addressing": "亲密而平等",
        "openness": "愿意共同讨论生活决定",
        "topicPool": ["共同生活"],
        "boundaries": ["重要决定需要双方确认"],
    }
    if policy is not None:
        body["intimacyPolicy"] = policy
    return body


# --- 1. 渲染白名单 ---------------------------------------------------------


def test_married_policy_reaches_the_card():
    card = _compact_stage_profile(_profile("married"))
    assert card["intimacyPolicy"]["style"] == SAMPLE_POLICY["style"]
    assert card["intimacyPolicy"]["pace"] == SAMPLE_POLICY["pace"]
    assert card["intimacyPolicy"]["avoidWhen"] == ["对方没有继续的意思"]


def test_dating_policy_reaches_the_card():
    assert "intimacyPolicy" in _compact_stage_profile(_profile("dating"))


def test_policy_is_dropped_outside_romantic_stages():
    for stage in ("stranger", "acquaintance", "friend", "close", "parent"):
        card = _compact_stage_profile(_profile(stage))
        assert "intimacyPolicy" not in card, stage


def test_absent_policy_adds_no_key():
    card = _compact_stage_profile(_profile("married", policy=None))
    assert "intimacyPolicy" not in card


def test_malformed_policy_does_not_raise():
    for bad in ("not a mapping", 42, ["a"], None):
        card = _compact_stage_profile(_profile("married", policy=bad))
        assert "intimacyPolicy" not in card


def test_partial_policy_keeps_only_present_fields():
    card = _compact_stage_profile(_profile("married", policy={"style": "只有风格"}))
    assert card["intimacyPolicy"] == {"style": "只有风格"}


def test_existing_stage_fields_still_render():
    """加字段不能挤掉原有的四件套。"""
    card = _compact_stage_profile(_profile("married"))
    for key in ("addressing", "openness", "topicPool", "boundaries"):
        assert card.get(key), key


# --- 2. 兜底档案 -----------------------------------------------------------


def test_default_profiles_carry_intimacy_for_romantic_stages():
    for stage in ("dating", "married"):
        policy = _DEFAULT_STAGE_PROFILES[stage].get("intimacyPolicy")
        assert isinstance(policy, dict), stage
        assert policy.get("style"), stage
        assert policy.get("pace"), stage
        assert policy.get("avoidWhen"), stage


def test_default_non_romantic_stages_have_no_intimacy():
    for stage in ("stranger", "acquaintance", "friend", "close", "parent"):
        assert "intimacyPolicy" not in _DEFAULT_STAGE_PROFILES[stage], stage


# --- 3. 真实档案 -----------------------------------------------------------


def _load(filename: str) -> dict:
    payload = json.loads((PERSONA_DIR / filename).read_text(encoding="utf-8"))
    return payload.get("personas", payload)


def _stages_with_policy(entry: object) -> dict[str, dict]:
    profiles = entry.get("stageProfiles") if isinstance(entry, dict) else None
    if not isinstance(profiles, dict):
        return {}
    found: dict[str, dict] = {}
    for stage in ("dating", "married"):
        body = profiles.get(stage)
        if isinstance(body, dict) and isinstance(body.get("intimacyPolicy"), dict):
            found[stage] = body["intimacyPolicy"]
    return found


def test_romanceable_vanilla_npcs_have_intimacy_policy():
    """除 Shane 外（vanilla 里他的 stageProfiles 为 null，走兜底档案）。"""
    personas = _load("vanilla.json")
    missing = []
    for npc in ROMANCEABLE:
        if npc == "Shane":
            continue
        found = _stages_with_policy(personas.get(npc))
        if set(found) != {"dating", "married"}:
            missing.append(npc)
    assert missing == [], missing


def test_female_bachelors_overlay_covers_its_own_members():
    personas = _load("female-bachelors.json")
    checked = 0
    for npc, entry in personas.items():
        if npc not in ROMANCEABLE:
            continue
        # 覆盖层里没有 stageProfiles 的成员会回落到 vanilla，不算缺口。
        profiles = entry.get("stageProfiles") if isinstance(entry, dict) else None
        if not isinstance(profiles, dict):
            continue
        found = _stages_with_policy(entry)
        assert set(found) == {"dating", "married"}, npc
        checked += 1
    assert checked > 0


def test_every_policy_is_character_specific_not_shared():
    """「按角色来」的核心断言：每个人的描述必须不同，不能是一份复制品。"""
    personas = _load("vanilla.json")
    styles: dict[str, str] = {}
    for npc in ROMANCEABLE:
        found = _stages_with_policy(personas.get(npc))
        if "married" in found:
            styles[npc] = found["married"]["style"]
    assert len(styles) >= 11
    assert len(set(styles.values())) == len(styles), "存在完全相同的角色描述"
