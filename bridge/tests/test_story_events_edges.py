"""`ProfileIndexStore.story_events` 的参与者匹配与事件门控。

按**缺失行数**排序挑出来的（缺 6/28）。它是“这个 NPC 参与了哪些剧情事件”的入口，
缺的全是过滤分支：

- 参与者列表里**必须有一个能对上这个 NPC**（用 canonical + casefold 比较）；
- `sourceMod` 要匹配当前启用的 Mod；
- **带 `requiredEventId` 的事件，只有玩家已完成它才返回**——这就是“**没走到那段剧情
  之前，NPC 不该提起它**”。

另外它还做了一个小分类：如果事件自身的 `eventId`／`sourceKey` 已经在
`completed_event_ids` 里，就给结果打上 `status = "completed"`。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.profile_index import ProfileIndexStore


def _event(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "eventId": "14",
        "sourceKey": "spring13",
        "sourceMod": "Vanilla",
        "participants": ["Shane", "Emily"],
        "summary": "春天的集市上大家聊了几句。",
    }
    base.update(overrides)
    return base


def _store(tmp_path: Path, events: object) -> ProfileIndexStore:
    index = {"schemaVersion": 2, "profiles": {}, "voiceCards": {}, "storyEvents": events}
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return ProfileIndexStore(path)


def _events(tmp_path: Path, events: object, **kwargs: object) -> list[dict[str, object]]:
    return _store(tmp_path, events).story_events("Shane", ("Vanilla",), **kwargs)  # type: ignore[arg-type]


# --- 入口与上限 -------------------------------------------------------------


@pytest.mark.parametrize("npc_id", ["", "   ", None, 42])
def test_a_blank_npc_id_yields_nothing(tmp_path: Path, npc_id: object) -> None:
    assert _store(tmp_path, [_event()]).story_events(npc_id, ("Vanilla",)) == []  # type: ignore[arg-type]


def test_a_zero_limit_yields_nothing(tmp_path: Path) -> None:
    assert _events(tmp_path, [_event()], limit=0) == []


def test_the_limit_is_capped_at_eight(tmp_path: Path) -> None:
    events = [_event(eventId=str(i), sourceKey=f"k{i}") for i in range(12)]

    assert len(_events(tmp_path, events, limit=99)) == 8


def test_a_non_list_container_yields_nothing(tmp_path: Path) -> None:
    assert _events(tmp_path, "不是列表") == []


# --- 参与者匹配 -------------------------------------------------------------


def test_non_mapping_events_are_skipped(tmp_path: Path) -> None:
    assert _events(tmp_path, ["不是映射", 42]) == []


@pytest.mark.parametrize("participants", ["Shane", 42, None, {}, []])
def test_a_non_list_participants_field_is_skipped(
    tmp_path: Path, participants: object
) -> None:
    assert _events(tmp_path, [_event(participants=participants)]) == []


def test_an_event_without_this_npc_is_skipped(tmp_path: Path) -> None:
    assert _events(tmp_path, [_event(participants=["Emily", "Abigail"])]) == []


def test_participant_matching_ignores_case_and_padding(tmp_path: Path) -> None:
    assert _events(tmp_path, [_event(participants=["  shane  "])]) != []


# --- 来源与门控 -------------------------------------------------------------


def test_an_unrelated_source_mod_is_skipped(tmp_path: Path) -> None:
    assert _events(tmp_path, [_event(sourceMod="SomeOtherMod")]) == []


def test_a_gated_event_is_hidden_until_completed(tmp_path: Path) -> None:
    # 没走到那段剧情之前，NPC 不该提起它。
    events = [_event(requiredEventId="42")]

    assert _events(tmp_path, events) == []
    assert _events(tmp_path, events, completed_event_ids=["42"]) != []


def test_event_ids_are_matched_case_insensitively_and_trimmed(tmp_path: Path) -> None:
    events = [_event(requiredEventId="Fall_14")]

    assert _events(tmp_path, events, completed_event_ids=["  fall_14  "]) != []


def test_a_blank_gate_is_treated_as_no_gate(tmp_path: Path) -> None:
    assert _events(tmp_path, [_event(requiredEventId="   ")]) != []


# --- 完成状态标记 -----------------------------------------------------------


def test_a_completed_event_is_marked_as_such(tmp_path: Path) -> None:
    # 事件自身的 eventId / sourceKey 命中已完成列表 → status = completed
    got = _events(tmp_path, [_event(eventId=""), _event(sourceKey="spring13")], completed_event_ids=["spring13"])

    assert got and got[0]["status"] == "completed"


def test_an_uncompleted_event_has_no_status_field(tmp_path: Path) -> None:
    got = _events(tmp_path, [_event()])

    assert got and "status" not in got[0]


# --- 其它 -------------------------------------------------------------------


def test_only_whitelisted_fields_survive(tmp_path: Path) -> None:
    got = _events(tmp_path, [_event(secretField="不该出现")])

    assert got and "secretField" not in got[0]


def test_a_bad_event_does_not_hide_a_good_one(tmp_path: Path) -> None:
    got = _events(tmp_path, ["不是映射", _event()])

    assert len(got) == 1
