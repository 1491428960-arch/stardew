"""约束作用域台账：判定「两条约束是否冲突」。

**目的**：让冲突判定**可复现**，不必每次靠读句子猜。
**起因**：2026-09-28 一晚之内四次把「作用域不同」误判成「矛盾」，四次都错 ——
根因是**只读句子内容，不读它的作用域**（见 `docs/STATE.md` §三）。
**人读视图**：`docs/constraint-scope.md`；本模块是**数据源**。

## 判定规则

两条约束**冲突**，当且仅当四条**同时**成立：

1. **同量** —— `quantity` 相同；
2. **条件重叠** —— `condition` 各维度允许值有交集；
3. **同优先级** —— `priority` 相同（不同 ⇒ 覆盖，是正常分级）；
4. **上界不同** —— `bound` 不相等。

⚠ 第 4 条是关键：同优先级意味着**没有覆盖关系**，此时两条不同的上界
就是**真冲突**（模型会取更宽的那条）。若一方上界更严 ⇒ 那是**分级**，不是矛盾。

**宁可漏判，不可误判**：漏判的代价是「一处冲突没发现」，
误判的代价是「删掉一层有意的防御」—— 后者在 2026-09-28 差点发生。
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: 优先级。数字越大越优先；`override` 用来表达「阶段卡/条件特化卡覆盖通用卡」。
PRIORITY: dict[str, int] = {"default": 0, "override": 1}

#: 抽取端量名（中文）→ 台账规范名。**全局默认。**
#:
#: ⚠ **不要把这层写成「按卡逐条」的明细。** 第一版就是那样，结果每新增一张卡都会
#: 静默漏掉 —— 2026-09-28 当天因此错了**三次**（`invite` 指向不存在的量名一次、
#: 漏掉 `affection_priority_final` 一次），每次的表现都是「把已录入的条目报成缺口」。
#: 全局默认 + `CARD_QUANTITY_OVERRIDES` 覆盖，才没有「忘了加一行」这个失败模式。
GLOBAL_QUANTITY_ALIASES: dict[str, str] = {
    "句数": "length_whole_reply",
    "字数": "length_whole_reply",
    "动作数": "action_count",
    "话题数": "topic_count",
    "邀约": "invite_action",
    "追问数": "followup_count",
    "重复次数": "repeat_object",
    "口语颗粒频率": "particle_frequency",
}

#: 卡级覆盖：**只在「同一个词在不同卡指不同量」时**才写。
CARD_QUANTITY_OVERRIDES: dict[tuple[str, str], str] = {
    # `safety_rules` 说的是**整条** 15–40 字；`voice_execution_card` 说的是**每句** ≤20 字
    ("voice_execution_card", "字数"): "length_per_sentence",
    # 「邀约」在阶段卡禁**行为**，在角色契约卡禁**时间承诺**
    ("final_role_voice_contract", "邀约"): "schedule_commitment",
    # acquaintance 阶段卡的「可以补一个当前话题事实」说的是**补几个事实**（动作数），
    # 不是话题数；「不主动换题」是**性质**而非数量 ⇒ 这张卡其实没有话题数约束。
    # ⚠ 补上 acquaintance 档后才暴露 —— 原先 `STAGES` 只有 4 档，查不到它。
    ("stage_execution_card", "话题数"): "action_count",
    # 2026-09-28 放宽抽取后新暴露的两处：原文都是**每句**长度，不是整条句数。
    # 「一句话通常十来个字，最多二十出头；话多了就断成第二句」——
    # 说的是单句上限与断句行为，**不设整条句数上限**。
    ("persona_core", "句数"): "length_per_sentence",
    ("voice_execution_card", "句数"): "length_per_sentence",
    # ⚠ 同一个表述「十来个字」会**先被「字数」正则命中** ⇒ 字数侧也必须覆盖，
    #   否则留下「persona_core × length_whole_reply」这个假缺口（实测踩到过）。
    ("persona_core", "字数"): "length_per_sentence",
}


def resolve_quantity(card: str, raw: str) -> str:
    """把抽取端的量名解析成台账的规范量名。卡级覆盖优先，其次全局默认。"""
    return CARD_QUANTITY_OVERRIDES.get(
        (card, raw), GLOBAL_QUANTITY_ALIASES.get(raw, raw)
    )


@dataclass(frozen=True)
class Constraint:
    """一条约束的**作用域**（不是它的文本）。"""

    id: str
    card: str
    text: str
    quantity: str
    bound: float | None = None
    """该量的**上界**（可比较）。`None` 表示非数值型，此时不参与第 4 条判定。"""
    condition: dict[str, frozenset[str]] = field(default_factory=dict)
    """维度 → 允许值。**空字典表示无条件（always）**。"""
    priority: str = "default"
    value: str = ""
    note: str = ""

    def label(self) -> str:
        return f"{self.id}（{self.card}｜{self.value or self.text[:18]}）"


def conditions_overlap(
    a: dict[str, frozenset[str]], b: dict[str, frozenset[str]]
) -> bool:
    """两个条件是否有交集。

    空字典 = 无条件 = 与任何条件都重叠。**维度不同 ⇒ 可同时成立 ⇒ 重叠**；
    维度相同但取值无交集 ⇒ 不重叠。
    """
    if not a or not b:
        return True
    for dimension, values in a.items():
        other = b.get(dimension)
        if other is not None and not (values & other):
            return False
    return True


@dataclass(frozen=True)
class Conflict:
    left: Constraint
    right: Constraint
    reason: str

    def describe(self) -> str:
        return (
            f"冲突：{self.left.label()}\n"
            f"      {self.right.label()}\n"
            f"      理由：{self.reason}"
        )


def find_conflicts(constraints: tuple[Constraint, ...]) -> list[Conflict]:
    """按四条规则找出全部冲突。顺序无关，同一对只报一次。"""
    found: list[Conflict] = []
    for index, left in enumerate(constraints):
        for right in constraints[index + 1 :]:
            if left.quantity != right.quantity:
                continue  # 规则 1：不是同一个量 ⇒ 不冲突
            if not conditions_overlap(left.condition, right.condition):
                continue  # 规则 2：条件不重叠 ⇒ 各自生效 ⇒ 不冲突
            if PRIORITY[left.priority] != PRIORITY[right.priority]:
                continue  # 规则 3：优先级不同 ⇒ 覆盖关系 ⇒ 不冲突
            if left.bound is None or right.bound is None:
                continue  # 非数值量无法比较 ⇒ 宁可漏判
            if left.bound == right.bound:
                continue  # 规则 4：上界相同 ⇒ 一致 ⇒ 不冲突
            wider, narrower = (
                (left, right) if left.bound > right.bound else (right, left)
            )
            found.append(
                Conflict(
                    left=left,
                    right=right,
                    reason=(
                        f"同量 `{left.quantity}`、条件重叠、优先级同为 "
                        f"`{left.priority}`，但上界不同（{narrower.bound:g} vs "
                        f"{wider.bound:g}）⇒ 模型会取更宽的 `{wider.id}`"
                    ),
                )
            )
    return found


# ---------------------------------------------------------------------------
# 台账：`length` 系列（样板，覆盖 stranger 与通用卡）
# ---------------------------------------------------------------------------

#: 当前状态（2026-09-28 收束之后）。
CURRENT: tuple[Constraint, ...] = (
    Constraint(
        id="len-whole-general",
        card="safety_rules",
        text="中文通常 1–2 句、15–40 字",
        quantity="length_whole_reply",
        bound=2,
        value="1–2 句 / 15–40 字",
        note="通用上限。字数 40 与「每句 ≤20 字 × 2 句」吻合。",
    ),
    Constraint(
        id="len-whole-greeting",
        card="safety_rules",
        text="…玩家那句话只是由头，只保留一个平实事实或感受，最多两句",
        quantity="length_whole_reply",
        bound=2,
        condition={"input": frozenset({"greeting", "status_query"})},
        value="≤ 2 句",
        note="寒暄/近况分支：与通用上限相同，不构成新取值。",
    ),
    Constraint(
        id="len-whole-stranger",
        card="stage_execution_card",
        text="回复最多 1 句，只有问题确实需要时才补第 2 句",
        quantity="length_whole_reply",
        bound=1,
        condition={"stage": frozenset({"stranger"})},
        priority="override",
        value="≤ 1 句（必要时 2）",
        note="阶段卡提高优先级：更严 ⇒ 覆盖通用上限，是**分级**不是矛盾。",
    ),
    Constraint(
        id="final-whole-response-hook",
        card="final_role_voice_contract",
        text="答完要让对方接得上——他顺着能应一句",
        quantity="length_whole_reply",
        bound=2,
        value="1 句「可接应」的收尾（**不是**整条句数）",
        note=(
            "⚠ **抽取误判**，与 `topic-source-sentence` 同构：抽取器把「他顺着**能应一句**」"
            "算成了整条句数 ⇒ 与通用上限并列显示为两种取值。"
            "**它们不是同一个量** —— 这里说的是「答完要让对方接得上」，"
            "管的是**收尾的可接续性**，不是「整条回复只许 1 句」⇒ 与 1–2 句**兼容**。"
            "登记它只为消掉 `--against-scope` 的「未覆盖」报数（2026-10-05），"
            "**不是新增一条约束**，也不参与冲突判定。"
        ),
    ),
    Constraint(
        id="len-per-sentence",
        card="voice_execution_card",
        text="一句话通常十来个字，最多二十出头",
        quantity="length_per_sentence",
        bound=20,
        value="每句 ≤ 20 字",
        note="**另一个量**（每句 vs 整条）⇒ 与上面三条不同量，天然不冲突。",
    ),
    # ------------------------------------------------------------------
    # topic 路径专有（`app.py`：`payload["intent"] == "topic"` 时走，15 张卡）。
    # 卡名本身已隐含路径（只有 topic 路径才渲染这张卡），故不设 condition。
    # ------------------------------------------------------------------
    Constraint(
        id="topic-whole-length",
        card="topic_response_contract",
        text="只输出 NPC 的中文对白，1–2 句",
        quantity="length_whole_reply",
        bound=2,
        value="1–2 句",
        note="与通用上限同值。⚠ 只在这条路径出现，默认路径根本没这张卡。",
    ),
    Constraint(
        id="topic-source-sentence",
        card="topic_response_contract",
        text="无论话题从哪来，都必须有一句来源句",
        quantity="length_whole_reply",
        bound=2,
        value="1 句来源句（**必须包含**，是下限）",
        note=(
            "⚠ 抽取器把「一句来源句」算成了整条句数 ⇒ 报告里与同卡 `topic-whole-length` "
            "并列显示为两种取值。**它们不是同一个量**：一个是「整条最多 2 句」，"
            "一个是「必须含 1 句来源句」。开场一拍 + 来源句 = 2 句，正好落在 1–2 内 ⇒ **兼容**。"
        ),
    ),
    Constraint(
        id="topic-invite-guard",
        card="topic_response_contract",
        text="不要凭空完成未确认的邀约或事件",
        quantity="invite_action",
        bound=0,
        value="不得凭空完成未确认的邀约",
        note="topic 路径专有；与阶段卡的「不额外邀约」同向。",
    ),
    # ------------------------------------------------------------------
    # 亲密阶段 / 群聊专有 —— 只有**完整卡组**（`compact=False`）才渲染这些卡。
    # ⚠ 这一组是 2026-09-28 把群聊路径接进检查后才看见的：此前所有探针都用
    #    `compact=True`（单聊），`affection_*` 与 `voice_variation` 从未被扫过。
    # ------------------------------------------------------------------
    Constraint(
        id="affection-initiative-length",
        card="affection_initiative",
        text="让爱意在自然位置尽早出现（通常在前一两句或同一句中）",
        quantity="length_whole_reply",
        bound=2,
        value="1–2 句",
        note="与通用上限同值 ⇒ 不构成新取值。",
    ),
    Constraint(
        id="affection-initiative-actions",
        card="affection_initiative",
        text="maxActions: 1（然后最多一个亲密动作）",
        quantity="action_count",
        bound=1,
        value="1 个",
        note="与 `act-history-guard` 同值。",
    ),
    Constraint(
        id="affection-priority-length",
        card="affection_priority_final",
        text="爱意在自然位置尽早出现（通常在前一两句或同一句中）",
        quantity="length_whole_reply",
        bound=2,
        value="1–2 句",
        note="与通用上限同值。这张卡是**输出前最后一次默检**。",
    ),
    Constraint(
        id="group-turn-plan-invite",
        card="turn_plan",
        text="不主动加问题、邀约",
        quantity="invite_action",
        bound=0,
        value="不主动加问题或邀约",
        note="⚠ 只在**群聊（完整卡组）**出现；单聊的 `turn_plan` 没有这句。",
    ),
    Constraint(
        id="group-voice-variation-particle",
        card="voice_variation",
        text="一组三轮对话最多自然使用一次",
        quantity="particle_frequency",
        bound=1,
        value="三轮最多 1 次",
        note="⚠ 只在**群聊（完整卡组）**出现；`voice_variation` 是群聊专有卡。",
    ),
    # ------------------------------------------------------------------
    # 以下为 2026-09-28 06:02 按「铺开清单」补齐的 5 组（由
    # `check_prompt_consistency.py --against-scope` 列出）。
    # ------------------------------------------------------------------
    Constraint(
        id="act-stage",
        card="stage_execution_card",
        text="最多再追加一个具体动作（细节、追问、选择或小安排）",
        quantity="action_count",
        bound=1,
        value="≤ 1 个动作",
        note=(
            "标签是「**表达预算**」—— 是**上限**，不是许可。"
            "它管**数量**；`initiative` 管的「不为延长对话而反问」是**动机**。"
            "2026-09-28 曾把这两者误判成同卡矛盾。"
        ),
    ),
    Constraint(
        id="act-role-contract",
        card="final_role_voice_contract",
        text="最多加入一个角色化细节或态度",
        quantity="action_count",
        bound=1,
        value="≤ 1 个细节",
        note="与 act-stage 上界相同 ⇒ 不冲突。",
    ),
    Constraint(
        id="invite-action",
        card="stage_execution_card",
        text="初识阶段不得反问、邀约或主动换题",
        quantity="invite_action",
        bound=0,
        condition={"stage": frozenset({"stranger"})},
        priority="override",
        value="stranger 不得邀约",
    ),
    Constraint(
        id="invite-schedule",
        card="final_role_voice_contract",
        text="不把当前动作改写成未来日期、预约或固定时长，不使用社交排期承诺",
        quantity="schedule_commitment",
        bound=0,
        value="不得承诺时间",
        note=(
            "与 invite-action **不是同一个量**：前者禁**邀约行为**、后者禁**给时间承诺**。"
            "⚠ 另注：stranger 的「不得反问」与招牌动作「再反问一句把话头交回对方」"
            "**仍未录入台账** —— 招牌动作来自 `voiceActions`，需要单独确认它属于哪个量。"
        ),
    ),
    Constraint(
        id="topic-single",
        card="safety_rules",
        text="…玩家那句话只是由头，只保留一个平实事实或感受",
        quantity="topic_count",
        bound=1,
        condition={"input": frozenset({"greeting", "status_query"})},
        value="≤ 1 个话题",
        note="全 prompt 只此一处 ⇒ 无双条目可比，结构上不可能冲突。",
    ),
    Constraint(
        id="act-affection",
        card="affection_priority_final",
        text="最多一个动作",
        quantity="action_count",
        bound=1,
        value="≤ 1 个动作",
        note=(
            "只在四阶段全查时才出现（stranger 阶段无此卡）。"
            "**未设 condition**：它究竟在哪些阶段进卡尚未实测，"
            "而 condition 设错会导致**漏判** —— 按「宁可漏判，不可误判」保守处理。"
            "与 act-stage / act-role-contract 上界同为 1 ⇒ 不冲突。"
        ),
    ),
    # ------------------------------------------------------------------
    # `followup_count`（反问 / 追问）—— 2026-09-28 06:15 定位：**按阶段分级**，不是冲突。
    # 判为成立的关键**不是**我的解读，而是阶段卡里的一句明文：
    # 「它是可执行约束，**优先于泛化的热情、礼貌或延长对话倾向**」。
    # ------------------------------------------------------------------
    Constraint(
        id="followup-stranger",
        card="stage_execution_card",
        text="初识阶段不得反问、邀约或主动换题",
        quantity="followup_count",
        bound=0,
        condition={"stage": frozenset({"stranger"})},
        priority="override",
        value="stranger 不得反问",
        note="阶段卡自带「优先于泛化倾向」的声明 ⇒ 压得住招牌动作。",
    ),
    Constraint(
        id="followup-acquaintance",
        card="stage_execution_card",
        text="只有玩家明确留下空间时才问一个问题",
        quantity="followup_count",
        bound=1,
        condition={"stage": frozenset({"acquaintance"})},
        priority="override",
        value="acquaintance 最多 1 次",
    ),
    Constraint(
        id="followup-open",
        card="stage_execution_card",
        text="允许自然反问或提出下一步，必须来自当前话题",
        quantity="followup_count",
        bound=None,
        condition={"stage": frozenset({"friend", "close", "dating", "married"})},
        priority="override",
        value="friend 起允许反问",
        note=(
            "**故意不设 bound**：原文没有上限数字，硬填一个反而会触发误判。"
            "按「宁可漏判，不可误判」处理。"
        ),
    ),
    Constraint(
        id="followup-signature-move",
        card="persona_core",
        text="尴尬或被撞见时用省略号吞掉半句，再反问一句把话头交回对方",
        quantity="followup_count",
        bound=1,
        value="招牌动作含 1 次反问",
        note=(
            "来自角色数据（`voiceActions`），属**泛化倾向** ⇒ 优先级低于阶段卡。"
            "⚠ 原文在 `persona_core`（抽取器实际报出的卡）与 `voice_execution_card` "
            "**两张卡里都出现**，这里按抽取器报的卡记。"
            "⚠ 2026-09-28 修正：此前「追问数」正则要求「最多/只」限定词，抓不到"
            "「再反问一句」，于是这条只能靠手写、不受 `--against-scope` 保护。"
            "放宽正则并补 `再反问 N 句` 形态后它已被覆盖。"
        ),
    ),
    # ---- 2026-09-28 放宽抽取后新暴露的量约束（原来全被正则漏掉）----
    Constraint(
        id="len-per-sentence-persona",
        card="persona_core",
        text="一句话通常十来个字，最多二十出头；话多了就断成第二句",
        quantity="length_per_sentence",
        bound=20,
        value="每句 ≤20 字",
        note="是**每句**长度而非整条句数 ⇒ 已在 CARD_QUANTITY_OVERRIDES 改判量名。",
    ),
    Constraint(
        id="len-per-sentence-voice",
        card="voice_execution_card",
        text="角色常态句式参考（控制句长和语域）：一句话通常十来个字，最多二十出头",
        quantity="length_per_sentence",
        bound=20,
        value="每句 ≤20 字",
        note="与 len-per-sentence-persona **同量同值** ⇒ 一致，是同义分层而非冲突。",
    ),
    Constraint(
        id="act-history-guard",
        card="post_history_voice_guard",
        text="最多加入一个角色化细节或态度",
        quantity="action_count",
        bound=1,
        value="最多 1 个细节/态度",
        note="与 act-stage / act-role-contract 上界同为 1 ⇒ 不冲突。",
    ),
    Constraint(
        id="act-story-state",
        card="story_state",
        text="可以主动关心、分享或提出一个具体下一步",
        quantity="action_count",
        bound=1,
        value="最多 1 个具体下一步",
        note="与 act-stage / act-role-contract 上界同为 1 ⇒ 不冲突。",
    ),
    Constraint(
        id="followup-signature-move-voice",
        card="voice_execution_card",
        text="（同一条招牌动作，也出现在这张卡里）",
        quantity="followup_count",
        bound=1,
        value="招牌动作含 1 次反问",
        note=(
            "与 `followup-signature-move` 是**同一句原文**，但抽取器在 `persona_core` 与 "
            "`voice_execution_card` **两张卡**里都能命中 ⇒ **两张卡都要记**，"
            "否则 `--against-scope` 会报「voice_execution_card × followup_count」缺口。"
        ),
    ),
    Constraint(
        id="particle-frequency",
        card="voice_execution_card",
        text="一组三轮对话最多自然使用一次，也可以一次都不用",
        quantity="particle_frequency",
        bound=1,
        condition={"window": frozenset({"three_turns"})},
        value="3 轮内最多 1 次",
        note=(
            "口语颗粒（嗯/唔/啊）的使用频率上限。条件维度是**时间窗口**而非关系阶段，"
            "所以它天然不会与阶段卡的量冲突 —— 但仍要录入，否则 `--against-scope` "
            "会一直报「voice_execution_card × particle_frequency」缺口。"
        ),
    ),
)

#: 收束**之前**的状态 —— 用作判定规则的**回归对照**：规则必须把它判成冲突。
#:
#: ⚠ 本组数据第一版**漏了一条**（`legacy-greeting`），自测当场 FAIL ——
#: 而漏掉的正是唯一能判出冲突的那一对。**台账漏条目 = 判不出冲突**，
#: 所以完整性不能靠手写保证，必须与「实际渲染出的 prompt」逐条对照
#: （这是 `check_prompt_consistency.py` 下一步该做的事，见 `docs/constraint-scope.md` §三）。
LEGACY_BEFORE_FIX: tuple[Constraint, ...] = (
    Constraint(
        id="legacy-general",
        card="safety_rules",
        text="中文通常 1–3 句、15–80 字",
        quantity="length_whole_reply",
        bound=3,
        value="1–3 句 / 15–80 字",
    ),
    Constraint(
        id="legacy-greeting",
        card="safety_rules",
        text="…玩家那句话只是由头，只保留一个平实事实或感受，最多两句",
        quantity="length_whole_reply",
        bound=2,
        condition={"input": frozenset({"greeting", "status_query"})},
        value="≤ 2 句",
        note="与 legacy-general 同量、条件重叠、优先级同为 default，上界 2 vs 3 ⇒ 真冲突。",
    ),
    Constraint(
        id="legacy-topic-path",
        card="safety_rules(topic_request 分支)",
        text="只输出 NPC 的中文对白，1–3 句，…",
        quantity="length_whole_reply",
        bound=3,
        value="1–3 句",
        note="与 legacy-general 取值相同 ⇒ 本身不冲突，但它把「上界 3」又多写了一遍。",
    ),
    Constraint(
        id="legacy-close",
        card="stage_policy.close.responseShape",
        text="2–3 句",
        quantity="length_whole_reply",
        bound=3,
        condition={"stage": frozenset({"close"})},
        priority="override",
        value="2–3 句",
        note="阶段卡，优先级更高 —— 不得单独判为冲突（这是分级）。",
    ),
    Constraint(
        id="legacy-stranger",
        card="stage_execution_card",
        text="回复最多 1 句",
        quantity="length_whole_reply",
        bound=1,
        condition={"stage": frozenset({"stranger"})},
        priority="override",
        value="≤ 1 句",
    ),
)


#: 规则级案例：四条判定规则**每条**都要有「应报出」与「应跳过」两个方向。
#:
#: ⚠ 为什么需要它：上面的 `LEGACY_BEFORE_FIX` / `CURRENT` 只测**总量**
#: （收束前 >0、收束后 ==0）。若把 `quantity !=` 误写成 `==`、或把优先级
#: 比较写反，**总量断言可能仍然通过** —— 判定引擎会静默失效，
#: 而整个台账的价值都建立在它上面。
_RULE_CASES: tuple[tuple[str, tuple[Constraint, ...], int], ...] = (
    (
        "规则1 不同量 ⇒ 不报（哪怕条件重叠、界不同）",
        (
            Constraint(id="c1a", card="c", text="t", quantity="length_whole_reply", bound=2, value="2"),
            Constraint(id="c1b", card="c", text="t", quantity="length_per_sentence", bound=20, value="20"),
        ),
        0,
    ),
    (
        "规则2 条件不重叠 ⇒ 不报（同量、同优先级、界不同）",
        (
            Constraint(id="c2a", card="c", text="t", quantity="length_whole_reply", bound=2,
                       condition={"stage": frozenset({"friend"})}, value="2"),
            Constraint(id="c2b", card="c", text="t", quantity="length_whole_reply", bound=3,
                       condition={"stage": frozenset({"close"})}, value="3"),
        ),
        0,
    ),
    (
        "规则3 优先级不同 ⇒ 不报（这是覆盖关系，不是矛盾）",
        (
            Constraint(id="c3a", card="c", text="t", quantity="length_whole_reply", bound=3, value="3"),
            Constraint(id="c3b", card="c", text="t", quantity="length_whole_reply", bound=2,
                       priority="override", value="2"),
        ),
        0,
    ),
    (
        "规则4 上界相同 ⇒ 不报",
        (
            Constraint(id="c4a", card="c", text="t", quantity="length_whole_reply", bound=2, value="2"),
            Constraint(id="c4b", card="c", text="t", quantity="length_whole_reply", bound=2, value="2"),
        ),
        0,
    ),
    (
        "四条全满足 ⇒ 报出 1 条",
        (
            Constraint(id="c5a", card="c", text="t", quantity="length_whole_reply", bound=3, value="3"),
            Constraint(id="c5b", card="c", text="t", quantity="length_whole_reply", bound=2, value="2"),
        ),
        1,
    ),
    (
        "非数值量（bound=None）⇒ 宁可漏判，不报",
        (
            Constraint(id="c6a", card="c", text="t", quantity="invite_action", value="禁"),
            Constraint(id="c6b", card="c", text="t", quantity="invite_action", bound=1, value="许"),
        ),
        0,
    ),
)


def summarize(constraints: tuple[Constraint, ...], title: str) -> int:
    """打印判定结果，返回冲突条数。"""
    print("=" * 78)
    print(title)
    print("=" * 78)
    conflicts = find_conflicts(constraints)
    if not conflicts:
        print("  未发现冲突。")
    for conflict in conflicts:
        print("  " + conflict.describe())
    print()
    return len(conflicts)


if __name__ == "__main__":
    # 规则级案例先跑：它们直接钉住四条判定规则的**方向性**，
    # 比下面的总量断言更早暴露「引擎写反了」。
    rule_ok = True
    for title, case, expected in _RULE_CASES:
        got = len(find_conflicts(case))
        mark = "OK  " if got == expected else "FAIL"
        if got != expected:
            rule_ok = False
        print(f"[{mark}] {title} —— 期望 {expected} 条，实际 {got} 条")

    # 回归对照：规则**必须**把收束前的状态判成冲突，把收束后判成无冲突。
    before = summarize(LEGACY_BEFORE_FIX, "收束之前（期望：判出冲突）")
    after = summarize(CURRENT, "当前状态（期望：无冲突）")

    print("-" * 78)
    ok = rule_ok
    if before == 0:
        print("[FAIL] 收束前应判出冲突，实际 0 条 —— 判定规则太松。")
        ok = False
    else:
        print(f"[OK] 收束前判出 {before} 条冲突。")
    if after != 0:
        print(f"[FAIL] 当前状态不该有冲突，实际 {after} 条 —— 判定规则太松。")
        ok = False
    else:
        print("[OK] 当前状态无冲突。")
    raise SystemExit(0 if ok else 1)
