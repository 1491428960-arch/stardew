"""紧凑 prompt 的场景卡与时段可读化。

这一组测试补的是此前的**测试盲区**：线上游戏端走 `compactPrompt=true`
（`smapi/BridgeClient.CompactPrompt` 默认 true），而既有测试
（`test_prompts.py::test_prompt_treats_current_scene_facts_as_hard_*`、
`test_game_context_contract.py` 只断言上下文层有 `time`）
全都落在 `compact=false` 的评测路径上，于是
「游戏内 prompt 里没有时间/天气/地点」这个坑一直没被任何断言覆盖。

实测证据（改动前，8 角色 × 4 时段 32 份）：紧凑路径的 prompt SHA256 **完全相同**；
同一份 prompt 的 `safety_rules` 却写着「天气、时间和地点是当前场景的硬事实」。
"""

from __future__ import annotations

import json

from stardew_ai_bridge.app import _build_context


NPC_ID = "Harvey"
MESSAGE = "早上好，今天怎么样？"


def _payload(
    *,
    time: int | None = 600,
    season: object = "spring",
    date: object = "25",
    weather: object = "clear",
    location: object = "Hospital",
    channel: str | None = "face_to_face",
    compact: bool = True,
    extra_state: dict[str, object] | None = None,
) -> dict[str, object]:
    """贴近 `smapi/GameStateCollector.cs` 真实产出的请求体。

    原始值形态按 C# 侧实测：season 是小写英文闭集、weather 只有 rain/clear、
    date 是 dayOfMonth 的十进制串、location 是地图标识符、time 是 600–2600 的整数。
    """

    state: dict[str, object] = {"npcId": NPC_ID, "displayName": NPC_ID}
    if season is not None:
        state["season"] = season
    if date is not None:
        state["date"] = date
    if weather is not None:
        state["weather"] = weather
    if location is not None:
        state["location"] = location
    if time is not None:
        state["time"] = time
    state.update(
        {
            "friendship": 1500,
            "friendshipHearts": 6,
            "relationship": "friend",
        }
    )
    if extra_state:
        state.update(extra_state)

    body: dict[str, object] = {
        "npcId": NPC_ID,
        "message": MESSAGE,
        "intent": "chat",
        "provider": "fake",
        "compactPrompt": compact,
        "sourceMods": [],
        "recentFacts": [],
        "history": [],
        "gameState": state,
    }
    if channel is not None:
        body["channel"] = channel
    return body


def _messages(**kwargs: object) -> list[dict[str, str]]:
    _, prompt = _build_context(_payload(**kwargs))  # type: ignore[arg-type]
    return prompt


def _scene(**kwargs: object) -> dict[str, object] | None:
    card = next((m for m in _messages(**kwargs) if m.get("name") == "scene"), None)
    return json.loads(card["content"]) if card else None


# --- 场景卡确实出现，且四种原始形态都被翻成人话 -------------------------------


def test_compact_prompt_renders_scene_card_with_readable_hard_facts() -> None:
    scene = _scene(time=600)

    assert scene == {
        "季节": "春天",
        "日期": "25",
        "天气": "晴天",
        "时段": "清晨（6:00）",
        "地点": "Hospital",
        "场合": "当面",
    }


def test_compact_scene_card_drops_fields_already_covered_by_other_cards() -> None:
    """friendship / hearts / relationship 已在 stage 系卡片里，场景卡不该重复。"""

    context, prompt = _build_context(_payload())
    card = next(m for m in prompt if m.get("name") == "scene")
    scene = json.loads(card["content"])

    assert set(scene) == {"季节", "日期", "天气", "时段", "地点", "场合"}, (
        "场景卡只保留场景硬事实与渠道结论，关系/好感字段不重复渲染"
    )
    # 硬事实的**来源字段**仍在 context 里（门控与语料检索照旧拿得到）
    assert context["gameState"]["friendshipHearts"] == 6


def test_compact_scene_card_renders_nothing_when_every_field_is_missing() -> None:
    """完全没有信息（场景字段与渠道都缺）时不产空卡。"""

    prompt = _messages(
        time=None, season=None, date=None, weather=None, location=None, channel=None
    )

    assert all(m.get("name") != "scene" for m in prompt)


def test_compact_scene_card_survives_on_channel_alone() -> None:
    """场景字段全空但渠道在场时仍产卡。

    `interaction` 卡（承载 `channelInstruction`）在紧凑路径被跳过，
    所以「场合」是这条路径上唯一的渠道信息——它不是可有可无的附赠字段。
    """

    assert _scene(
        time=None, season=None, date=None, weather=None, location=None
    ) == {"场合": "当面"}


# --- 时段可读化与跨日边界 -----------------------------------------------------


def test_compact_scene_card_translates_raw_time_into_readable_segment() -> None:
    assert _scene(time=600)["时段"] == "清晨（6:00）"
    assert _scene(time=830)["时段"] == "上午（8:30）"
    assert _scene(time=1200)["时段"] == "中午（12:00）"
    assert _scene(time=1830)["时段"] == "傍晚（18:30）"
    assert _scene(time=2100)["时段"] == "晚上（21:00）"
    assert _scene(time=2300)["时段"] == "深夜（23:00）"


def test_compact_scene_card_marks_next_day_after_midnight() -> None:
    """`2400` 起星露谷算次日：0:00 写作 2400、次日 2:00 写作 2600。

    不标「次日」的话，「凌晨（2:00）」会被模型读成当天下午 2 点。
    """

    assert _scene(time=2400)["时段"] == "次日凌晨（0:00）"
    assert _scene(time=2500)["时段"] == "次日凌晨（1:00）"
    assert _scene(time=2600)["时段"] == "次日凌晨（2:00）"


def test_compact_scene_card_omits_segment_for_unusable_time() -> None:
    """越界/非法时刻不编造时段，其余字段照常渲染。"""

    for bad in (0, 599, 2601, 760):
        scene = _scene(time=bad)
        assert "时段" not in scene, f"time={bad} 不该产出时段"
        assert scene["天气"] == "晴天"


# --- 早/中/晚必须产出不同 prompt（本次修复的核心验收）-------------------------


def test_compact_prompts_differ_across_morning_noon_and_night() -> None:
    """改动前这三份 prompt 字节级完全相同——正是「早上说晚上的话」的源头。"""

    morning = _messages(time=600)
    noon = _messages(time=1200)
    night = _messages(time=2100)

    blobs = [json.dumps(prompt, ensure_ascii=False) for prompt in (morning, noon, night)]
    assert len(set(blobs)) == 3, "早/中/晚三份紧凑 prompt 必须互不相同"

    for prompt, expected in ((morning, "清晨（6:00）"), (noon, "中午（12:00）"), (night, "晚上（21:00）")):
        card = next(m for m in prompt if m.get("name") == "scene")
        assert expected in card["content"]


def test_compact_prompt_does_not_leak_relationship_fields_into_scene_card() -> None:
    """紧凑路径仍不渲染完整 game_state 卡（那是本次修复刻意保持的省预算行为）。"""

    prompt = _messages(time=600)

    assert all(m.get("name") != "game_state" for m in prompt)
    assert any(m.get("name") == "scene" for m in prompt)


# --- 非紧凑路径不受影响 -------------------------------------------------------


def test_offline_compact_keeps_full_game_state_and_no_scene_card() -> None:
    """评测路径（`compact` 为真但无 `_runtime_compact`）保持完整卡组。

    `runtime_compact` 同时要求 `context["_runtime_compact"] is True`，
    而该标记只由请求的 `compactPrompt` 置位，因此离线评测的
    `EvaluationBudget.compact_prompt=True` 不受本次改动影响。
    """

    context, prompt = _build_context(_payload(time=600, compact=False))

    assert context.get("_runtime_compact") is None
    assert any(m.get("name") == "game_state" for m in prompt)
    assert all(m.get("name") != "scene" for m in prompt)


def test_compact_scene_card_passes_unknown_location_through() -> None:
    """地点是开放集合（mod 地图），认不出也必须透传，不能整块丢掉。"""

    assert _scene(location="CustomModMap_Interior")["地点"] == "CustomModMap_Interior"
