"""对白边界的唯一定义：收口标记、重新拉开、渠道方向与事件锁。

## 为什么有这一个模块

2026-09-20 的语义层审计（`docs/semantic-duplication-audit-2026-09-20.md` P1 #16～#21）
发现同一批概念被两处独立实现，**两处都跑、结论却相反**：

- 「玩家是否在收口／要空间」：`guard` 认 23 条字面标记，`behavior_quality` 的正则不认
  `不用陪`／`别过来`／`心情很差`，于是同一句「你先休息吧。」运行时放过、离线评测判
  `missing_proactive_affection`。
- 「NPC 是否在自然收口」：反向差集 9 条只在离线评测一侧。
- 「收口后有没有重新拉开」：`guard` 只在 conversation lead 启用时才采信共享诊断。
- 「有没有给出具体安排」：`specific_plan` 有三套判定，同一份诊断里能同时出现
  `specific_plan` 与 `companionship_only`。
- 「渠道越界」：`wrong_channel` 两套标记表，且离线评测缺 face_to_face 方向。

修法不是「把 A 抄给 B」，而是**提取单一实现、两处共用**——`guard`、
`behavior_quality`、`character_quality_eval` 一律从这里取表和判定。合并口径默认取
**并集**（识别范围更宽）：运行时放过的，离线评测也该放过。

## 这里的依赖纪律

本模块只放**表与纯判定**，不 import 任何 bridge 模块，避免与
`behavior_quality` → `guard` → `character_quality_eval` 的既有依赖方向成环。
需要「个人亲近信号」这类上层诊断时，由调用方传入判定函数（见
`violates_event_gate` 的 `detect_personal_affection` 形参）。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

_CONVERSATION_LEAD_PLAYER_CLOSING_PATTERN = re.compile(
    r"(?:先走|先休息|先睡|晚安|不打扰|就这样|"
    r"我不想(?:再)?(?:聊|说|谈)|不想(?:再)?(?:聊|说|谈)(?:这个|了)?|"
    r"(?:下次|改天)再聊(?:[吧呀啊呢]?)(?:[。！!?]?\s*)$|"
    r"(?:晚点|过会儿|等会儿)(?:再)?(?:联系|聊|说|回你|找你))"
)

# 字面表里的时间词也可能是**开场铺垫**而不是收口：
# 「下次再聊的时候，你愿意告诉我那件事吗？」是提问，不是要结束。
# 因此这两个标记带 `的时候` 时不算收口信号（P1 #16 的边界）。
_FUTURE_CHAT_MARKERS = ("下次再聊", "改天再聊")
_FUTURE_CHAT_CONTINUATION_PATTERN = re.compile(r"的时候")

# 「玩家在收口／要空间」：guard 的运行时常量表与离线正则的并集。
PLAYER_CLOSE_MARKERS: tuple[str, ...] = (
    "不打扰",
    "先休息",
    "先睡",
    "先走",
    "晚安",
    "下次再聊",
    "改天再聊",
    "不想聊",
    "不想再聊",
    "不想再说",
    "不想再谈",
    "不想谈",
    "不用陪",
    "别过来",
    "别逼我",
    "没心情",
    "心情很差",
    "很难受",
    "就这样吧",
    "先不说了",
    "晚点再联系",
    "晚点联系",
    "晚点再聊",
)

# 「NPC 在自然收口」：guard 的回复标记与离线评测的 guarded 收口标记的并集。
# 并集里 `去吧`／`路上小心`／`注意安全` 这类**交付式关心**确实比 guard 原有集合宽：
# 代价是「玩家收口 + NPC 说去吧」时不再触发亲密重试。当前离线评测本来就是这样判的，
# 统一到并集后两处一致（见 P1 #17）。
NPC_CLOSE_REPLY_MARKERS: tuple[str, ...] = (
    "明天再聊",
    "下次再聊",
    "改天再聊",
    "明天见",
    "下次见",
    "改天见",
    "好好休息",
    "早点休息",
    "早点睡",
    "先睡吧",
    "睡吧",
    "先睡了",
    "晚安",
    "先休息",
    "早点钻被窝",
    "休息吧",
    "明天再联系",
    "不打扰你",
    "不想聊",
    "先这样",
    "到这吧",
    "回头见",
    "回头再见",
    "去吧",
    "路上小心",
    "注意安全",
)

# 「NPC 说出了自己的边界」：只出现在 guard 侧，离线评测目前不消费这张表；
# 保留在共享模块里，供将来两处共用同一份定义。
NPC_BOUNDARY_REPLY_MARKERS: tuple[str, ...] = (
    "想一个人待",
    "需要一点空间",
    "需要空间",
    "别过来",
    "不想见人",
    "今天状态很差",
    "状态也不好",
    "状态不好",
    "真撑不住",
    "累得不行",
    "今天太累",
    "早点钻被窝",
    "先睡吧",
    "休息吧",
    "明天再联系",
    "没法陪你多聊",
    "想静一静",
    "别等我",
    "让我缓缓",
    "别说了",
    "不说了",
    "不聊了",
    "别勉强",
    "别跟我较劲",
)

# 「NPC 的收口式照顾」：guard 一侧的判定表，与 `NPC_CLOSE_REPLY_MARKERS` 分开，
# 因为「收口」与「照顾」在重试链里是可区分的两类证据。
NPC_CARE_REPLY_MARKERS: tuple[str, ...] = (
    "吃点东西",
    "别空着肚子",
    "弄点吃的",
    "热一下就吃",
    "躺下睡觉",
    "不会烦你",
    "带点吃的",
    "先休息",
    "早点休息",
    "早点睡",
    "别担心",
    "照看你",
    "帮你吃点",
    "帮你休息",
)

# 「收口之后又把对话拉开」的动作词。
NPC_CLOSE_REOPENING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:明天|下次|改天|过会儿|等会儿|之后|以后|晚点|等下|回头).{0,16}"
        r"(?P<action>来|过来|一起|见面|约|帮我|帮你|找我|陪我|看看|送|带|拿|准备|联系|告诉|问|安排)"
    ),
    re.compile(
        r"(?:要不要|有空).{0,16}"
        r"(?P<action>来|过来|一起|见|约|帮我|帮你|找我|陪我|送|带|拿|准备|联系|告诉|问|安排)"
    ),
    re.compile(
        r"(?:别(?:急着)?走|先别走|等等|别急).{0,12}(?:接着|继续|再).{0,8}"
        r"(?P<action>说|聊|讲|谈|看|听)"
    ),
)

# 「收口之后的动作被明确否定」——命中就不算重新拉开。
NEGATED_FUTURE_ACTION = re.compile(r"(?:别|不要|不用|不必|无需).{0,3}$")

# 句末反问所在的**分句**带着否定时，这个反问是被否定动作的一部分，不算重新拉开：
# 「你别跟我较劲行不行？」只有那句顶回去，没有把话题交回玩家。
NEGATED_FUTURE_ACTION_CLAUSE = re.compile(
    r"(?:别|不要|不用|不必|无需)[^，,。！？!?；;：:]{0,6}(?:走|过来|来|过来|聊|说|谈|看|听)"
    r"[^，,。！？!?；;：:]{0,8}$"
)

# 反问本身就要求玩家继续回答，因此也是「重新拉开」的一种——但**只有把选择交回
# 玩家的反问**才算。「你现在还好吗？」是收口里的关心，「你别跟我较劲行不行？」
# 是顶回去，都不算；「你想先听哪一种？」带着可继续的对象，才把话题重新拉回来。
#
# 口径故意比 `behavior_quality._CONVERSATION_LEAD_CHOICE_PATTERN` 窄：这里只做
# 「是否重新拉开」的兜底判定，宁可漏判也不误判（误判会把自然的关心式收口
# 拖进重试链）。若将来两处要共用，应把它上移成本模块的表并由两边引用。
SUBSTANTIVE_QUESTION_PATTERN = re.compile(
    r"(?:哪一种|哪一个|哪个|哪杯|哪首|哪一首|哪一组|哪组|哪袋|哪一袋|哪段|哪一段|"
    r"选一个)[^。！？!?]{0,12}[？?]"
)

# 渠道方向标记：线上回合不得写成已见面；当面回合不得写成线上约定。
# `behavior_quality` 与 `character_quality_eval` 共用同一份（P1 #21）。
REMOTE_ONLY_MARKERS: tuple[str, ...] = (
    "已经见面",
    "已经碰面",
    "就在你面前",
    "已经赴约",
    "过来找我",
    "我现在就在你面前",
    "到我这里来",
    "当面再说",
)
FACE_TO_FACE_MARKERS: tuple[str, ...] = (
    "发消息给我",
    "线上再聊",
    "下次视频",
)

WRONG_CHANNEL_TAG = "wrong_channel"

# 「有没有给出具体安排」的**唯一**判定（P1 #20）。
# 此前有三套：`_SPECIFIC_PLAN_PATTERNS` 正则、`specific_plan` 单字标记、
# 以及 conversation lead 自己的 `_CONVERSATION_LEAD_PLAN_PATTERN`，
# 结果是同一份诊断里能同时出现 `specific_plan` 与 `companionship_only`。
#
# 分工写清楚：
# - 本表是**内容**判定（是否真的给出可执行的安排），供 `specificPlanDetected`、
#   `specific_plan_only` 与 lead 的 `has_plan` 共用；
# - `behavior_quality._INITIATIVE_SIGNAL_MARKERS["specific_plan"]` 仍是**粗粒度
#   信号**（`今晚`／`一起` 等），只决定主动类型标签，不冒充「安排已发生」。
FUNCTIONAL_TASK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:收拾|整理|清理|修(?:好|理)?|搬(?:走|开)?|准备|过一遍|算完|喂鸡|浇|建|采购|交付|交给|给|查看|核对|汇报|交代|送|拿).{0,12}(?:鸡舍|账本|农活|工具|货物|材料|栅栏|农田|作物|订单|早餐|东西|建筑|房子|报告|记录|表格)"
    ),
    re.compile(
        r"(?:鸡舍|账本|农活|工具|货物|材料|栅栏|农田|作物|订单|早餐|东西|建筑|房子|报告|记录|表格).{0,12}(?:收拾|整理|清理|修(?:好|理)?|搬(?:走|开)?|准备|过一遍|算完|喂鸡|浇|建|采购|交付|交给|给|查看|看|核对|汇报|交代|送|拿)"
    ),
)
SPECIFIC_ARRANGEMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:一起|约).{0,8}(?:吃饭|骑车|散步|听歌|喝茶|出门|看画)"),
    re.compile(
        r"(?:陪你|陪我|和你|跟你|一起|一块|搭把手|帮你|帮(?:个)?忙).{0,12}"
        r"(?:收拾|整理|修(?:好|理)?|搬|清理|准备)"
    ),
    re.compile(r"(?:今晚|明天|改天).{0,12}(?:七点|几点|在.{0,8}见|安排|约)"),
    re.compile(r"(?:七点|几点).{0,12}(?:见|出发|过来)"),
    re.compile(
        r"(?:今晚|明天|改天|等会儿|一会儿|一起|陪你|陪我|和你|跟你|过来|去).{0,18}"
        r"(?:吃饭|喝茶|喝酒|听歌|骑车|散步|聊天|待着|坐一会儿|鸡舍|酒窖|训练|出门|见面)|"
        r"(?:把|将|我们把).{0,18}(?:抱|带|拿).{0,8}(?:过去|进去|过来)"
    ),
    *FUNCTIONAL_TASK_PATTERNS,
)

# 纯陪伴说法（「陪你坐一会儿」「陪你待一会儿」）**不是安排**：
# 没有时间点、没有可执行的事，只表达在场。这一条把「陪伴」与「安排」分开，
# 否则同一份诊断会同时得到两个互斥的「只有……」结论（P1 #20）。
PURE_COMPANIONSHIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:陪你|陪我|和你|跟你)(?:一起)?(?:先)?(?:坐|待|呆)(?:一?会儿|着|一下)"),
    re.compile(r"(?:一起|陪你|陪我)(?:先)?(?:坐|待|呆)着"),
)


def contains_marker(text: object, markers: tuple[str, ...]) -> bool:
    """大小写不敏感的标记命中判定；非字符串一律视为未命中。"""

    if not isinstance(text, str) or not text:
        return False
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in markers)


# 事件锁解锁前的「未达成亲密」阶段：此时只收窄主动亲密，不动日常照顾（P1 #22）。
EVENT_GATE_BLOCKED_STAGES = frozenset({"stranger", "acquaintance", "friend"})


def event_gate_effective_stage(event_gate: object) -> str:
    """读取事件锁投影出的叙事亲密上限；没有事件锁时返回空串。

    同时接受 mapping（prompt 里的 `eventGate` 卡片）与带
    `effective_intimacy_stage` 字段的结果对象（`relationship_gating` 的
    `RelationshipGateResult`），两处调用方因此可以共用同一判定。
    """

    if isinstance(event_gate, Mapping):
        value = event_gate.get("effectiveIntimacyStage")
    else:
        value = getattr(event_gate, "effective_intimacy_stage", None)
    return value.strip().casefold() if isinstance(value, str) else ""


def violates_event_gate(
    event_gate: object,
    reply: object,
    *,
    detect_personal_affection: Callable[[str], bool],
) -> bool:
    """事件未解锁时，回复里是否落下了**主动亲密**。

    事件锁只压制「专属亲密」，普通日常照顾不受影响；判据是调用方传进来的
    `detect_personal_affection`（`guard` 与 `character_quality_eval` 共用
    `behavior_quality.diagnose_personal_affection`），避免本模块反向依赖上层。
    """

    if not isinstance(reply, str) or not reply.strip():
        return False
    if event_gate_effective_stage(event_gate) not in EVENT_GATE_BLOCKED_STAGES:
        return False
    return bool(detect_personal_affection(reply))


def turn_plan_mode_from(payload: object) -> str:
    """从回合契约 payload 读出受支持的 `mode`；未知模式返回空串。"""

    if not isinstance(payload, Mapping):
        return ""
    value = payload.get("mode")
    if not isinstance(value, str):
        return ""
    mode = value.strip().casefold()
    return mode if mode in TURN_PLAN_MODES else ""


# 回合契约的窄执行模式（`turn_plan.mode` 的合法取值）。
TURN_PLAN_MODES = frozenset(
    {
        "answer_only",
        "answer_plus_detail",
        "answer_plus_lead",
        "answer_plus_warmth",
        "boundary_close",
        "explicit_intimacy",
    }
)


def affection_requirement_from_turn_plan(mode: object) -> str:
    """`turn_plan.mode` → 本轮的主动亲密要求（空串表示不要求）。

    这是 `guard._affection_requirement` 与
    `character_quality_eval._turn_for_plan_scoring` 的**唯一**映射表（P1 #19）：
    两处此前各写一份，一旦一边改了模式集合就会悄悄给出相反的结论。
    """

    normalized = str(mode or "").strip().casefold()
    if normalized in {"answer_only", "answer_plus_detail", "answer_plus_lead", "boundary_close"}:
        return ""
    if normalized in {"answer_plus_warmth", "explicit_intimacy"}:
        return "proactive"
    return ""


def is_player_closing(text: object) -> bool:
    """玩家是否在收口／要空间。

    字面表与正则**任一命中**即算，但字面表里带时间条件的两个标记
    （`下次再聊`／`改天再聊`）后面跟 `的时候` 时不算——那是开场铺垫。
    """

    if not isinstance(text, str) or not text.strip():
        return False
    if _CONVERSATION_LEAD_PLAYER_CLOSING_PATTERN.search(text):
        return True
    for marker in PLAYER_CLOSE_MARKERS:
        if marker not in text:
            continue
        if marker in _FUTURE_CHAT_MARKERS and _FUTURE_CHAT_CONTINUATION_PATTERN.search(
            text[text.index(marker) + len(marker) :]
        ):
            continue
        return True
    return False


def is_substantive_question(text: object) -> bool:
    """回复是否在提出**实质**追问（把选择交回玩家）。

    与「有没有问号」分开：收口回合里的关心式反问（「你现在还好吗？」）与
    顶回去式反问（「你别跟我较劲行不行？」）都不该被当成重新拉开。
    """

    if not isinstance(text, str) or not text.strip():
        return False
    if NEGATED_FUTURE_ACTION_CLAUSE.search(text):
        return False
    return bool(SUBSTANTIVE_QUESTION_PATTERN.search(text))


def is_npc_close_reply(text: object) -> bool:
    """NPC 的这句话是否属于自然收口。"""

    return contains_marker(text, NPC_CLOSE_REPLY_MARKERS)


def is_npc_boundary_reply(text: object) -> bool:
    """NPC 是否说出了自己的边界（要空间、状态差、别等我）。"""

    return contains_marker(text, NPC_BOUNDARY_REPLY_MARKERS)


def is_npc_care_reply(text: object) -> bool:
    """NPC 是否把收口落成了照顾式关心。"""

    return contains_marker(text, NPC_CARE_REPLY_MARKERS)


def reopens_after_close(reply: object) -> bool:
    """收口之后是否又用未来安排或追问把对话拉开；被否定的未来动作不算。

    顺序有意义：**先看动作表，最后才看实质反问**。带了未来动作的那一类
    （「明天过来帮我收拾」「别急着走，继续说」）无条件算重新拉开；
    只剩反问时才用实质追问兜底——收口里的「你现在还好吗？」与顶回去的
    「你别跟我较劲行不行？」都不算重新拉开。
    """

    if not isinstance(reply, str) or not reply:
        return False
    for pattern in NPC_CLOSE_REOPENING_PATTERNS:
        for match in pattern.finditer(reply):
            action_start = match.start("action")
            preceding = reply[max(match.start(), action_start - 6) : action_start]
            if NEGATED_FUTURE_ACTION.search(preceding):
                continue
            return True
    return is_substantive_question(reply)


def is_specific_arrangement(text: object) -> bool:
    """回复是否给出**可执行的具体安排**（时间／共同活动／约定动作）。

    纯陪伴说法先被排除：它们表达在场，不构成安排。
    """

    if not isinstance(text, str) or not text:
        return False
    if any(pattern.search(text) for pattern in PURE_COMPANIONSHIP_PATTERNS):
        return False
    return any(pattern.search(text) for pattern in SPECIFIC_ARRANGEMENT_PATTERNS)


def channel_direction_tag(
    channel: object,
    reply: object,
    *,
    tag: str = WRONG_CHANNEL_TAG,
) -> str:
    """渠道方向越界判定，`remote` 与 `face_to_face` 两个方向共用一张表。

    返回 `tag` 或空串；调用方据此决定是只记标签还是同时触发重试。
    """

    if not isinstance(channel, str) or not isinstance(reply, str) or not reply:
        return ""
    normalized = channel.strip().casefold()
    if normalized == "remote" and contains_marker(reply, REMOTE_ONLY_MARKERS):
        return tag
    if normalized == "face_to_face" and contains_marker(reply, FACE_TO_FACE_MARKERS):
        return tag
    return ""


_SENTENCE_BOUNDARY = r"[。！？!?；;，,、\n]"
_OPENING_SPLIT = re.compile(_SENTENCE_BOUNDARY)


def reply_opening(text: object) -> str:
    """回复的第一个分句（去空白）；没有内容时返回空串。"""

    if not isinstance(text, str) or not text.strip():
        return ""
    return _OPENING_SPLIT.split(text.strip(), maxsplit=1)[0].strip()


def reply_avoids_speech_particle(reply: object, particles: tuple[str, ...]) -> bool:
    """回复是否又用上了「历史已经用过」的口头颗粒（P1 #23）。

    判据与 `guard._repeats_history_speech_particle` 原先一致：颗粒出现在
    句首或标点之后才算，避免把词语内部同字误判成颗粒。
    `dialogue_style_quality` 与本判定同源后，运行时重试与离线标签才不会再
    一个说重复、一个说没重复。
    """

    if not isinstance(reply, str) or not reply.strip() or not particles:
        return False
    text = reply.strip()
    return any(
        re.search(
            rf"(?:^|[。！？!?；;：:，,\s…]){re.escape(particle)}",
            text,
        )
        for particle in particles
    )


# 句首语气颗粒：只是开口语气，不构成开场结构本身。
#
# 2026-09-21（用户实测「开场结构逐字重复」）：`reply_opens_with_marker` 原先用
# **逐字前缀**匹配，多一个「嘿，」就完全不命中——索菲亚第 1 轮
# 「我刚从蓝月亮葡萄园回来……」与第 3 轮「嘿，我刚从蓝月亮葡萄园回来……」
# 正是这样逃逸的：同一个开场在相邻两轮复用，运行时却判「没有重复」。
# 表放在本模块是因为这里是不 import 任何 bridge 模块的底层，
# `prompts`（生成 avoidOpenings/前缀）与 `guard`、`dialogue_style_quality`（判定）
# 共用同一份，避免又出现「两处各写一套、结论相反」。
LEADING_SPEECH_PARTICLES: tuple[str, ...] = (
    "嘿",
    "嗨",
    "嗯",
    "哦",
    "啊",
    "唔",
    "呃",
    "唉",
    "呀",
    "哎",
    "喂",
)
_LEADING_SPEECH_PARTICLE_PATTERN = re.compile(
    r"^(?:"
    + "|".join(map(re.escape, LEADING_SPEECH_PARTICLES))
    + r")[，,、。！？!?…\s]*"
)


def strip_leading_speech_particles(text: str) -> str:
    """剥掉句首的语气颗粒及紧随的停顿标点；没有颗粒时原样返回。"""

    if not isinstance(text, str) or not text:
        return text if isinstance(text, str) else ""
    return _LEADING_SPEECH_PARTICLE_PATTERN.sub("", text, count=1)


def reply_opens_with_marker(reply: object, markers: tuple[str, ...]) -> bool:
    """回复是否以给定标记（或其前缀）开头（P1 #23）。

    比对**忽略句首语气颗粒**：这条判定问的是「有没有复用历史开场」，而「嘿，」
    这类开口语气不属于开场结构本身。逐字匹配时「嘿，我刚从……回来」不会命中
    历史里的「我刚从……回来」，同一条开场便可在相邻两轮逐字复用而无人拦下
    （2026-09-21 用户实测的索菲亚第 1/3 轮）。
    """

    if not isinstance(reply, str) or not reply.strip() or not markers:
        return False
    text = reply.strip()
    candidates = (text, strip_leading_speech_particles(text))
    return any(
        candidate.startswith(marker)
        for candidate in candidates
        for marker in markers
        if marker
    )


def repeats_affection_shape(
    current_shape: object,
    previous_shape: object,
    *,
    allowed_close: bool = False,
) -> bool:
    """相邻轮次是否机械复用了同一种亲密形状（P1 #24）。

    这是 `guard._repeats_personal_affection_shape` 与
    `character_quality_eval.score_affection_variation` 的**唯一**判定：

    - 形状相同即算复用；
    - 明确收口（`allowed_close`）始终允许复用短句；
    - 「本轮是否带来新锚点」由调用方用 `has_new_anchor` 单独判定后传入。

    判据**只看形状，不看主动类型**：评测侧原先额外要求 kind 也相同，
    于是同一段相邻回复在运行时被改写、在评测里判「不机械」。既有用例
    `test_affection_variation_flags_same_personal_shape_even_when_kind_changes`
    正是钉住「kind 变了也算机械复用」的，因此 kind 一律不参与判定。
    """

    current = str(current_shape or "").strip()
    previous = str(previous_shape or "").strip()
    if not current or current != previous or allowed_close:
        return False
    return True

