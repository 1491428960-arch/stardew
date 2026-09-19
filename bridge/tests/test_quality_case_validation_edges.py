"""`character_quality_eval.validate_quality_cases` 的案例合法性校验。

2026-09-20 用覆盖率定位到 `character_quality_eval.py` 92%，未覆盖的行密集在
**L681–756**——那是 `validate_quality_cases` 里**各条校验规则的报错分支**。它保证
**评测数据本身是合法的**：判错了，整批评测结论就不可信。

两点值得单独说：

- **真实案例集（47 个）当前全部通过校验**——这既是有用的基线，也能在将来有人
  改坏案例时立刻报警。
- 校验函数**只看案例、不看模型输出**（docstring 明确写了“不触碰模型输出”），
  所以它可以在跑任何云端批次**之前**离线检查。

测试用 `dataclasses.replace` 改真实案例，而不是手工构造 8 个必填字段——后者容易
在字段默认值变化时失真。
"""

from __future__ import annotations

import dataclasses

import pytest

from stardew_ai_bridge.character_quality_eval import (
    DEFAULT_CASES,
    CharacterQualityCase,
    validate_quality_cases,
)

_BASE_ID = DEFAULT_CASES[0].case_id


def _case(**overrides: object) -> CharacterQualityCase:
    return dataclasses.replace(DEFAULT_CASES[0], **overrides)


# --- 基线与入口 -------------------------------------------------------------


def test_the_shipped_cases_all_pass_validation() -> None:
    # 47 个真实案例是评测的输入；它们必须干净，否则整批结论不可信。
    assert validate_quality_cases(DEFAULT_CASES) == []


def test_a_single_valid_case_yields_no_errors() -> None:
    assert validate_quality_cases([_case()]) == []


def test_validation_returns_errors_instead_of_raising() -> None:
    # 它服务于“跑批次前先离线检查”，数据坏掉时应当给出清单而不是抛异常。
    errors = validate_quality_cases([_case(relationship_stage="nonsense")])

    assert errors == [f"invalid:relationship_stage:{_BASE_ID}"]


def test_duplicate_case_ids_are_reported() -> None:
    errors = validate_quality_cases([_case(), _case()])

    assert errors == [f"duplicate:case_id:{_BASE_ID}"]


# --- 各条规则（每条只钉“会报出对应前缀”）-----------------------------------


@pytest.mark.parametrize(
    ("overrides", "prefix"),
    [
        ({"relationship_stage": "nonsense"}, "invalid:relationship_stage:"),
        ({"channel": "nonsense"}, "invalid:channel:"),
        ({"intent": "nonsense"}, "invalid:intent:"),
        ({"flirt_intensity": "nonsense"}, "invalid:flirt_intensity:"),
        ({"continuation_mode": "nonsense"}, "invalid:continuation_mode:"),
        ({"follow_up_mode": "nonsense"}, "invalid:follow_up_mode:"),
        ({"relationship_context": "   "}, "relationship_context:"),
    ],
)
def test_enum_fields_report_invalid_values(
    overrides: dict[str, object], prefix: str
) -> None:
    errors = validate_quality_cases([_case(**overrides)])

    assert any(error.startswith(prefix) for error in errors), errors


def test_consensual_adult_content_requires_a_romance_eligible_case() -> None:
    errors = validate_quality_cases(
        [_case(adult_consensual=True, romance_eligible=False)]
    )

    assert any(
        error.startswith("adult_consensual_requires_romance:") for error in errors
    ), errors


def test_flirtation_requires_a_romance_eligible_case() -> None:
    errors = validate_quality_cases([_case(flirt_intensity="light", romance_eligible=False)])

    assert any(error.startswith("romance_eligible:") for error in errors), errors


def test_close_stages_require_enough_hearts() -> None:
    # dating/married/parent 的案例必须真的到了那个关系程度。
    errors = validate_quality_cases(
        [_case(relationship_stage="married", friendship_hearts=1)]
    )

    assert any(error.startswith("friendship_hearts:") for error in errors), errors


def test_a_blank_context_is_rejected_but_an_empty_one_is_derived() -> None:
    # 实测发现的一个区别：空白串被判为“没写上下文”，而**空串会走派生逻辑**
    # （`_case_relationship_context` 会从阶段/NPC 组装出默认文本），所以两者行为不同。
    assert validate_quality_cases([_case(relationship_context="   ")]) != []
    assert validate_quality_cases([_case(relationship_context="")]) == []


# --- relationship_world 的结构校验 ------------------------------------------


def test_relationship_world_must_be_a_mapping() -> None:
    errors = validate_quality_cases([_case(relationship_world="不是映射")])

    assert any(error.startswith("invalid:relationship_world:") for error in errors), errors


def test_relationship_views_must_be_a_list() -> None:
    errors = validate_quality_cases([_case(relationship_world={"views": "不是列表"})])

    assert any(error.startswith("invalid:relationship_views:") for error in errors), errors


def test_each_view_must_be_a_mapping() -> None:
    errors = validate_quality_cases([_case(relationship_world={"views": ["不是映射"]})])

    assert any(error.startswith("invalid:relationship_view:") for error in errors), errors


def test_visibility_must_be_a_known_value() -> None:
    errors = validate_quality_cases(
        [_case(relationship_world={"views": [{"visibility": "nonsense"}]})]
    )

    assert any(
        error.startswith("invalid:relationship_visibility:") for error in errors
    ), errors


@pytest.mark.parametrize(
    "world",
    [
        {"views": [{"visibility": "known"}]},
        {"views": [{"visibility": "suspected"}, {"visibility": "unknown"}]},
        {"views": []},
    ],
)
def test_a_well_formed_relationship_world_is_accepted(world: dict[str, object]) -> None:
    assert validate_quality_cases([_case(relationship_world=world)]) == []


# --- 露骨调情的两道额外门槛 -------------------------------------------------


def test_direct_flirtation_requires_a_close_relationship_stage() -> None:
    # direct/explicit 只能出现在 dating 或 married 阶段。
    errors = validate_quality_cases(
        [_case(flirt_intensity="direct", relationship_stage="acquaintance")]
    )

    assert any(error.startswith("relationship_stage:") for error in errors), errors


def test_direct_flirtation_requires_explicit_consent() -> None:
    errors = validate_quality_cases(
        [
            _case(
                flirt_intensity="explicit",
                relationship_stage="married",
                friendship_hearts=10,
                adult_consensual=False,
            )
        ]
    )

    assert any(error.startswith("adult_consensual:") for error in errors), errors


def test_an_eligible_consensual_dating_case_passes() -> None:
    # 反向对照：关系到位 + 明确同意时不该报这两条错。
    errors = validate_quality_cases(
        [
            _case(
                flirt_intensity="explicit",
                relationship_stage="dating",
                friendship_hearts=10,
                adult_consensual=True,
            )
        ]
    )

    assert not any(
        error.startswith(("relationship_stage:", "adult_consensual:"))
        for error in errors
    ), errors
