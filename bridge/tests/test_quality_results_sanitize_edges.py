"""`quality_results` 的数据净化：`_safe_score` 的三处同构白名单。

2026-09-20 用覆盖率定位到 `quality_results.py` 92%，其中 **`L295–304`（`topicMatches` 的净化）
从未执行**——而它与上面两段（`evidenceMatches`、`semanticEvidenceMatches`）**逐行同构**。
典型情况：**三份副本只测了两份**。这里用参数化把三处放在一起断言，既覆盖第三处，
也把“三者行为必须一致”变成契约。

这个模块是**回放页的数据层**：它决定哪些字段能从评测产物进到浏览器。所以白名单之外的键
一律**不出现**，而不是“原样带过去”。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.quality_results import TAG_LIMIT, TAG_TEXT_LIMIT, _safe_score

_TERM_TABLE_KEYS = ("evidenceMatches", "semanticEvidenceMatches", "topicMatches")


# --- 入口与白名单 -----------------------------------------------------------


@pytest.mark.parametrize("value", ["x", None, 42, ["a"]])
def test_non_mapping_score_is_dropped(value: object) -> None:
    assert _safe_score(value) is None


def test_unknown_keys_never_reach_the_browser() -> None:
    # 回放页只需要判定结果；完整回复、prompt 这类字段不该透传。
    assert _safe_score({"reply": "完整回复不该进回放页", "prompt": "x"}) == {}


# --- 布尔与计数 -------------------------------------------------------------


@pytest.mark.parametrize("key", ["passed", "continuity", "topicEvidence"])
def test_boolean_flags_are_kept_only_when_actually_boolean(key: str) -> None:
    assert _safe_score({key: True}) == {key: True}
    assert _safe_score({key: False}) == {key: False}
    # 1 与 "true" 都不是布尔，不能被当成真
    assert _safe_score({key: 1}) == {}
    assert _safe_score({key: "true"}) == {}


@pytest.mark.parametrize(
    "key",
    ["replyLength", "expectedHits", "exactExpectedHits", "semanticExpectedHits", "forbiddenHits"],
)
def test_counters_keep_non_negative_ints_only(key: str) -> None:
    assert _safe_score({key: 3}) == {key: 3}
    assert _safe_score({key: 0}) == {key: 0}
    assert _safe_score({key: -1}) == {}
    assert _safe_score({key: True}) == {}  # bool 不算数字
    assert _safe_score({key: 1.5}) == {}


# --- tags -------------------------------------------------------------------


def test_tags_are_capped_and_truncated() -> None:
    safe = _safe_score({"tags": ["a" * 100] + ["t"] * 30})

    assert safe is not None
    assert len(safe["tags"]) == TAG_LIMIT
    assert len(safe["tags"][0]) == TAG_TEXT_LIMIT


def test_tags_drop_non_strings() -> None:
    safe = _safe_score({"tags": ["ok", 1, None, "fine"]})

    assert safe is not None
    assert safe["tags"] == ["ok", "fine"]


# --- 三处同构的“术语 → 匹配列表”表 ------------------------------------------


@pytest.mark.parametrize("key", _TERM_TABLE_KEYS)
def test_term_tables_drop_non_string_terms_and_matches(key: str) -> None:
    safe = _safe_score(
        {
            key: {
                "term": ["m1", 2, None, "m2"],
                "bad": "不是列表",
                7: ["x"],  # 非字符串术语
            }
        }
    )

    assert safe is not None
    assert safe[key] == {"term": ["m1", "m2"]}


@pytest.mark.parametrize("key", _TERM_TABLE_KEYS)
def test_term_tables_truncate_terms_and_matches(key: str) -> None:
    safe = _safe_score({key: {"x" * 100: ["m" * 100]}})

    assert safe is not None
    table = safe[key]
    assert list(table) == ["x" * TAG_TEXT_LIMIT]
    assert table["x" * TAG_TEXT_LIMIT] == ["m" * TAG_TEXT_LIMIT]


@pytest.mark.parametrize("key", _TERM_TABLE_KEYS)
def test_term_tables_are_capped_at_twenty_terms_and_ten_matches(key: str) -> None:
    safe = _safe_score({key: {f"t{i}": [f"m{j}" for j in range(15)] for i in range(25)}})

    assert safe is not None
    table = safe[key]
    assert len(table) == 20
    assert all(len(matches) == 10 for matches in table.values())


@pytest.mark.parametrize("key", _TERM_TABLE_KEYS)
def test_a_non_mapping_term_table_is_omitted_entirely(key: str) -> None:
    safe = _safe_score({key: "不是映射"})

    assert safe is not None
    assert key not in safe


def test_the_three_term_tables_behave_identically() -> None:
    # 显式对照：三段是逐行同构的，将来若只改其中一处，这条会失败。
    payload = {"term": ["m1", 2, "m2"]}
    results = [_safe_score({key: dict(payload)})[key] for key in _TERM_TABLE_KEYS]  # type: ignore[index]

    assert results[0] == results[1] == results[2] == {"term": ["m1", "m2"]}
