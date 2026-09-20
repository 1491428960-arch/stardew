"""对白边界判定的单一实现：收口标记、重新拉开、渠道方向与事件锁（P1 #16～#24）。

背景：`docs/semantic-duplication-audit-2026-09-20.md` 的 P1 一节记录了一批
「同一个概念被两处独立实现、两处都跑、结论却相反」的静默不一致。它们用户看不见，
但会同时影响运行时行为（重试链）与离线评测结论，使评测与实际体验脱节。

本文件按批建立语义：

- **#16～#18**：玩家收口、NPC 收口、收口后重新拉开——统一到
  `dialogue_boundaries` 的并集表与共享判定；运行时放过的，离线评测也放过。
- **#19～#21**：同名 tag 的两个来源（guard 的回合契约 / 离线诊断）以同一张表判定。
- **#22～#24**：事件锁、口头颗粒与相邻轮次机械复用，收敛到同一实现。

这些用例先红后绿：修复前它们钉住的正是两处分歧本身。
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from stardew_ai_bridge import behavior_quality as behavior_quality_module
from stardew_ai_bridge import character_quality_eval
from stardew_ai_bridge import guard as guard_module
from stardew_ai_bridge.behavior_quality import (
    _SPECIFIC_PLAN_PATTERNS,
    diagnose_affection_initiative,
    diagnose_conversation_lead,
    diagnose_personal_affection,
)
from stardew_ai_bridge.dialogue_boundaries import (
    FACE_TO_FACE_MARKERS,
    NPC_CLOSE_REPLY_MARKERS,
    PLAYER_CLOSE_MARKERS,
    REMOTE_ONLY_MARKERS,
    channel_direction_tag,
    is_npc_close_reply,
    is_player_closing,
    is_specific_arrangement,
    repeats_affection_shape,
    reopens_after_close,
    reply_avoids_speech_particle,
    reply_opens_with_marker,
    violates_event_gate,
)

# --- #16 玩家是否在收口／要空间 ---------------------------------------------


def test_player_close_markers_are_one_union_table() -> None:
    """两处曾经各持一张表；现在共用的必须是同一张（并集），且互不遗漏。"""

    assert tuple(guard_module._CLOSE_INPUT_MARKERS) == PLAYER_CLOSE_MARKERS
    assert tuple(behavior_quality_module._CLOSE_INPUT_MARKERS) == (
        PLAYER_CLOSE_MARKERS
    )


@pytest.mark.parametrize(
    "player_input",
    [
        "我先睡了，晚安。",  # guard 与离线评测都认（原有交集）
        "我今天没心情，先让我一个人待会儿。",
        "不用陪我了，我想静一静。",  # 离线评测定则此前漏掉
        "你先别过来，我今天真的很难受。",
        "我心情很差，改天再聊吧。",
    ],
)
def test_player_closing_reads_both_the_marker_table_and_the_pattern(
    player_input: str,
) -> None:
    assert is_player_closing(player_input) is True


@pytest.mark.parametrize(
    "player_input",
    [
        "账本整理好了吗？",
        "我把音量调低了，你不用抢我的耳机。",  # “不用”是正向，不该判成收口
        "听完这首再回房间，行吗？",
    ],
)
def test_ordinary_player_input_is_not_a_close(player_input: str) -> None:
    assert is_player_closing(player_input) is False


def test_conversation_lead_uses_the_shared_player_closing_decision() -> None:
    """#16：`不用陪` 这类收口此前只在 guard 侧成立，离线评测会误判为缺引导。"""

    result = diagnose_conversation_lead(
        {"relationship_stage": "dating", "npc_id": "Shane"},
        {"initiative_expectation": "guarded"},
        "好，那我就不打扰你了。",
        player_input="不用陪我了，我想静一静。",
    )

    assert result["conversationLeadKind"] == "lead_exit_allowed"
    assert "lead_exit_allowed" in result["conversationLeadTags"]


# --- #17 NPC 是否在自然收口 -------------------------------------------------


def test_npc_close_reply_markers_are_one_union_table() -> None:
    """并集：guard 的 20 条与离线评测的 9 条合并后，两边引用同一张表。"""

    assert tuple(guard_module._CLOSE_REPLY_MARKERS) == NPC_CLOSE_REPLY_MARKERS
    assert tuple(behavior_quality_module._CLOSE_REPLY_MARKERS) == (
        NPC_CLOSE_REPLY_MARKERS
    )
    for marker in ("好好休息", "去吧", "路上小心", "注意安全"):
        assert is_npc_close_reply(f"你先休息吧，{marker}。") is True
    for marker in ("明天再聊", "改天见", "早点钻被窝", "回头再见"):
        assert is_npc_close_reply(f"那就{marker}。") is True


@pytest.mark.parametrize(
    "reply",
    ["你先休息吧。", "去吧，路上小心。", "好好休息，明天见。"],
)
def test_offline_evaluation_accepts_the_closes_that_runtime_already_accepts(
    reply: str,
) -> None:
    """#17：同一句「你先休息吧。」guard 放过、离线评测曾经判缺爱意。"""

    diagnostic = diagnose_affection_initiative(
        {"relationship_stage": "dating", "channel": "remote"},
        {"initiative_expectation": "guarded", "initiative_kind": "guarded_care"},
        reply,
        player_input="我先睡了，晚安。",
    )

    assert "guarded_exit_allowed" in diagnostic["initiativeTags"]
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


def test_offline_evaluation_still_reads_a_npc_side_close_the_way_runtime_does() -> None:
    """并集不改变原有交集成员的判定：`明天再聊` 两侧本来就是收口。"""

    diagnostic = diagnose_affection_initiative(
        {"relationship_stage": "dating", "channel": "remote"},
        {"initiative_expectation": "guarded", "initiative_kind": "guarded_care"},
        "你先休息吧，明天再聊。",
        player_input="我先睡了，晚安。",
    )

    assert "guarded_exit_allowed" in diagnostic["initiativeTags"]
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


# --- #18 收口后有没有重新拉开 -----------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "别走，酒窖里还有两种香气，你想先听哪一种？",  # 直接追问
        "你别走，酒窖里还有两种香气，明天过来帮我收拾。",  # 未来安排
        "等等，别急着走，继续说。",  # 祈使式挽留
    ],
)
def test_reopening_after_close_is_detected_by_the_shared_predicate(reply: str) -> None:
    assert reopens_after_close(reply) is True


@pytest.mark.parametrize(
    "reply",
    [
        "那就明天再聊吧。",
        "不用过来帮我，我自己能行。",  # 未来动作被否定
        "你先休息吧。",
    ],
)
def test_plain_close_is_not_a_reopening(reply: str) -> None:
    assert reopens_after_close(reply) is False


def test_reopen_gate_does_not_depend_on_a_conversation_lead_contract() -> None:
    """#18：没有 conversation lead 契约时，运行时的收口判据必须与评测同源。

    此前 guard 在这种 prompt 上回落到自己的收口正则，离线诊断则用另一套，
    于是「运行时放过、离线评测判失败」。
    """

    prompt = [
        {"role": "user", "name": "player_input", "content": "我先睡了，晚安。"},
    ]

    assert (
        guard_module._reopens_after_player_close(
            prompt,
            "你别走，酒窖里还有两种香气，明天过来帮我收拾。",
        )
        is True
    )
    assert guard_module._reopens_after_player_close(prompt, "你先休息吧。") is False


# --- 单源判定函数本身 -------------------------------------------------------


def test_specific_plan_patterns_stay_the_single_arrangement_table() -> None:
    """#20 的前置：具体安排只有一张表，guard 与评测不得各持一套。"""

    assert isinstance(_SPECIFIC_PLAN_PATTERNS, tuple) and _SPECIFIC_PLAN_PATTERNS


# --- #20 「有没有给出具体安排」：三套判定 + 一个同名 tag ----------------------


def test_companionship_and_specific_plan_are_mutually_exclusive_on_one_reply() -> None:
    """#20：同一份诊断里不会再同时出现 `specific_plan` 与 `companionship_only`。

    实测的矛盾出现在 conversation lead 里：`明天我陪你坐一会儿。`的 `specific_plan`
    信号（`明天`）与 `companionship` 信号（`陪你`）同时命中。归因按**内容**定：
    纯陪伴说法不是安排，只有带上可执行的具体约定才算。
    """

    case = {"relationship_stage": "dating", "npc_id": "Elliott"}
    arrangement_reply = "明天我过来帮你收拾。"
    companionship_reply = "明天我陪你坐一会儿。"

    arrangement = diagnose_conversation_lead(
        case,
        {},
        arrangement_reply,
        player_input="今晚有空吗？",
    )
    companionship = diagnose_conversation_lead(
        case,
        {},
        companionship_reply,
        player_input="今晚有空吗？",
    )

    assert "specific_plan_only" in arrangement["conversationLeadTags"]
    assert "companionship_only" not in arrangement["conversationLeadTags"]
    assert "companionship_only" in companionship["conversationLeadTags"]
    assert "specific_plan_only" not in companionship["conversationLeadTags"]


def test_conversation_lead_reads_the_same_specific_plan_definition() -> None:
    """#20：`has_plan` 与 `specificPlanDetected` 是同一套判定，不再各持一个正则。

    这句话从前一条正则认不出来（旧表只写 `帮(?:个)?忙`），于是同一份 tags 里
    出现「陪伴」与「安排」并存；统一后 lead 侧稳定给出 `specific_plan_only`。
    """

    case = {"relationship_stage": "dating", "channel": "remote"}
    turn = {"initiative_expectation": "proactive", "initiative_kind": "specific_plan"}
    reply = "明天我过来帮你收拾。"

    affection = diagnose_affection_initiative(case, turn, reply)
    result = diagnose_conversation_lead(
        {"relationship_stage": "dating", "npc_id": "Elliott"},
        {},
        reply,
        player_input="今晚有空吗？",
    )

    assert affection["specificPlanDetected"] is True
    assert is_specific_arrangement(reply) is True
    assert "specific_plan_only" in result["conversationLeadTags"]
    assert "companionship_only" not in result["conversationLeadTags"]


# --- #21 渠道越界：两处标记表 + 缺一个方向 -----------------------------------


def test_channel_direction_uses_one_marker_table_for_both_directions() -> None:
    """#21：线上写见面、当面写线上，两个方向共用同一份标记与判定。"""

    remote_reply = "我明天过来找你，已经见面了。"
    face_reply = "你发消息给我就好。"

    assert channel_direction_tag("remote", remote_reply) == "wrong_channel"
    # guard 侧原先没有 face_to_face 方向的反向检查，现在两处同源。
    assert channel_direction_tag("face_to_face", face_reply) == "wrong_channel"
    assert channel_direction_tag("remote", "明天我给你带点吃的。") == ""
    assert channel_direction_tag("face_to_face", "明天我给你带点吃的。") == ""


def test_channel_tables_have_exactly_one_home() -> None:
    """`behavior_quality` 与 `character_quality_eval` 的表都来自共享模块。"""

    assert behavior_quality_module._REMOTE_ONLY_MARKERS == REMOTE_ONLY_MARKERS
    assert behavior_quality_module._FACE_TO_FACE_MARKERS == FACE_TO_FACE_MARKERS


# --- #22 阶段锁 vs 事件锁 ---------------------------------------------------


def test_event_gate_blocks_only_personal_affection_before_unlock() -> None:
    """事件未解锁时只拦「主动亲密」，普通日常照顾照旧。"""

    gate = {"effectiveIntimacyStage": "friend"}
    detect = lambda text: "想陪你" in text  # noqa: E731 - 测试替身

    assert violates_event_gate(gate, "今晚也想着你。", detect_personal_affection=detect) is False
    assert (
        violates_event_gate(
            gate,
            "我会想陪你，别自己扛。",
            detect_personal_affection=detect,
        )
        is True
    )
    assert (
        violates_event_gate(
            {"effectiveIntimacyStage": "close"},
            "我会想陪你，别自己扛。",
            detect_personal_affection=detect,
        )
        is False
    )


def test_evaluation_and_runtime_share_the_same_event_gate_decision() -> None:
    """#22：stage=dating + eventGate=friend 时，运行时会拦、评测以前判合规。

    运行时只认 `effectiveIntimacyStage` 到 friend 以内就收窄亲密，
    离线评测此前完全不看事件锁——这一条把两处钉在同一个入口上。
    """

    gate = {"effectiveIntimacyStage": "friend"}
    # 真实诊断里带个人亲近的句子（`想陪你` 只是测试替身用的字面，不是信号词）。
    reply = "这件事我只想先告诉你。"
    detect = lambda text: diagnose_personal_affection(text)["personalAffectionDetected"]  # noqa: E731

    assert detect(reply) is True
    assert (
        violates_event_gate(gate, reply, detect_personal_affection=detect) is True
    )
    assert guard_module._violates_event_gate(
        [
            {
                "role": "system",
                "name": "stage_execution_card",
                "content": json.dumps({"eventGate": gate}),
            },
            {"role": "user", "name": "player_input", "content": "今天怎么样？"},
        ],
        reply,
    ) is True


def _event_gate_case(completed_event_ids: tuple[str, ...]) -> object:
    """#22 续：Shane 的事件链只到 `completed_event_ids` 为止的评测案例。

    2026-09-20 补数据后，`shane-close-boundary` 自身已带完整的 close 档链
    （`611944 / 3910674 / 3910975 / 3900074`）；这里显式传入进度覆盖它，
    让「锁住 / 解锁」成为唯一变量。
    """

    return replace(
        character_quality_eval.case_by_id("shane-close-boundary"),
        relationship_stage="dating",
        friendship_hearts=8,
        expected_terms=(),
        completed_event_ids=completed_event_ids,
    )


def test_quality_score_fails_a_reply_that_crosses_the_event_gate() -> None:
    """#22：事件锁未解锁时的主动亲密必须计入离线评测**不合格**。

    运行时 guard 会因同一判定触发重试，离线评测此前只打标签、不影响
    `passed`——于是同一条回复一处拦、一处判合规。2026-09-20 用户口径：
    「不同阶段的不同说话方式是核心体验的一部分」，越界不是风格问题。
    """

    # 只完成 acquaintance 事件，friend／close 事件链仍未完成 → 事件锁收窄亲密权限。
    case = _event_gate_case(("611944",))

    score = character_quality_eval.score_character_reply(
        case,
        "这件事我只想先告诉你。",
    )

    assert "event_gate_intimacy" in score["tags"]
    assert score["passed"] is False


def test_quality_score_accepts_the_same_reply_once_the_event_gate_is_unlocked() -> None:
    """对照：事件链接通后同一句话不再越界，说明失败只来自事件锁。"""

    case = _event_gate_case(("611944", "3910674", "3910975", "3900074"))

    score = character_quality_eval.score_character_reply(
        case,
        "这件事我只想先告诉你。",
    )

    assert "event_gate_intimacy" not in score["tags"]
    assert score["passed"] is True


# --- #23 开场／口头颗粒 -----------------------------------------------------


def test_speech_particle_and_opening_predicates_are_shared() -> None:
    """#23：同一个「重复颗粒」概念在 guard 与表达质量里必须同源。"""

    particles = ("嗯", "哦")
    assert reply_avoids_speech_particle("嗯，今天还行。", particles) is True
    assert reply_avoids_speech_particle("今天还行。", particles) is False
    # 词语内部的同字不算颗粒（与 guard 的边界判定一致）。
    assert reply_avoids_speech_particle("这件事嗯嗯啊啊的。", ("啊",)) is False

    assert reply_opens_with_marker("今天还行。", ("今天挺忙。", "今天还行。")) is True
    assert reply_opens_with_marker("明天再说。", ("今天挺忙。",)) is False


# --- #24 相邻轮次机械复用同一亲密形状 ---------------------------------------


def test_mechanical_shape_predicate_is_the_single_decision() -> None:
    """#24：形状相同、没有新锚点、不是收口，才算机械复用。

    主动类型**不**参与判定：评测侧原先额外要求 kind 相同，于是同一段相邻
    回复在运行时被改写、在评测里判「不机械」（既有用例
    `test_affection_variation_flags_same_personal_shape_even_when_kind_changes`
    正是钉住 kind 变了也算复用的）。
    """

    assert repeats_affection_shape("exclusive_share", "exclusive_share") is True
    assert repeats_affection_shape("exclusive_share", "companionship") is False
    assert repeats_affection_shape("", "exclusive_share") is False
    assert (
        repeats_affection_shape(
            "exclusive_share",
            "exclusive_share",
            allowed_close=True,
        )
        is False
    )


def test_evaluation_variation_scoring_uses_the_shared_shape_decision() -> None:
    """#24：`score_affection_variation` 与 guard 用同一个形状判定函数。"""

    seen: list[tuple[object, object]] = []
    original = character_quality_eval._repeats_affection_shape

    def spy(*args: object, **kwargs: object) -> bool:
        seen.append((args[0] if args else None, args[1] if len(args) > 1 else None))
        return original(*args, **kwargs)

    character_quality_eval._repeats_affection_shape = spy
    try:
        scores = character_quality_eval.score_affection_variation(
            ["这首歌我只想先给你听。", "这段话我也只留给你听。"],
            [None, None],
            [
                {"affectionShape": "exclusive_share", "initiativeKind": "creative_share"},
                {"affectionShape": "exclusive_share", "initiativeKind": "creative_share"},
            ],
        )
    finally:
        character_quality_eval._repeats_affection_shape = original

    assert seen, "score_affection_variation 必须走共享的形状判定"
    assert scores[1]["mechanical"] is True
