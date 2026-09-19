"""`merge_persona` 的覆盖层去重身份（B11）。

2026-09-20 修。原实现用**原始** overlay 键做去重（`marker_key in applied_markers`），
但**匹配**是归一化的——于是 `"SVE"` 与 `"  SVE  "` 这两个**语义相同**的键会各自通过检查，
同一份覆盖层被 `_deep_merge` 应用**两次**。

**后果与直觉不同**（实测确认后才这么写）：`_deep_merge` 对**列表与标量是替换**、
对**嵌套字典是递归合并**——所以：

- 平铺字段（列表／标量）看起来"没坏"，只是**后者覆盖前者**；
- **嵌套字典会把两处内容都并进来**（`{"k":1,"fromA":True,"fromB":True}`），这才是真问题。

顺带一提：B11 原本把位置记成 `app.py`，实际在 `bridge/src/stardew_ai_bridge/personas.py`。
"""

from __future__ import annotations

from stardew_ai_bridge.personas import merge_persona


def _persona(overlays: dict[str, object], **extra: object) -> dict[str, object]:
    return {"npcId": "Shane", "modOverlay": overlays, **extra}


# --- 修掉的问题 -------------------------------------------------------------


def test_equivalent_keys_apply_the_overlay_only_once() -> None:
    # 两个键语义相同（归一化后都是 "sve"），只能生效一次。
    persona = _persona(
        {
            "SVE": {"nested": {"fromFirst": True}},
            "  SVE  ": {"nested": {"fromSecond": True}},
        }
    )

    merged = merge_persona(persona, ["SVE"])

    assert merged["nested"] == {"fromFirst": True}


def test_only_one_overlay_key_is_recorded() -> None:
    persona = _persona({"SVE": {"nested": {"a": 1}}, "  SVE  ": {"nested": {"b": 2}}})

    merged = merge_persona(persona, ["SVE"])

    # 保留的是**第一个遇到的原始写法**，而不是两个都记下来
    assert list(merged["modOverlay"]) == ["SVE"]


def test_case_only_differences_are_also_deduplicated() -> None:
    persona = _persona({"sve": {"nested": {"a": 1}}, "SVE": {"nested": {"b": 2}}})

    assert merge_persona(persona, ["SVE"])["nested"] == {"a": 1}


def test_a_repeated_source_mod_does_not_double_apply() -> None:
    # 既有的正确行为，不该被这次修改破坏。
    persona = _persona({"SVE": {"nested": {"a": 1}}})

    merged = merge_persona(persona, ["SVE", "  sve  "])

    assert merged["nested"] == {"a": 1}
    assert list(merged["modOverlay"]) == ["SVE"]


# --- 不能误伤 ---------------------------------------------------------------


def test_distinct_overlays_all_still_apply() -> None:
    persona = _persona(
        {
            "SVE": {"nested": {"fromSve": True}},
            "Ridgeside": {"nested": {"fromRidgeside": True}},
        }
    )

    merged = merge_persona(persona, ["SVE", "Ridgeside"])

    assert merged["nested"] == {"fromSve": True, "fromRidgeside": True}
    assert set(merged["modOverlay"]) == {"SVE", "Ridgeside"}


def test_an_unlisted_mod_is_still_not_applied() -> None:
    persona = _persona({"SVE": {"nested": {"a": 1}}, "Other": {"nested": {"b": 2}}})

    merged = merge_persona(persona, ["SVE"])

    assert merged["nested"] == {"a": 1}
    assert list(merged["modOverlay"]) == ["SVE"]


def test_flat_fields_keep_the_documented_replace_behaviour() -> None:
    # 平铺字段是替换语义（不是追加）——把这一点也钉住，免得有人按“追加”去理解。
    persona = _persona(
        {"SVE": {"traits": ["x"]}, "  SVE  ": {"traits": ["y"]}},
        traits=["base"],
    )

    assert merge_persona(persona, ["SVE"])["traits"] == ["x"]
