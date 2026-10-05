"""婚后亲密请求在生产路径上的可达性（2026-10-03）。

背景：`smapi/BridgeClient.cs` 的请求体没有 `qualityContext`，
`flirtIntensity` / `adultConsensual` / `romanceEligible` 恒缺，
`_build_turn_plan` 的 `explicit_intimacy` 分支因而在生产路径**不可达**——
婚后玩家明确提出亲密请求，也一律落到 `answer_only`（「不主动加亲密表达」）。
离线评测用例自带这三个字段，所以这条缺口在评测里永远暴露不出来。

⚠ 字段名容易搞错：`NpcGameState`（models.py:111）里 **`relationship` 是关系类型**
（值域 friend / dating），**`marriageStatus` 才是婚姻状态**，`GameStateCollector.cs:595`
的 `DeriveMarriageStatus` 说明后者由前者派生。实测请求用 `relationship: "married"`
既不合值域、也判不出婚姻（`_relationship_stage` 会给 `stranger`），
所以下面所有夹具都按**生产真实组合**写。

测试用的三句玩家输入都取自用户存档 test2_412086775 的真实对话。
"""

from __future__ import annotations

from stardew_ai_bridge.prompts import (
    _build_turn_plan,
    _infer_turn_plan_quality_context,
    _relationship_stage,
)

# 用户存档里的真实三轮（Shane，已婚）
REAL_OPENING = "早啊宝贝，亲一个？"
REAL_EXPLICIT = "我还想再做一次嘛，别去，这个早上给我"
# 这一句本身不含任何词表里的词——靠历史延续兜
REAL_INNUENDO = "你下面的这张嘴可不是这么想的，她在欢迎我呢"

# 生产真实形状（见 BridgeClientTests.cs:416-417 / 551-552）
MARRIED_STATE = {"relationship": "friend", "marriageStatus": "married", "friendshipHearts": 10}
DATING_STATE = {"relationship": "dating", "marriageStatus": "dating", "friendshipHearts": 8}
FRIEND_STATE = {"relationship": "friend", "friendshipHearts": 6}


def _infer(state: dict, player_input: str, quality=None, history=None) -> dict:
    return _infer_turn_plan_quality_context(
        quality if quality is not None else {},
        player_input=player_input,
        game_state=state,
        history=history,
    )


def _mode(state: dict, player_input: str, history=None, quality=None) -> str:
    """走一遍和线上一致的判定：先推断补缺，再算 turn_plan。"""

    inferred = _infer(state, player_input, quality, history)
    return str(_build_turn_plan(inferred, player_input=player_input).get("mode"))


# --- 前置：字段语义（这条挂了，说明夹具本身就错） ---------------------------


def test_production_field_semantics() -> None:
    assert _relationship_stage(MARRIED_STATE) == "married"
    assert _relationship_stage(DATING_STATE) == "dating"
    # relationship 的值域不含 married；传进去只该兜底成 stranger，不该被判成已婚
    assert _relationship_stage({"relationship": "married"}) != "married"


# --- 推断层 ---------------------------------------------------------------


def test_married_with_explicit_marker_fills_intensity_and_consent() -> None:
    inferred = _infer(MARRIED_STATE, REAL_EXPLICIT)
    assert inferred["flirtIntensity"] == "explicit"
    assert inferred["adultConsensual"] is True
    assert inferred["romanceEligible"] is True


def test_colloquial_marker_is_recognised() -> None:
    """「亲一个」是口语；原词表只有书面的「亲一下」。"""

    assert _infer(MARRIED_STATE, REAL_OPENING)["flirtIntensity"] == "explicit"


def test_innuendo_without_marker_inherits_from_history() -> None:
    """露骨的那句本身可能一个词表词都没有，靠最近几轮玩家输入延续。"""

    history = [
        {"role": "user", "content": REAL_OPENING},
        {"role": "assistant", "content": "……干嘛啊，大清早的。"},
        {"role": "user", "content": REAL_EXPLICIT},
    ]
    inferred = _infer(MARRIED_STATE, REAL_INNUENDO, history=history)
    assert inferred["flirtIntensity"] == "explicit"
    # 字面 marker 命中不了的一句，直接给出本轮目标，不再依赖字面匹配
    assert inferred["turnPlan"]["mode"] == "explicit_intimacy"


def test_history_window_is_bounded() -> None:
    """超出窗口的旧亲密不该无限期地把后续轮次都判成 explicit。"""

    history = [{"role": "user", "content": REAL_EXPLICIT}] + [
        {"role": "user", "content": f"今天做点什么好呢 {i}"} for i in range(6)
    ]
    inferred = _infer(MARRIED_STATE, "鸡舍那边的活干完了", history=history)
    assert "flirtIntensity" not in inferred


# --- 不越界 ---------------------------------------------------------------


def test_non_romantic_stage_is_untouched() -> None:
    assert _infer(FRIEND_STATE, REAL_EXPLICIT) == {}


def test_plain_married_chat_is_untouched() -> None:
    """回归：婚后普通闲聊不能被误判成 explicit_intimacy。"""

    inferred = _infer(MARRIED_STATE, "今天天气不错，鸡舍那边的活干完了")
    assert "flirtIntensity" not in inferred
    assert inferred.get("adultConsensual") is True  # 仅同意边界，不涉及强度


def test_explicit_values_are_never_overwritten() -> None:
    """调用方显式给了值就以显式值为准。"""

    inferred = _infer(
        MARRIED_STATE,
        REAL_EXPLICIT,
        quality={
            "flirtIntensity": "light",
            "adultConsensual": False,
            "romanceEligible": False,
        },
    )
    assert inferred["flirtIntensity"] == "light"
    assert inferred["adultConsensual"] is False
    assert inferred["romanceEligible"] is False


def test_explicit_turn_plan_is_never_overwritten() -> None:
    """调用方（或评测用例）显式给了 turnPlan 时，不被历史延续改写。"""

    history = [{"role": "user", "content": REAL_EXPLICIT}]
    inferred = _infer(
        MARRIED_STATE,
        REAL_INNUENDO,
        quality={"turnPlan": {"mode": "answer_plus_detail"}},
        history=history,
    )
    assert inferred["turnPlan"]["mode"] == "answer_plus_detail"


def test_malformed_game_state_does_not_raise() -> None:
    for bad in (None, "", [], 0, {"marriageStatus": None}):
        assert _infer_turn_plan_quality_context(
            {}, player_input=REAL_EXPLICIT, game_state=bad
        ) == {}


# --- 端到端：判定层现在真的能走到 explicit_intimacy -------------------------


def test_married_explicit_request_reaches_explicit_intimacy_mode() -> None:
    assert _mode(MARRIED_STATE, REAL_EXPLICIT) == "explicit_intimacy"


def test_married_opening_reaches_explicit_intimacy_mode() -> None:
    assert _mode(MARRIED_STATE, REAL_OPENING) == "explicit_intimacy"


def test_innuendo_reaches_explicit_intimacy_mode_via_history() -> None:
    history = [
        {"role": "user", "content": REAL_OPENING},
        {"role": "user", "content": REAL_EXPLICIT},
    ]
    assert _mode(MARRIED_STATE, REAL_INNUENDO, history=history) == "explicit_intimacy"


def test_dating_gets_intensity_but_not_consent() -> None:
    """dating 给强度；同意边界不由系统默认成立，仍由模型在回复里先确认。"""

    inferred = _infer(DATING_STATE, REAL_EXPLICIT)
    assert inferred["flirtIntensity"] == "explicit"
    assert "adultConsensual" not in inferred


def test_friend_explicit_request_does_not_reach_explicit_intimacy() -> None:
    assert _mode(FRIEND_STATE, REAL_EXPLICIT) != "explicit_intimacy"


def test_plain_married_chat_does_not_reach_explicit_intimacy() -> None:
    """最重要的一条回归：普通婚后对话的行为不该改变。"""

    assert (
        _mode(MARRIED_STATE, "今天天气不错，鸡舍那边的活干完了")
        != "explicit_intimacy"
    )
