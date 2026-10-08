from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from time import perf_counter

from .guard import ResponseGuard, missing_opening_grounding
from .models import (
    DialogueTestRequest,
    GroupDialogueRequest,
    GroupDialogueResponse,
    GroupParticipant,
    GroupTurn,
    NpcGameState,
    ProviderResult,
    ProviderUsage,
    RelationshipWorldContext,
)
from .providers import ProviderRouter


class GroupResponseError(ValueError):
    """多人回复不符合参与者或结构约束。"""


# 回放页已经用气泡展示发言人，对白里再写一遍名字会明显像评测腔。
_SPEECH_HYGIENE_RULE = (
    "对白只写这个角色真正会说出口的话：不要在对白开头重复写自己的名字或“名字：”，"
    "不要写括号里的舞台动作、旁白或具体日期。"
)

# 群聊里的角色差异过去只靠 npcId 撑着，模型会退回通用文艺腔。
# 2026-09-24：原来这里写「优先参考 voiceAnchors 的句式和**口语颗粒度**」，
# 但锚点样本的语气词密度是全库的 1.8 倍（见
# docs/report-kimi-filler-diagnosis-2026-09-24.md），照它复现会让参与者
# 都退化成同一种结巴。现在只要求参考句式，并把颗粒度说明成零星出现的。
_GROUP_NATURAL_CONTRACT = (
    "对白要像熟人聊天，不写评测答案：不写情绪标签和解释，"
    "不要写成散文或统一的书面模板，比喻只在角色本来就会用时才用；"
    "参考每个参与者 voice.voiceAnchors 的句式，"
    "口语颗粒（嗯、呃、啊等）在原作对白里是零星出现的，不必每句都带；"
    "多数时候直接说事实、动作或短感受。"
)

# 开场（接受邀约后、玩家一句话都还没说）时补给模型的那条 user 消息。
# ⚠ 必须是**非空**且**不假定玩家说过话**的旁白 —— 见 build_group_messages 里的注释。
_GROUP_OPENING_NUDGE = "（玩家还没有说话，你们先聊。）"

# 解析失败只重试一次：把整条多轮结果丢掉太亏，但也不能无限重试。
_FORMAT_REPAIR_RULE = (
    "上一次输出不是合法 JSON，或者回合数超出了上限。现在只输出一个 JSON 对象："
    '{"turns":[{"speakerNpcId":"名单内 ID","content":"对白","addressedTo":[]}]}。'
    "不要 Markdown 代码块、不要解释、不要任何多余文字；"
    "每个回合都必须同时有 speakerNpcId 和 content。"
)

# ---------------------------------------------------------------------------
# 角色卡拼接时的**归属**（2026-09-22，群聊云端验证 BUG-1）
# ---------------------------------------------------------------------------
#
# 背景：multi_turn 只用**一次** provider 调用同时演名单里的所有人，
# 所以 `build_group_messages` 必须把**每份**参与者角色卡都拼进同一个 messages
# 数组（详见该函数内的注释）。而角色卡与私聊同源，每份卡里都带着自己的语气样例
# （`prompts.py` 的 `original_style_example_assistant`，3 人场实测 4 条/人）。
#
# 实测（`.tmp/group-cloud-verify/dump_shape.py`，3 人场 0 请求）：
# 76 条消息里 12 条 assistant 的 `name` **一字不差**都是
# `original_style_example_assistant`，三人的样例被压平进同一个数组、
# 无任何归属字段——模型只能靠正文猜「这条是谁的」，
# 于是会把 A 的语气样例读成「群里某人说过的话」（对应 BUG-2 的事实串味）。
#
# 修法**不删样例**：删掉别人的样例会让模型失去多人语气依据（multi_turn 要演所有人），
# 而样例必须留在 assistant 位置（`prompts.py` 记录过 Sophia 的实证：移除
# assistant few-shot 会掉语气）。因此只在拼装处补两层归属：
# 1. 每条语气样例的 `name` 带上该参与者（`_style_example_name`）；
# 2. 合并多份卡时，每份卡前插一张 `participant_card_boundary` 划出边界。

#: `prompts.py` 里语气样例消息的 name（私聊、群聊同源）。加归属时保留这个前缀，
#: 既有的 `startswith` 式识别与工具不受影响。
_STYLE_EXAMPLE_NAME = "original_style_example_assistant"

#: 参与者卡之间的分隔卡：多份卡拼接时用来划出「以下这一段属于谁」。
_PARTICIPANT_CARD_BOUNDARY_NAME = "participant_card_boundary"

#: 上游对 `message.name` 的限制（OpenAI 兼容：`^[a-zA-Z0-9_-]{1,64}$`）。
#: npcId 一般就是游戏内英文名，但 mod NPC 的 id 没有字符集保证，所以统一清洗。
_NAME_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_-]")
_NAME_MAX_LENGTH = 64


def _style_example_name(npc_id: str) -> str:
    """把语气样例的 `name` 归属化：`original_style_example_assistant_<npcId>`。"""

    suffix = _NAME_UNSAFE_CHARS.sub("_", str(npc_id).strip()).strip("_")
    if not suffix:
        return _STYLE_EXAMPLE_NAME
    room = _NAME_MAX_LENGTH - len(_STYLE_EXAMPLE_NAME) - 1
    if room <= 0:  # pragma: no cover - 前缀本身远短于上限，留作防御
        return _STYLE_EXAMPLE_NAME
    return f"{_STYLE_EXAMPLE_NAME}_{suffix[:room]}"


def _participant_card_boundary(npc_id: str, display_name: str) -> dict[str, str]:
    """一份参与者卡开始处的边界卡：明确「这一段消息属于谁」。

    没有它，多份卡的卡名完全相同（`safety_rules`、`persona_core` … 各三轮），
    模型只能跨二十多条消息自己推断段落归属——实测它推不出来（见 BUG-2）。
    """

    return {
        "role": "system",
        "name": _PARTICIPANT_CARD_BOUNDARY_NAME,
        "content": json.dumps(
            {
                "npcId": npc_id,
                "displayName": display_name,
                "scope": (
                    "以下是这位参与者一个人的角色卡（直到下一张 "
                    f"{_PARTICIPANT_CARD_BOUNDARY_NAME} 为止）："
                    "这一段里的“当前 NPC”“你”都只指他，不指名单里的其他人。"
                    "其中 role=assistant 的消息是他自己的原版语气示例，"
                    "不是本场群聊里任何人说过的话，也不是别人转述给他的话；"
                    "只学这些原句的说法方式，示例里的事实、人物、宠物、事件都属于"
                    "示例本身，不属于本场对话，也不能记到别人头上。"
                ),
            },
            ensure_ascii=False,
        ),
    }


def _participant_value(
    participant: GroupParticipant | Mapping[str, object],
    key: str,
    alias: str,
) -> object:
    if isinstance(participant, GroupParticipant):
        return getattr(participant, key)
    return participant.get(alias, participant.get(key))


# ---------------------------------------------------------------------------
# 参与者**私有上下文**卡（2026-10-05：「群聊与晨间话题的有机统一」的地基）
# ---------------------------------------------------------------------------
#
# 场景卡 `group_scene` 里的 `recentFacts` / `relationshipWorld` 是**无归属的单槽位**，
# 而群聊有 2～3 位参与者：放进去的那一份是「按某个 NPC 视角过滤过的记忆与关系」，
# 另外两人读到它，就等于知道了「玩家只跟那个人私下说过的事」——比不传更糟。
# 所以生产端（`GroupDialogueMenu`）从 2026-09-22 起一直给这两个槽位传 null。
#
# 正确做法是把槽位下移到参与者身上，并在这里渲染成**带归属的卡**：卡名带 npcId、
# 卡内写明「这些只属于他，别人并不知道」。这与下面 `_participant_card_boundary`
# 是同一套思路——2026-09-22 的 BUG-2 已经证明，模型串味的原因是**没有归属**，
# 而不是「它看到了别人的内容」（multi_turn 本来就会把所有人的卡拼进同一个数组）。

#: 私有上下文卡的名字前缀；与语气样例一样按 npcId 归属化。
_PARTICIPANT_CONTEXT_NAME = "participant_private_context"

_PARTICIPANT_CONTEXT_SCOPE = (
    "以下是这位参与者一个人的私有上下文，只属于他：这些记忆与关系视角都是"
    "他自己知道的事，名单里的其他人并不知道，也没有对他说过这里的内容。"
    "不要让名单里的其他人说出、知道、认领或转述这里的事实；"
    "他本人也不必主动提起，只在话题自然相关时才用，"
    "并且不要把它当成本场群聊里已经公开说过的话。"
)


def _participant_context_name(npc_id: str) -> str:
    """把私有上下文卡的名字归属化（规则与 `original_style_example_assistant` 一致）。"""

    return _style_example_name(npc_id).replace(
        _STYLE_EXAMPLE_NAME, _PARTICIPANT_CONTEXT_NAME, 1
    )


def _participant_entry(
    participants: Sequence[GroupParticipant | Mapping[str, object]],
    npc_id: str,
) -> GroupParticipant | Mapping[str, object] | None:
    """按 npcId 取回参与者条目（大小写不敏感）。"""

    target = npc_id.casefold()
    for item in participants:
        if str(_participant_value(item, "npc_id", "npcId")).casefold() == target:
            return item
    return None


def _participant_private_context(
    *,
    npc_id: str,
    display_name: str,
    relationship_world: object,
    recent_facts: object,
) -> dict[str, str] | None:
    """这位参与者自己的私有上下文卡；两样都空时返回 None（不插空卡）。"""

    # `exclude_defaults=True` 不是省字：`RelationshipWorldContext` 的每个字段默认都是
    # 空集合，而生产端的快照**总有对象**（没有关系时也是一个全空对象，而不是 None）。
    # 不排除默认值的话，每位参与者都会多出一张 `objectiveRelationships: [] …` 的空卡，
    # 而且 `has_world` 会把它当成"有关系内容"——空卡对模型只是噪声，还白花钱。
    dump = getattr(relationship_world, "model_dump", None)
    world = (
        dump(by_alias=True, exclude_none=True, exclude_defaults=True)
        if callable(dump)
        else relationship_world
    )
    facts = [
        str(item).strip() for item in (recent_facts or ()) if str(item).strip()
    ]
    has_world = bool(world)
    if not has_world and not facts:
        return None

    return {
        "role": "system",
        "name": _participant_context_name(npc_id),
        "content": json.dumps(
            {
                "npcId": npc_id,
                "displayName": display_name,
                "scope": _PARTICIPANT_CONTEXT_SCOPE,
                "relationshipWorld": world if has_world else {},
                "recentFacts": facts,
            },
            ensure_ascii=False,
        ),
    }


def _group_scene_instruction(
    *,
    active_npc_id: str,
    roster_ids: list[str],
    strategy: str,
    turn_count: int | None,
    is_opening: bool = False,
    topic: str | None = None,
) -> str:
    """群聊场景指令。

    ``is_opening`` 表示**玩家一句话都还没说**（接受邀约后正是这个状态）：
    此时不能让模型“接玩家”，而要它自己起个头，且**不得假定玩家说过任何话**。
    """
    others = [item for item in roster_ids if item.casefold() != active_npc_id.casefold()]
    other_rule = (
        "不能替 " + "、".join(others) + " 发言。" if others else "不能替其他 NPC 发言。"
    )
    # 开场（玩家一句话都还没说）时不能让模型“接玩家”，而要它自己起个头。
    first_speaker_rule = (
        "玩家还没有说话，请由名单里最自然的那个人先起个头"
        "（可以提起邀约里的由头，也可以说说自己的近况），"
        "之后由内容和角色决定谁接；"
        "不要假定玩家说过任何话，也不要替玩家发言；"
        if is_opening
        else "第一个发言的人先接玩家，之后由内容和角色决定谁接；"
    )
    # 2026-10-09：把邀约由头提到 instruction 的**最前面**。
    # 此前 topic 只是 group_scene JSON 里的一个字段，排在 1500 字格式规则之后，
    # 而那段规则明写「这些回合不需要推进话题」「允许打岔、突然说起别的事」——
    # 模型因此有理有据地不聊主题。instruction 是它唯一会逐字读的地方。
    topic_lead = (
        f"本次群聊的由头：{topic}。这轮对话要真的围绕这个由头展开，"
        "不要跑题去聊天气、农活或别处的传闻。"
        if topic
        else ""
    )
    if strategy == "multi_turn":
        limit = turn_budget(turn_count, len(roster_ids))
        return topic_lead + (
            "这是公开线上群聊，channel=remote。像几个熟人同时在群里说话，"
            "不要写成轮流做任务汇报。"
            "自然节奏优先于任何格式要求：长度要参差，可以只有两三个字，也可以连着说两三句，"
            "不要人人一句等长；允许只是附和、追问、吐槽或重复对方一个词表示在听，"
            "这些回合不需要推进话题；允许打岔、突然说起别的事、说到一半停住，"
            "也可以有人整场不说话；不要每条都以总结、感悟或小道理收尾，"
            "也不要写“我先说……你呢？”这种对称发言模板。"
            "谁说话："
            + first_speaker_rule
            + "有人想接别人的话就自然接，不必每条都严丝合缝地对上，"
            "几个人各给一条建议、各说各的近况都很正常；"
            "但不要让一个人把话说完：名单里每个人都应有机会开口，"
            "两个人里不要只有一个人说话，三个人里也不要只出现一个人。"
            "如果某条对白点名或提到了名单里的另一个人，那个人应当接一轮，"
            "不能只被别人议论却没有自己的回合；整段至少出现一次真正的来回。"
            "事实与指代要准确：说“你们”时只指名单里除自己以外的人，人数必须与名单一致"
            "（只有两个别人就说“你们俩”，别写“你们仨”）；把自己也算进去时说“我们”。"
            "人称要自然：对名单里某个人说话时直接用“你”，不要当面叫他的名字或用第三人称"
            "（对 Harvey 说“你大概不会同意”而不是“Harvey 大概不会同意”）；"
            "只有对玩家说话、或提到不在场的人时才用名字。"
            "addressedTo 要和这句话的人称对上：对某个 NPC 说“你”时才填他的 ID；"
            "如果是在对玩家说、只是提到某个 NPC（说“他”“她”或名字），就留空数组。"
            f"最多输出 {limit} 个公开回合，每个回合只说对应 speakerNpcId 自己的话。"
            "addressedTo 只能填这条对白真正在回应或递给的人，且只能填名单内的参与者 ID；"
            "回应玩家时留空数组，不要写 player、you 之类的代称。"
            "每张角色卡只描述它自己；本轮允许同时输出这些角色的对白，"
            "这部分覆盖角色卡里“只输出当前 NPC 的对白”的收尾限制，但不得因此改变任何角色的说话方式。"
            "不能让名单外 NPC 加入，不能把远程聊天写成已经线下见面。"
            "不能修改关系、好感度、库存或 NPC 日程。"
            + _SPEECH_HYGIENE_RULE
            + _GROUP_NATURAL_CONTRACT
            + "节奏示例（只示范长短参差与接话方式，内容不要照抄）："
            "玩家问“你们周末一般干什么”，依次是："
            "“睡到中午。”／“我周六去镇上，顺便看看种子店开没开。”／"
            "“啊对，我要买点肥料。”／“……我周末都在补觉，别问我。”"
            + '只输出 JSON 对象 {"turns":[{"speakerNpcId":"参与者 ID",'
            '"content":"对白","addressedTo":["目标 ID"]}],"memory":["…"]}，不要输出 Markdown 或解释。'
            "memory 可选：只挑 1～2 条值得长期记住的内容（玩家提到的事实、约定、承诺、重要变化），"
            "每条写成一句简短陈述，例如“玩家说下周要交报告”；"
            "闲聊、寒暄、当轮情绪和 NPC 自己的近况都不要写，没有就省略或给空数组。"
        )
    return topic_lead + (
        "这是公开线上群聊，channel=remote。"
        f"当前策略是 {strategy}，当前发言人只能说 {active_npc_id} 自己的话。"
        + other_rule
        + "不能让名单外 NPC 加入，不能把远程聊天写成已经线下见面。"
        "不能修改关系、好感度、库存或 NPC 日程。"
        + _SPEECH_HYGIENE_RULE
        + _GROUP_NATURAL_CONTRACT
    )


def build_group_messages(
    *,
    participants: list[GroupParticipant | Mapping[str, object]],
    active_npc_id: str,
    participant_prompts: Mapping[str, Sequence[Mapping[str, str]]] | None,
    strategy: str,
    turn_count: int | None = None,
    player_message: str = "",
    public_history: Sequence[Mapping[str, object]] = (),
    invitation_topic: str | None = None,
    invitation_guidance: str | None = None,
    relationship_world: RelationshipWorldContext | None = None,
    recent_facts: Sequence[str] = (),
) -> list[dict[str, str]]:
    """群聊消息：参与者角色卡与私聊完全同源，只额外追加一张群聊场景卡。

    角色卡由单 NPC 的 ``PromptBuilder`` 产出，这里不再自己拼角色描述；
    因此私聊侧的每次迭代都会自动作用到群聊，两边不会各自演进。
    """

    prompts = participant_prompts or {}
    roster_ids = [
        str(_participant_value(item, "npc_id", "npcId")) for item in participants
    ]
    roster_ids = [item for item in roster_ids if item]
    display_name_by_id = {
        str(_participant_value(item, "npc_id", "npcId")).casefold(): str(
            _participant_value(item, "display_name", "displayName") or ""
        )
        for item in participants
    }
    speakers = (
        roster_ids
        if strategy == "multi_turn"
        else [item for item in roster_ids if item.casefold() == active_npc_id.casefold()]
    )
    # multi_turn 下 speakers 是**整个名单**：那一次调用要同时演所有人
    # （见 `_group_scene_instruction` 的「本轮允许同时输出这些角色的对白」），
    # 因此这里必须把每份角色卡都拼进来，不能只留当前发言人的那一份。
    # 代价是同一个数组里出现 N 份卡——而卡内消息的 name 完全相同，
    # 归属必须由这里补上（见文件头部 `_STYLE_EXAMPLE_NAME` 那段注释）。
    merge_cards = len(speakers) > 1
    messages: list[dict[str, str]] = []
    for npc_id in speakers:
        block = prompts.get(npc_id.casefold()) or ()
        # 边界卡懒插入：这份卡一条可保留消息都没有时不插，免得出现
        # 一张指向空卡的分隔卡（角色卡取不到时会走到这里）。
        boundary = (
            _participant_card_boundary(
                npc_id, display_name_by_id.get(npc_id.casefold(), "")
            )
            if merge_cards
            else None
        )
        # 每人一份的私有上下文：紧跟边界卡，让归属链连续
        # （边界卡说「这段属于 X」→ 私有上下文说「这些是 X 自己的」→ X 的角色卡）。
        context_card = None
        participant_entry = _participant_entry(participants, npc_id)
        if participant_entry is not None:
            context_card = _participant_private_context(
                npc_id=npc_id,
                display_name=display_name_by_id.get(npc_id.casefold(), ""),
                relationship_world=_participant_value(
                    participant_entry, "relationship_world", "relationshipWorld"
                ),
                recent_facts=_participant_value(
                    participant_entry, "recent_facts", "recentFacts"
                ),
            )
        inserted_context = False
        for message in block:
            if not isinstance(message, Mapping):
                continue
            # 玩家输入由群聊统一追加，角色卡里各自的末条 user 消息要去掉。
            if str(message.get("role")) == "user":
                continue
            entry = {
                "role": str(message.get("role") or "system"),
                "content": str(message.get("content") or ""),
            }
            name = message.get("name")
            if isinstance(name, str) and name:
                # 语气样例必须标明归属：它和别的参与者的样例在同一个数组里，
                # 而 name 在此前是完全相同的（BUG-1 的成因）。
                if name == _STYLE_EXAMPLE_NAME:
                    name = _style_example_name(npc_id)
                entry["name"] = name
            if boundary is not None:
                messages.append(boundary)
                boundary = None
            if context_card is not None and not inserted_context:
                messages.append(context_card)
                inserted_context = True
            messages.append(entry)
        # 角色卡一条可保留消息都没有时（取不到卡），私有上下文仍然要落地：
        # 否则这位参与者在这一轮里完全不可见，比不传更糟。
        if context_card is not None and not inserted_context:
            messages.append(context_card)
    messages.append(
        {
            "role": "system",
            "name": "group_scene",
            "content": json.dumps(
                {
                    "instruction": _group_scene_instruction(
                        active_npc_id=active_npc_id,
                        roster_ids=roster_ids,
                        strategy=strategy,
                        turn_count=turn_count,
                        # 玩家消息为空（或纯空白）⇒ 这是开场：NPC 自己起话题。
                        is_opening=not player_message.strip(),
                        topic=invitation_topic,
                    ),
                    # 2026-09-20 修：这里此前**没有 invitation**，而实际用的正是多轮路径，
                    # 于是邀约的 topic/guidance 根本进不了 prompt —— 模型只知道“这是群聊”，
                    # 便按角色卡自由发挥（Abigail 就会一直聊回矿洞）。单轮路径
                    # build_group_prompt 一直带着它，两条路径在此不一致。
                    "invitation": (
                        {
                            "topic": invitation_topic,
                            "guidance": invitation_guidance,
                            # 2026-10-09 改：原文是「…不是 NPC 已确认的事实、NPC 记忆或
                            # 未来承诺。」这句对「聊动物」那类主题无害（聊动物不需要
                            # "已确认的事实"），但对**依赖关系事实**的主题是致命的：
                            # 打趣要的全部内容就是「你和玩家在一起这件事」，而 scope
                            # 先把这件事降级成"不是事实"⇒ 模型回避得完全合理。
                            # 实测：同一张打趣卡，四种 topic/guidance 写法 4/4 都退化成寒暄。
                            # 保护意图（别把邀约内容当成记忆或承诺写下去）保留，
                            # 只把「否定事实」改成「禁止据它推断」。
                            "scope": "这是本次邀约给出的讨论方向，用来给这轮聊天定题；"
                            "不要把它当成 NPC 已经知道的事实、既有记忆或做出过的承诺。",
                        }
                        if (invitation_topic or invitation_guidance)
                        else {}
                    ),
                    "participants": [
                        {
                            "npcId": _participant_value(item, "npc_id", "npcId"),
                            "displayName": _participant_value(
                                item, "display_name", "displayName"
                            ),
                        }
                        for item in participants
                    ],
                    # 2026-09-20 修（语义层审计）：这两个字段此前只有单轮回退路径带，
                    # 而生产走的是多轮路径——于是 SMAPI 一直在发的 relationshipWorld
                    # 与 recentFacts 根本进不了 prompt（与 invitation 那次同形）。
                    "relationshipWorld": (
                        relationship_world.model_dump(by_alias=True, exclude_none=True)
                        if relationship_world is not None
                        else {}
                    ),
                    "recentFacts": list(recent_facts),
                    "publicHistory": [dict(item) for item in public_history],
                },
                ensure_ascii=False,
            ),
        }
    )
    if player_message.strip():
        messages.append({"role": "user", "content": player_message})
    else:
        # 2026-10-09：开场（接受邀约后）这里原本**完全不发 user 消息**，于是整个
        # messages 里只有 system —— 模型看不到「该回答什么」，8 次原地重放实测
        # 7 次首答不是合法 JSON（64% 把 JSON 包进 ``` 围栏、27% 干脆只吐对白）。
        #
        # ⚠ 2026-09-20 的教训是「**不要塞空消息**」（当时无条件 append 一条
        # `content=""`，模型只能凭空猜），不是「不要塞任何消息」。这里补的是
        # **非空、且明确声明玩家尚未开口**的旁白：既给模型一个必须回应的
        # user 轮次，又不假定玩家说过任何话，与 `_group_scene_instruction` 里
        # `is_opening` 的措辞（「玩家还没有说话，请由名单里最自然的那个人先起个头」）
        # 完全一致，不构成矛盾。
        messages.append({"role": "user", "content": _GROUP_OPENING_NUDGE})
    return messages


def build_group_prompt(
    *,
    active_npc_id: str,
    participants: list[GroupParticipant | Mapping[str, object]],
    shared_game_state: NpcGameState | None,
    relationship_world: RelationshipWorldContext | None,
    recent_facts: list[str],
    public_history: list[dict[str, object]],
    player_message: str,
    strategy: str,
    turn_count: int | None = None,
    invitation_topic: str | None = None,
    invitation_guidance: str | None = None,
    participant_cards: Mapping[str, Mapping[str, object]] | None = None,
) -> list[dict[str, str]]:
    cards = participant_cards or {}
    roster: list[dict[str, object]] = []
    for item in participants:
        npc_id = _participant_value(item, "npc_id", "npcId")
        if not str(npc_id or "").strip():
            # 与 build_group_messages 同一条规矩：空 ID 不算名单成员。
            # 2026-09-20（语义层审计 #29）：此前这里把空 ID 也算进回合额度，
            # 于是回退 prompt 与场景卡对同一场群聊给出不同的「最多输出 N 个回合」。
            continue
        entry: dict[str, object] = {
            "npcId": npc_id,
            "displayName": _participant_value(item, "display_name", "displayName"),
        }
        voice = cards.get(str(npc_id).casefold()) if npc_id else None
        if isinstance(voice, Mapping) and voice:
            entry["voice"] = dict(voice)
        roster.append(entry)
    scene = (
        shared_game_state.model_dump(
            by_alias=True,
            exclude_none=True,
            # `completedEventIds` 是事件门控的输入，不是 prompt 内容：它随存档
            # 单调增长（正常存档数百条），模型无法据此生成对白，整卡渲染只占预算。
            # 与 `prompts._PROMPT_HIDDEN_STATE_FIELDS` 是同一条规矩；主路径的
            # 参与者角色卡走 `PromptBuilder`，已在那边挡掉。
            exclude={"completed_event_ids"},
        )
        if shared_game_state is not None
        else {}
    )
    relationship = (
        relationship_world.model_dump(by_alias=True, exclude_none=True)
        if relationship_world is not None
        else {}
    )
    invitation = {}
    if invitation_topic or invitation_guidance:
        invitation = {
            "topic": invitation_topic,
            "guidance": invitation_guidance,
            "scope": (
                "这是玩家选择的话题方向，不是 NPC 已确认的事实、NPC 记忆或未来承诺。"
            ),
        }
    other_npcs = [
        str(item["npcId"])
        for item in roster
        if item["npcId"] and str(item["npcId"]).casefold() != active_npc_id.casefold()
    ]
    other_speaker_rule = (
        "不能替 " + "、".join(other_npcs) + " 发言。"
        if other_npcs
        else "不能替其他 NPC 发言。"
    )
    if strategy == "multi_turn":
        instruction = (
            "这是公开线上群聊，channel=remote。当前策略是自然接话流；"
            "名单内每个 NPC 都可以发言，但不要求每个人都发言，也不要求一人恰好一句。"
            "根据玩家输入、公开历史和各自角色气质决定谁先接话；允许另一个 NPC 插话，"
            "也允许同一 NPC 连续补一句或把话题递给指定参与者。"
            "如果某条对白点名了名单里的另一个人（addressedTo），那个人应当接一轮；"
            "整段至少出现一次来回：有人说完，另一个人接住并推进一次。"
            "其余人可以不发言——沉默要来自角色自己没话说，而不是因为没人接。"
            f"最多输出 {turn_budget(turn_count, len(roster))} 个公开回合，"
            "每个回合只说对应 speakerNpcId 自己的话，不要替别人代答。"
            + other_speaker_rule
            + "不能让名单外 NPC 加入，不能把远程聊天写成已经线下见面。"
            "不能修改关系、好感度、库存或 NPC 日程。" + _SPEECH_HYGIENE_RULE
            + _GROUP_NATURAL_CONTRACT
        )
        instruction += (
            '只输出 JSON 对象 {"turns":[{"speakerNpcId":"参与者 ID",'
            '"content":"对白","addressedTo":["目标 ID"]}]}，不要输出 Markdown 或解释。'
        )
    else:
        instruction = (
            "这是公开线上群聊，channel=remote。"
            f"当前策略是 {strategy}，当前发言人只能说 {active_npc_id} 自己的话。"
            + other_speaker_rule
            + "不能让名单外 NPC 加入，不能把远程聊天写成已经线下见面。"
            "不能修改关系、好感度、库存或 NPC 日程。" + _SPEECH_HYGIENE_RULE
            + _GROUP_NATURAL_CONTRACT
        )
    if not player_message.strip():
        instruction += (
            "玩家还没有说话：请根据公开历史、各自角色气质与邀约里的由头，"
            "让最自然的那个人先起个头；不要假定玩家说过任何话，也不要替玩家发言。"
        )

    # 玩家消息为空（或纯空白）⇒ 这是开场：NPC 自己起话题，且不得假定玩家说过话。
    # 此前这里是**无条件**追加 user 消息，于是开场时会塞进一条空消息，
    # 而指令却在要求“接玩家”—— 模型只能凭空猜（2026-09-20 修复）。
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "name": "group_conversation",
            "content": json.dumps(
                {
                    "instruction": instruction,
                    "participants": roster,
                    "gameState": scene,
                    "relationshipWorld": relationship,
                    "invitation": invitation,
                    "recentFacts": recent_facts,
                    "publicHistory": public_history,
                },
                ensure_ascii=False,
            ),
        },
    ]
    if player_message.strip():
        messages.append({"role": "user", "content": player_message})
    return messages


def _canonical_participant_ids(participant_ids: Iterable[str]) -> dict[str, str]:
    """**本次请求**参与者名单的唯一索引：casefold 键 → 规范写法。

    2026-09-20（语义层审计 #31）：`addressedTo` 的「必须在名单内」这条约束
    此前在两处各判一遍（都在本模块：解析出的发言人、归一化后的目标）。
    现在本函数是这份名单的权威来源，两处都从它派生。

    注意 `providers.py` 里还有一处**看着像、其实不是**：它判的是 Fake 内置
    白名单 `_GROUP_LABELS`（「是不是演示自己认识的角色」，防止回显请求方伪造的
    身份文本），与「是否在本次请求的名单内」不是同一个概念——**不要合并**。
    """

    index: dict[str, str] = {}
    for item in participant_ids:
        if not isinstance(item, str):
            continue
        canonical = item.strip()
        if canonical:
            index.setdefault(canonical.casefold(), canonical)
    return index


def _normalize_addressed_to(
    value: object,
    participant_ids: Iterable[str],
) -> list[str]:
    """只保留名单内目标：模型偶尔会写 player/you 或大小写不符的代称。

    回应玩家时没有名单内目标，归一化成空数组，回放页就不会显示多余的箭头。
    """

    if not isinstance(value, (list, tuple)):
        return []
    allowed = _canonical_participant_ids(participant_ids)
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        canonical = allowed.get(item.strip().casefold())
        if canonical and canonical not in normalized:
            normalized.append(canonical)
    return normalized


# 提示词里告诉模型「memory 可选：只挑 1～2 条」（见 _group_scene_instruction），
# 而这里是**容忍上限**：模型偶尔多给一条（3 条）也接受并落库，超过才截断。
# 两者**不是同一个约束**——1～2 是期望值，3 是防御边界，所以刻意不相等。
# 另外注意：三层里**只有这里**做数量截断；SMAPI 的 GroupMemoryRules.Plan
# 只做去空/trim/去重，不限制条数（2026-09-20 跨层扫描时确认）。
_MAX_MEMORY_HIGHLIGHTS = 3

# 群聊「开场」时玩家尚未发言。DialogueTestRequest 要求 message 非空，而群聊实际
# 用显式构造的 messages 送模型，所以这里只需要一个不会进入 prompt 的占位。
_OPENING_MESSAGE_PLACEHOLDER = "(群聊开场：玩家尚未发言)"
_MEMORY_HIGHLIGHT_LENGTH = 160

# 公开回合的硬上限，与 models.GroupDialogueRequest.turn_count 的 le=4 保持一致。
_MAX_GROUP_TURNS = 4


def turn_budget(turn_count: int | None, participant_count: int) -> int:
    """回合上限：显式指定就照用；没指定就按在场人数给。

    调用方（例如游戏客户端）不传 turnCount 时，旧默认值 2 会让 3 人场必然有人
    整场不开口——实测 3 人案例在 turnCount=2 下两个案例各漏一人。按人数给额度
    才能保证名单里每个人都有机会说话，同时仍受 _MAX_GROUP_TURNS 限制。
    """

    if isinstance(turn_count, int) and turn_count >= 1:
        return min(turn_count, _MAX_GROUP_TURNS)
    return max(1, min(participant_count, _MAX_GROUP_TURNS))


def _normalize_memory_highlights(value: object) -> list[str]:
    """挑选值得长期记住的候选：只要简短短语，闲聊与超长内容一律丢弃。"""

    if not isinstance(value, (list, tuple)):
        return []
    highlights: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or len(text) > _MEMORY_HIGHLIGHT_LENGTH:
            continue
        if text not in highlights:
            highlights.append(text)
        if len(highlights) >= _MAX_MEMORY_HIGHLIGHTS:
            break
    return highlights


def guard_group_turns(
    turns: list[GroupTurn],
    guard: ResponseGuard,
    *,
    prompt: list[dict[str, str]] | None = None,
) -> tuple[list[GroupTurn], list[str]]:
    """逐条过通用质量门，返回保留下来的对白与警告。

    2026-09-20（语义层审计 #13）：群聊此前没有任何内容拦截。这里刻意**丢掉**
    不合格的那一条，而不是像私聊那样整条回落到安全文案——群聊有多位发言人，
    少一个人开口比让整场变成一句通用台词自然，也不会把内容问题伪装成
    provider 降级（``fallback=True`` 的语义是上游失败，SMAPI 按整场失败处理）。

    传入 ``prompt`` 时同时检查「开场白把缺失前情推给玩家」（#14）。
    """

    kept: list[GroupTurn] = []
    warnings: list[str] = []
    for turn in turns:
        decision = guard.check(turn.content)
        if not decision.accepted:
            warnings.append(f"response_guard: {decision.reason}")
            continue
        if prompt is not None and missing_opening_grounding(prompt, decision.text):
            warnings.append("response_guard: opaque_opening")
            continue
        if decision.text != turn.content:
            turn = turn.model_copy(update={"content": decision.text})
        kept.append(turn)
    return kept, warnings


def guard_memory_highlights(
    highlights: list[str],
    guard: ResponseGuard,
) -> tuple[list[str], list[str]]:
    """长期记忆候选同样过门：它会写进存档，污染面比单条对白更长。"""

    kept: list[str] = []
    warnings: list[str] = []
    for item in highlights:
        decision = guard.check(item)
        if not decision.accepted:
            warnings.append(f"response_guard: {decision.reason}")
            continue
        kept.append(decision.text)
    return kept, warnings


_FENCE_LANGUAGE_TAGS = frozenset({"", "json", "json5", "js", "javascript"})


def _strip_code_fence(text: str) -> str:
    """剥掉包裹 JSON 的 markdown 代码围栏。

    2026-10-09 实测：**开场**（messages 里只有 system、没有 user）时，云侧模型
    有 64% 的概率把本该裸输出的 JSON 包进 ` ```json … ``` `。围栏对人眼毫无
    歧义，对 `json.loads` 却是致命的 —— 而 `_FORMAT_REPAIR_RULE` 早已明写
    「不要 Markdown 代码块」，重试仍有 57% 救不回来，说明**光靠提示词约束不住**。

    这里做**无损**剥离：剥完能解析出合法对象，就等价于模型当初没加围栏。
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped[3:]
    newline = body.find("\n")
    if newline < 0:
        # 没有换行 ⇒ 不是完整围栏（可能是 `` ` `` 开头的普通文本），原样返回。
        return stripped
    if body[:newline].strip().casefold() not in _FENCE_LANGUAGE_TAGS:
        return stripped
    body = body[newline + 1 :].rstrip()
    if body.endswith("```"):
        body = body[:-3]
    return body.strip()


def _extract_json_object(text: str) -> str | None:
    """从 JSON 前后夹带的旁白或解释里，抠出第一个完整的 `{…}`。

    用括号配平 + 字符串状态机而不是正则，避免正文里的 `}` 提前截断。
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _load_multi_turn_json(reply: object) -> object:
    """解析模型回复；裸 JSON 走原路，**只有失败时**才尝试剥围栏 / 抠对象。

    ⚠ 兜底只在 `json.loads(reply)` 抛错后触发 —— 原文本来就合法时行为完全不变。
    不猜、不补、不修内容，只做「把 JSON 从包装里取出来」这一件事。
    ⚠ 纯对白（压根没吐 JSON）仍然会失败，那一类要靠 prompt 侧解决。
    """
    try:
        return json.loads(reply)
    except (TypeError, json.JSONDecodeError):
        pass

    if not isinstance(reply, str):
        raise GroupResponseError("multi_turn 回复不是有效 JSON")

    candidate = _extract_json_object(_strip_code_fence(reply))
    if candidate is None:
        raise GroupResponseError("multi_turn 回复不是有效 JSON")
    try:
        return json.loads(candidate)
    except (TypeError, json.JSONDecodeError) as exc:
        raise GroupResponseError("multi_turn 回复不是有效 JSON") from exc


def parse_multi_turn_payload(
    reply: str,
    *,
    participant_ids: Iterable[str],
    expected_turn_count: int,
) -> tuple[list[GroupTurn], list[str]]:
    """解析多轮回复，并取出可选 memory 字段（值得长期记住的事实或约定）。"""
    parsed = _load_multi_turn_json(reply)

    if not isinstance(parsed, Mapping) or not isinstance(parsed.get("turns"), list):
        raise GroupResponseError("multi_turn 回复缺少 turns")
    if not parsed["turns"]:
        raise GroupResponseError("multi_turn 没有可用回合")

    turn_payloads = parsed["turns"]
    if len(turn_payloads) > expected_turn_count:
        # 2026-10-09：模型经常**多给 1～2 轮**（实测 4 轮 vs 上限 2）。
        # 但多出来的内容是**自然的群聊推进**，不是坏输出 —— 00:18:03 那次的结构是
        # 「起头 → 话题落地 → 追问 → 收尾寒暄」，整条丢掉等于把好台词全扔了，
        # 而丢的结果正是玩家看到的「无可用回复」。
        #
        # 保守截断：**保留最前面的 N 轮**。开场最要紧的是「有人起头 + 话题落地」，
        # 头部两轮承担这个职能；尾部多是收尾寒暄，丢掉损失最小。
        # ⚠ 与「轮数不足」不同，这条**不再整条拒绝**，但也不算通过 ——
        # 上层据此仍能看出模型超出了上限（见 parse 的调用方）。
        turn_payloads = turn_payloads[:expected_turn_count]

    normalized_ids = set(_canonical_participant_ids(participant_ids))
    turns: list[GroupTurn] = []
    for item in turn_payloads:
        if not isinstance(item, Mapping):
            raise GroupResponseError("multi_turn 中存在无效回合")
        speaker = item.get("speakerNpcId")
        content = item.get("content")
        if not isinstance(speaker, str) or speaker.casefold() not in normalized_ids:
            raise GroupResponseError("未知发言人")
        if not isinstance(content, str) or not content.strip():
            raise GroupResponseError("multi_turn 存在空对白")
        turns.append(
            GroupTurn.model_validate(
                {
                    "speakerNpcId": speaker,
                    "content": content,
                    "addressedTo": _normalize_addressed_to(
                        item.get("addressedTo", []), participant_ids
                    ),
                }
            )
        )
    return turns, _normalize_memory_highlights(parsed.get("memory"))


def parse_multi_turn_reply(
    reply: str,
    *,
    participant_ids: set[str],
    expected_turn_count: int,
) -> list[GroupTurn]:
    """兼容入口：只要回合，长期记忆候选由 parse_multi_turn_payload 提供。"""

    turns, _ = parse_multi_turn_payload(
        reply,
        participant_ids=participant_ids,
        expected_turn_count=expected_turn_count,
    )
    return turns


class GroupConversationService:
    """编排线上多人对话策略；不负责线下 NPC 在场判断。"""

    def __init__(
        self,
        provider_router: ProviderRouter,
        voice_card_provider: (
            Callable[[list[GroupParticipant]], Mapping[str, Mapping[str, object]]] | None
        ) = None,
        prompt_provider: (
            Callable[
                [list[GroupParticipant], GroupDialogueRequest],
                Mapping[str, Sequence[Mapping[str, str]]],
            ]
            | None
        ) = None,
        response_guard: ResponseGuard | None = None,
    ) -> None:
        self.provider_router = provider_router
        self.voice_card_provider = voice_card_provider
        self.prompt_provider = prompt_provider
        # 2026-09-20（语义层审计 #13）：群聊此前**完全没有**回复质量门——私聊有
        # `response_guard.check` 加安全兜底替换，群聊只有一句提示词，于是舞台动作
        # （`（笑）`）、Markdown、提示词泄露都会原样进对白。这里与私聊共用同一个
        # `ResponseGuard`（它无状态，只带 max_chars）。
        self.response_guard = response_guard if response_guard is not None else ResponseGuard()

    def _participant_prompts(
        self,
        participants: list[GroupParticipant],
        request: GroupDialogueRequest,
    ) -> dict[str, Sequence[Mapping[str, str]]]:
        """取每个参与者与私聊同源的角色卡；取不到时回退到旧组装方式。"""

        if self.prompt_provider is None:
            return {}
        try:
            raw_prompts = self.prompt_provider(participants, request)
        except Exception:  # noqa: BLE001 - 取卡失败不应让群聊整体不可用
            return {}
        if not isinstance(raw_prompts, Mapping):
            return {}
        return {
            str(key).casefold(): value
            for key, value in raw_prompts.items()
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        }

    def _participant_cards(
        self, participants: list[GroupParticipant]
    ) -> dict[str, Mapping[str, object]]:
        if self.voice_card_provider is None:
            return {}
        try:
            raw_cards = self.voice_card_provider(participants)
        except Exception:  # noqa: BLE001 - 语气卡失败不应让整场群聊不可用
            return {}
        if not isinstance(raw_cards, Mapping):
            return {}
        return {
            str(key).casefold(): value
            for key, value in raw_cards.items()
            if isinstance(value, Mapping)
        }

    def generate(self, request: GroupDialogueRequest) -> GroupDialogueResponse:
        started_at = perf_counter()
        if request.turn_count is None:
            # 未显式指定回合上限时按在场人数给：3 人场只给 2 个回合必然漏人。
            request = request.model_copy(
                update={"turn_count": turn_budget(None, len(request.participants))}
            )
        participant_by_id = {
            item.npc_id.casefold(): item for item in request.participants
        }
        # 2026-09-20（语义层审计 #10）：参与者上下文此前在这里**无条件构建两次**
        # ——一次声线卡（`_participant_cards`）、一次角色卡（`_participant_prompts`），
        # 而两份产物都要走 `ContextBuilder.build`。主路径（角色卡可用）只读角色卡，
        # 声线卡那份整份被丢掉，纯浪费。现在声线卡**按需**构建：只有回退到
        # `build_group_prompt` 时才现取（见 `_call_participant`）。
        participant_prompts = self._participant_prompts(request.participants, request)
        if request.strategy == "fanout":
            results = [
                self._call_participant(
                    request,
                    participant,
                    participant.npc_id,
                    participant_prompts,
                )
                for participant in request.participants
            ]
        else:
            active_id = request.active_speaker_npc_id or request.participants[0].npc_id
            active = participant_by_id[active_id.casefold()]
            results = [
                self._call_participant(
                    request, active, active.npc_id, participant_prompts
                )
            ]

        turns: list[GroupTurn] = []
        provider_errors: list[str] = []
        warnings: list[str] = []
        memory_highlights: list[str] = []
        provider_results = []
        for participant, result, provider_request, messages in results:
            provider_results.append(result)
            warnings.extend(result.warnings)
            if result.fallback:
                provider_errors.extend(result.warnings or ["provider fallback"])
                continue
            if request.strategy == "multi_turn":
                parsed, memory, retried, failure = self._multi_turn_turns(
                    request=request,
                    result=result,
                    # 用规范大小写的 ID，避免归一化后把 addressedTo 写成小写。
                    participant_ids={item.npc_id for item in request.participants},
                    provider_request=provider_request,
                    messages=messages,
                )
                if retried is not None:
                    provider_results.append(retried)
                    warnings.extend(retried.warnings)
                if failure:
                    provider_errors.append(failure)
                guarded_turns, turn_warnings = guard_group_turns(
                    parsed, self.response_guard, prompt=messages
                )
                guarded_memory, memory_warnings = guard_memory_highlights(
                    memory, self.response_guard
                )
                warnings.extend([*turn_warnings, *memory_warnings])
                turns.extend(guarded_turns)
                for item in guarded_memory:
                    if item not in memory_highlights:
                        memory_highlights.append(item)
                continue
            guarded_turns, turn_warnings = guard_group_turns(
                [
                    GroupTurn(
                        speakerNpcId=participant.npc_id,
                        content=result.reply,
                    )
                ],
                self.response_guard,
                prompt=messages,
            )
            warnings.extend(turn_warnings)
            turns.extend(guarded_turns)

        if request.strategy == "multi_turn" and not provider_errors and not turns:
            provider_errors.append("multi_turn 没有可用对白")

        provider_names = {result.provider for result in provider_results}
        provider = next(iter(provider_names), "unknown")
        if len(provider_names) > 1:
            provider = "mixed"
        return GroupDialogueResponse(
            strategy=request.strategy,
            channel=request.channel,
            provider=provider,
            fallback=any(result.fallback for result in provider_results),
            turns=turns,
            providerCalls=len(provider_results),
            providerErrors=limit_warnings(provider_errors),
            fallbackCount=sum(result.fallback for result in provider_results),
            latencyMs=int((perf_counter() - started_at) * 1000),
            warnings=limit_warnings(warnings),
            usage=_merge_usage([result.usage for result in provider_results]),
            memoryHighlights=memory_highlights[:_MAX_MEMORY_HIGHLIGHTS],
        )

    def _call_participant(
        self,
        request: GroupDialogueRequest,
        participant: GroupParticipant,
        active_npc_id: str,
        participant_prompts: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
    ) -> tuple[GroupParticipant, ProviderResult]:
        provider_request = DialogueTestRequest.model_validate(
            {
                "npcId": participant.npc_id,
                # 开场（玩家还没说话）时 request.message 为空，而 DialogueTestRequest
                # 要求文本非空。这个字段在群聊里只是载体——真正送进模型的是下面显式
                # 构造的 messages，所以用内部占位即可，不会进入 prompt。
                "message": request.message or _OPENING_MESSAGE_PLACEHOLDER,
                "provider": request.provider,
                "displayName": participant.display_name,
                "sourceMods": participant.source_mods,
                "gameState": participant.game_state or request.game_state,
                "recentFacts": request.recent_facts,
                "history": [item.model_dump(by_alias=True) for item in request.history],
                "relationshipWorld": request.relationship_world,
                "channel": request.channel,
            "groupStrategy": request.strategy,
            "groupParticipantIds": [item.npc_id for item in request.participants],
            "groupTurnCount": request.turn_count,
        }
        )
        if participant_prompts:
            messages = build_group_messages(
                participants=request.participants,
                active_npc_id=active_npc_id,
                participant_prompts=participant_prompts,
                strategy=request.strategy,
                turn_count=request.turn_count,
                player_message=request.message,
                public_history=[
                    item.model_dump(by_alias=True) for item in request.history
                ],
                invitation_topic=request.invitation_topic,
                invitation_guidance=request.invitation_guidance,
                relationship_world=request.relationship_world,
                recent_facts=request.recent_facts,
            )
        else:
            # 2026-09-20（语义层审计 #10）：声线卡只在这条回退路径上被读，
            # 所以只在这里现取——主路径不再为一份没人读的产物多跑一遍
            # `ContextBuilder.build`（`build_group_voice_cards` 逐人构建）。
            messages = build_group_prompt(
                active_npc_id=active_npc_id,
                participants=request.participants,
                shared_game_state=request.game_state,
                relationship_world=request.relationship_world,
                recent_facts=request.recent_facts,
                public_history=[item.model_dump(by_alias=True) for item in request.history],
                player_message=request.message,
                strategy=request.strategy,
                turn_count=request.turn_count,
                invitation_topic=request.invitation_topic,
                invitation_guidance=request.invitation_guidance,
                participant_cards=self._participant_cards(request.participants),
            )
        result = self.provider_router.generate(provider_request, messages=messages)
        return participant, result, provider_request, messages

    def _multi_turn_turns(
        self,
        *,
        request: GroupDialogueRequest,
        result: ProviderResult,
        participant_ids: set[str],
        provider_request: DialogueTestRequest,
        messages: list[dict[str, str]],
    ) -> tuple[list[GroupTurn], ProviderResult | None, str | None]:
        """解析多轮 JSON；首次失败时带着格式修复提示重试一次。

        整条多轮结果因为格式问题被丢掉太亏，但也不能无限重试。
        """

        def parse(candidate: str) -> tuple[list[GroupTurn], list[str]]:
            return parse_multi_turn_payload(
                candidate,
                participant_ids=participant_ids,
                expected_turn_count=request.turn_count,
            )

        first_error = ""
        try:
            turns, memory = parse(result.reply)
            return turns, memory, None, None
        except GroupResponseError as exc:
            first_error = str(exc)

        retried = self.provider_router.generate(
            provider_request,
            messages=[
                *messages,
                {
                    "role": "system",
                    "name": "format_repair",
                    "content": _FORMAT_REPAIR_RULE,
                },
            ],
        )
        try:
            turns, memory = parse(retried.reply)
            return turns, memory, retried, None
        except GroupResponseError as exc:
            return [], [], retried, f"{first_error}；重试后仍失败：{exc}"


# 响应里 warnings / providerErrors 的条数上限（与 models.py 的 max_length 对齐）。
# 2026-09-20 修（语义层审计）：这条截断此前只有私聊路径做（app.py 的 _limit_warnings），
# 群聊直接原样返回，累积超过 20 条时 pydantic 校验失败 → 端点 500。
_WARNING_LIMIT = 20


def limit_warnings(warnings: Iterable[str]) -> list[str]:
    """保留 guard 类警告与末尾若干条，总数不超过 _WARNING_LIMIT。"""
    values = list(warnings)
    guard_indices = [
        index
        for index, warning in enumerate(values)
        if warning.startswith(("response_guard:", "fallback_guard:"))
    ]
    selected = set(guard_indices[-_WARNING_LIMIT:])
    for index in range(len(values) - 1, -1, -1):
        if len(selected) >= _WARNING_LIMIT:
            break
        selected.add(index)
    return [values[index] for index in sorted(selected)]


def _merge_usage(usages: list[ProviderUsage | None]) -> ProviderUsage | None:
    present = [item for item in usages if item is not None]
    if not present:
        return None

    def total(field: str) -> int | None:
        # 保守口径：只要有一个 chunk 没报该字段，就不给这个字段一个偏小的数。
        #
        # 2026-09-20（语义层审计）：私聊的 `_merge_provider_usages` 此前是逐字段累加，
        # 两边口径不同。**统一到这里的保守口径**——token 用量用于成本统计，
        # 「缺失」比「偏小」安全，调用方能从 None 看出数据不全。
        values = [getattr(item, field) for item in present]
        return sum(values) if all(value is not None for value in values) else None

    return ProviderUsage(
        inputTokens=total("input_tokens"),
        outputTokens=total("output_tokens"),
        totalTokens=total("total_tokens"),
    )
