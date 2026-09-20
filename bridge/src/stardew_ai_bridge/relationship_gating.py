"""根据已完成的好感度事件计算可使用的叙事亲密度上限。

游戏里的 friendship hearts 是数值状态，heart event 才是角色关系已经经历过的
叙事证据。两者不一致时，回复不能直接使用最高心级的开放程度。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .personas import canonical_npc_id


HEART_STAGES = ("stranger", "acquaintance", "friend", "close")
STATUS_STAGES = ("dating", "married", "parent")
STAGE_RANK = {
    "stranger": 0,
    "acquaintance": 1,
    "friend": 2,
    "close": 3,
    "dating": 4,
    "married": 5,
    "parent": 6,
}

# 2026-09-20：“朋友及以上”这个阶段集合与它的相对顺序，此前在 guard.py 与
# character_quality_eval.py 里**各写了一份一模一样的表**（连比较逻辑都同构），
# prompts.py 还有第三份只含集合的副本。三处任何一处改了都会漏掉另两处，
# 所以统一在这里派生——**相对顺序与 STAGE_RANK 天然一致，不会再漂移**。
# 2026-09-20（用户拍板）：parent 此前把两件事混在一起——
#   ① 这个 NPC 自己有孩子（例如 Jodi 的两个孩子）：这是**背景信息**，
#      不该改变“我和他的关系”；
#   ② 我和他有了孩子：这才是**关系状态**，是 married 的子状态。
# 现在 ① 不再影响阶段；② 仍判 parent，且 **parent 继承 married 的亲密契约**。
# 需要判断“算不算既成亲密关系”的地方，用 INTIMATE_STAGES，不要各写一份字面量。
INTIMATE_STAGES = frozenset({"dating", "married", "parent"})

CONVERSATION_LEAD_STAGES = frozenset({"friend", "close", "dating", "married"})
CONVERSATION_LEAD_STAGE_ORDER = {
    stage: STAGE_RANK[stage] for stage in ("friend", "close", "dating", "married")
}

# 2026-09-20（语义层审计 #28）：「游戏事件是否已完成」此前有**四套匹配规则**，
# 各自演化：
#   ① `story_state._matches_event` —— 拆**候选**前缀（`Mod.Pack:EventX` 也产出
#      `eventx`），并额外去掉非字母数字字符（`shane-heart-6` ↔ `Shane6`）。
#   ② `relationship_gating._event_id_matches` —— 只匹配**基线**前缀：
#      `completed` 侧可以带命名空间，`required` 侧不行。
#   ③ `profile_index._event_dialogue_is_completed` —— 由记录的 `sourceMod`
#      合成前缀（`Vanilla:56`），但**必须**带前缀才算。
#   ④ `profile_index.story_events` / `known_characters` 的门控 —— 直接
#      `required.strip().casefold() in completed_keys`，**两侧都不认前缀**。
# 前两套「两边都能认」的宽口径给出同一个答案，③④ 会分裂：内容侧声明
# `requiredEventId="56"`、游戏侧报 `completed=["flashshifter.SVE:56"]` 时，
# ②判已完成、④判未完成（内容库 `storyEvents` 目前为空，所以是潜伏分歧）。
#
# 下面两个函数是**唯一实现**，四处一律从它派生。宽口径同时保留两条旧契约：
# 命名空间前缀两个方向都认（`flashshifter.SVE:56` ↔ `56`），分隔符差异容忍
# （`Shane6` ↔ `shane-heart-6`）。
_EVENT_TOKEN_RE = re.compile(r"[^a-z0-9一-鿿]+", re.IGNORECASE)


def game_event_id_tokens(value: object) -> set[str]:
    """事件 ID → 可比较的 token 集合。

    产出 `(全名, 去掉命名空间前缀的尾段)`，每个再附一份去掉分隔符的写法。
    大小写、两端空白一律归一；`None` 与其它对象先 `str()`（与旧实现一致）。
    """

    text = str(value).strip().casefold()
    if not text:
        return set()
    candidates = {text}
    if ":" in text:
        candidates.add(text.rsplit(":", 1)[-1])
    tokens: set[str] = set()
    for candidate in candidates:
        tokens.add(candidate)
        tokens.add(_EVENT_TOKEN_RE.sub("", candidate))
    return {token for token in tokens if token}


def game_event_completed(required: object, completed: Iterable[object]) -> bool:
    """`required` 指向的事件是否出现在 `completed` 里。

    `completed` 可以是任意可迭代对象；空集合直接判否（没有已完成事件
    不等于“全都完成了”）。
    """

    required_tokens = game_event_id_tokens(required)
    if not required_tokens:
        return False
    for value in completed:
        if required_tokens.intersection(game_event_id_tokens(value)):
            return True
    return False


@dataclass(frozen=True)
class RelationshipEventGate:
    """某个叙事阶段需要完成的事件链。"""

    stage: str
    required_event_ids: tuple[str, ...]


@dataclass(frozen=True)
class RelationshipGateResult:
    """同时保留游戏真实关系状态和事件锁定后的亲密权限。"""

    relationship_stage: str
    heart_stage: str | None
    effective_stage: str
    effective_intimacy_stage: str
    event_unlocked_stage: str | None
    event_gate_configured: bool
    event_gate_applied: bool
    relationship_status_preserved: bool
    missing_event_ids: tuple[str, ...]

    def as_prompt_dict(self) -> dict[str, object]:
        return {
            "relationshipStage": self.relationship_stage,
            "heartStage": self.heart_stage,
            "effectiveStage": self.effective_stage,
            "effectiveIntimacyStage": self.effective_intimacy_stage,
            "eventUnlockedStage": self.event_unlocked_stage,
            "eventGateConfigured": self.event_gate_configured,
            "eventGateApplied": self.event_gate_applied,
            "relationshipStatusPreserved": self.relationship_status_preserved,
            "missingEventIds": list(self.missing_event_ids),
        }


# 这里只登记已从原版/SVE 事件条件核对过的节点。事件素材里存在的其他节点
# 仍然可以作为 completedEventIds 门控素材，但不会被误当成关系阶段解锁条件。
_EVENT_GATES: dict[str, tuple[RelationshipEventGate, ...]] = {
    "Wizard": (
        RelationshipEventGate("acquaintance", ("1000075",)),
        RelationshipEventGate("friend", ("1000075", "1724096")),
        RelationshipEventGate("close", ("1000075", "1724096", "1724097")),
    ),
    "Sophia": (
        RelationshipEventGate("acquaintance", ("8185291",)),
        RelationshipEventGate("friend", ("8185291", "8185292", "8185293")),
        RelationshipEventGate("close", ("8185291", "8185292", "8185293", "8185295")),
    ),
    "Shane": (
        RelationshipEventGate("acquaintance", ("611944",)),
        RelationshipEventGate("friend", ("611944", "3910674", "3910975")),
        RelationshipEventGate("close", ("611944", "3910674", "3910975", "3900074")),
    ),
    "Sebastian": (
        RelationshipEventGate("acquaintance", ("2794460",)),
        RelationshipEventGate("friend", ("2794460", "384883", "27")),
        RelationshipEventGate("close", ("2794460", "384883", "27", "29")),
    ),
    "Alex": (
        RelationshipEventGate("acquaintance", ("20",)),
        RelationshipEventGate("friend", ("20", "2481135", "2119820")),
        RelationshipEventGate("close", ("20", "2481135", "2119820", "288847")),
    ),
    "Elliott": (
        RelationshipEventGate("acquaintance", ("39",)),
        RelationshipEventGate("friend", ("39", "40", "423502")),
        RelationshipEventGate("close", ("39", "40", "423502", "1848481")),
    ),
    "Harvey": (
        RelationshipEventGate("acquaintance", ("56",)),
        RelationshipEventGate("friend", ("56", "57", "58")),
        RelationshipEventGate("close", ("56", "57", "58", "571102")),
    ),
}


def _normalise_stage(value: object) -> str:
    stage = str(value or "").strip().casefold()
    return stage if stage in STAGE_RANK else "stranger"


def _heart_stage(friendship_hearts: object) -> str | None:
    if friendship_hearts is None or friendship_hearts == "":
        return None
    try:
        hearts = int(friendship_hearts)
    except (TypeError, ValueError):
        return None
    if hearts >= 8:
        return "close"
    if hearts >= 6:
        return "friend"
    if hearts >= 2:
        return "acquaintance"
    return "stranger"


def _event_id_matches(required: str, completed: set[str]) -> bool:
    """保留旧签名，实现统一到 ``game_event_completed``（见上方 #28 说明）。"""

    return game_event_completed(required, completed)


def relationship_event_gates(npc_id: object) -> tuple[RelationshipEventGate, ...]:
    canonical_id = canonical_npc_id(npc_id)
    return _EVENT_GATES.get(canonical_id, ())


def resolve_relationship_gate(
    npc_id: object,
    *,
    relationship_stage: object,
    friendship_hearts: object,
    completed_event_ids: Iterable[object] | None = None,
) -> RelationshipGateResult:
    """返回真实关系状态与事件解锁后的有效亲密权限。

    对 dating/married/parent 不篡改关系标签，只降低其可使用的亲密权限；
    对普通心级阶段则直接选择不超过事件上限的 stage profile。
    """

    raw_stage = _normalise_stage(relationship_stage)
    heart_stage = _heart_stage(friendship_hearts)
    gates = relationship_event_gates(npc_id)

    # 没有 completedEventIds 只能说明调用方没有提供事件状态，不能推断为
    # “事件全部未完成”；只有明确传入空列表时才启用事件锁。
    if not gates or heart_stage is None or completed_event_ids is None:
        return RelationshipGateResult(
            relationship_stage=raw_stage,
            heart_stage=heart_stage,
            effective_stage=raw_stage,
            effective_intimacy_stage=raw_stage,
            event_unlocked_stage=None,
            event_gate_configured=bool(gates),
            event_gate_applied=False,
            relationship_status_preserved=raw_stage in STATUS_STAGES,
            missing_event_ids=(),
        )

    completed = {
        str(value).strip().casefold()
        for value in completed_event_ids
        if str(value).strip()
    }

    # 数值达到二心但事件尚未发生时，仍允许普通的“二心前后”熟悉感，
    # 但不得直接跳到更高阶段；低于二心则保持 stranger。
    unlocked_stage = (
        "acquaintance"
        if STAGE_RANK[heart_stage] >= STAGE_RANK["acquaintance"]
        else "stranger"
    )
    missing: tuple[str, ...] = ()
    for gate in gates:
        if STAGE_RANK[gate.stage] > STAGE_RANK[heart_stage]:
            break
        missing_for_gate = tuple(
            event_id
            for event_id in gate.required_event_ids
            if not _event_id_matches(event_id, completed)
        )
        if missing_for_gate:
            missing = missing_for_gate
            break
        unlocked_stage = gate.stage

    if raw_stage in HEART_STAGES:
        effective_stage = min(
            (raw_stage, unlocked_stage),
            key=lambda item: STAGE_RANK[item],
        )
        effective_intimacy_stage = effective_stage
        status_preserved = False
    else:
        # 婚姻/恋爱是游戏事实，不因为缺事件而伪装成普通朋友；只限制
        # 私人披露、主动亲密和高级事件式关系表达。
        status_base = "close"
        effective_intimacy_stage = min(
            (status_base, heart_stage, unlocked_stage),
            key=lambda item: STAGE_RANK[item],
        )
        effective_stage = raw_stage
        status_preserved = True

    if raw_stage in HEART_STAGES:
        applied = effective_stage != raw_stage
    else:
        # dating/married/parent 用 close 作为最高的普通亲密基线；不能拿
        # relationshipStage 本身和 close 比较，否则即使事件链全部完成，
        # "married" 也会被误判成仍处于事件锁定状态。
        unrestricted_intimacy = min(
            ("close", heart_stage),
            key=lambda item: STAGE_RANK[item],
        )
        applied = effective_intimacy_stage != unrestricted_intimacy

    return RelationshipGateResult(
        relationship_stage=raw_stage,
        heart_stage=heart_stage,
        effective_stage=effective_stage,
        effective_intimacy_stage=effective_intimacy_stage,
        event_unlocked_stage=unlocked_stage,
        event_gate_configured=True,
        event_gate_applied=applied,
        relationship_status_preserved=status_preserved,
        missing_event_ids=missing,
    )

# 2026-09-20（系统性排查 · 语义层）：下面两个换算此前被复制到多处，且**已经漂移**：
# - `providers.py` 的分档把「2 心」判成 stranger，而 prompts/corpus/本模块都判
#   acquaintance（并连带走 stranger 的短答与不主动策略）。夹具恰好只喂 3／4 心，
#   所以这条分歧一直没被照到。
# - `providers.py` 还会**忽略请求里显式给的 relationshipStage**，自己重新推导一遍。
# 现在统一到这里，四处改为调用。
_HEART_STAGE_THRESHOLDS = ((8, "close"), (6, "friend"), (2, "acquaintance"))


def hearts_to_stage(hearts: int | None) -> str:
    """好感心数 → 关系阶段。四处必须给出同一答案。"""
    value = hearts or 0
    for threshold, stage in _HEART_STAGE_THRESHOLDS:
        if value >= threshold:
            return stage
    return "stranger"


_MARRIED_MARKERS = frozenset({"married", "spouse", "partner", "roommate"})
_DATING_MARKERS = frozenset(
    {"dating", "engaged", "fiance", "fiancé", "girlfriend", "boyfriend"}
)


def relationship_stage_from_state(
    *,
    explicit_stage: str | None = None,
    children_count: int | None = None,
    marriage_status: str | None = None,
    relationship: str | None = None,
    friendship_hearts: int | None = None,
) -> str:
    """游戏状态 → 关系阶段。**显式 stage 优先**，其次孩子/婚姻/恋爱标记，最后按心数兜底。"""
    candidate = str(explicit_stage or "").strip().casefold()
    if candidate in STAGE_RANK:
        return candidate
    spouse = str(marriage_status or "").strip().casefold() in _MARRIED_MARKERS
    if spouse and children_count is not None and children_count > 0:
        # 只有“与玩家有孩子”才是 parent；普通 NPC 自己的孩子是背景信息。
        return "parent"
    if spouse:
        return "married"
    if str(relationship or "").strip().casefold() in _DATING_MARKERS:
        return "dating"
    return hearts_to_stage(friendship_hearts)

