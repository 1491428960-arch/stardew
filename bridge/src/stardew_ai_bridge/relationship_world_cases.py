"""关系世界观的八角色三轮质量评测案例。

案例只用于离线质量评测：objectiveRelationships 是领域输入，实际发给
Provider 的请求会先投影成当前 NPC 能看到的最小视角，不会写入评测工件。
"""

from __future__ import annotations

from .character_quality_eval import CharacterQualityCase, CharacterQualityTurn


RELATIONSHIP_WORLD_SUITE: dict[str, object] = {
    "suiteId": "relationship-world",
    "title": "复数关系世界观：八角色三轮验收",
    "description": "检查局部知情、婚礼公开、一对一调解和可恢复嫉妒，同时保留五个 NPC 的角色差异。",
    "caseCount": 32,
    "roles": [
        "Wizard",
        "Sophia",
        "Shane",
        "Sebastian",
        "Alex",
        "Elliott",
        "Harvey",
        "Sam",
    ],
    "turnsPerCase": 3,
    "safety": "双方成年且自愿；不生成露骨性行为过程，不把 NPC 的拒绝或暂缓视为错误。",
}


def _history(*messages: tuple[str, str]) -> tuple[dict[str, str], ...]:
    return tuple({"role": role, "content": content} for role, content in messages)


def _fact(
    npc_id: str,
    relation_type: str = "dating",
    *,
    public_event_id: str | None = None,
    public_on: str | None = None,
) -> dict[str, str]:
    fact: dict[str, str] = {"npcId": npc_id, "relationType": relation_type}
    if public_event_id:
        fact["publicEventId"] = public_event_id
    if public_on:
        fact["publicOn"] = public_on
    return fact


def _view(
    owner_npc_id: str,
    subject_npc_id: str,
    visibility: str,
    *,
    relation_type: str = "dating",
    source: str = "none",
    evidence: str | None = None,
) -> dict[str, str]:
    view: dict[str, str] = {
        "ownerNpcId": owner_npc_id,
        "subjectNpcId": subject_npc_id,
        "relationType": relation_type,
        "visibility": visibility,
        "source": source,
    }
    if evidence:
        view["evidence"] = evidence
    return view


def _world(
    *,
    facts: tuple[dict[str, str], ...],
    views: tuple[dict[str, str], ...],
    viewer_npc_id: str,
    acceptance: str | None = None,
    mediation: dict[str, str] | None = None,
    jealousy: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "objectiveRelationships": [dict(item) for item in facts],
        "views": [dict(item) for item in views],
        "acceptanceByNpc": (
            {viewer_npc_id: acceptance} if acceptance is not None else {}
        ),
        "mediationByNpc": (
            {viewer_npc_id: dict(mediation)} if mediation is not None else {}
        ),
        "jealousyByNpc": (
            {viewer_npc_id: dict(jealousy)} if jealousy is not None else {}
        ),
    }


def _turn(
    turn_id: str,
    message: str,
    expected_terms: tuple[str, ...],
    focus: str,
    evaluation_focus: str,
    *,
    forbidden_terms: tuple[str, ...] = (),
    relationship_actor: str = "",
    relationship_target_npc_id: str = "",
    intent: str | None = None,
    initiative_expectation: str = "none",
    initiative_kind: str = "none",
) -> CharacterQualityTurn:
    return CharacterQualityTurn(
        turn_id=turn_id,
        message=message,
        expected_terms=expected_terms,
        forbidden_terms=forbidden_terms,
        evaluation_focus=evaluation_focus,
        relationship_focus=focus,
        relationship_actor=relationship_actor,
        relationship_target_npc_id=relationship_target_npc_id,
        intent=intent,
        initiative_expectation=initiative_expectation,
        initiative_kind=initiative_kind,
    )


def _case(
    *,
    case_id: str,
    profile_key: str,
    npc_id: str,
    display_name: str,
    source_mods: tuple[str, ...],
    relationship_stage: str,
    channel: str,
    turns: tuple[CharacterQualityTurn, ...],
    relationship_world: dict[str, object],
    relationship_context: str,
    story_progress: str,
    topic_seed: str,
    topic_keywords: tuple[str, ...],
    history: tuple[dict[str, str], ...] = (),
    gender_presentation: str = "",
    intent: str = "chat",
    # 该案例声明的「角色已经历过的剧情事件」。刻意**不给默认值**：空元组在
    # 事件锁里表示「这些事件都没发生」，会被收窄到 acquaintance；
    # 「忘记声明」与「声明为空」必须是两件事，所以每条案例都要自己写清楚。
    completed_event_ids: tuple[str, ...],
) -> CharacterQualityCase:
    if len(turns) != 3:
        raise ValueError(f"关系世界观案例必须有三轮：{case_id}")
    return CharacterQualityCase(
        case_id=case_id,
        profile_key=profile_key,
        npc_id=npc_id,
        display_name=display_name,
        source_mods=source_mods,
        relationship_stage=relationship_stage,
        channel=channel,
        message=turns[0].message,
        intent=intent,
        topic_seed=topic_seed,
        topic_keywords=topic_keywords,
        friendship_hearts={
            "friend": 6,
            "close": 8,
            "dating": 8,
            "married": 10,
        }[relationship_stage],
        relationship_context=relationship_context,
        history=history,
        expected_terms=turns[0].expected_terms,
        forbidden_terms=turns[0].forbidden_terms,
        story_progress=story_progress,
        gender_presentation=gender_presentation,
        relationship_world=relationship_world,
        completed_event_ids=completed_event_ids,
        turns=turns,
    )


RELATIONSHIP_WORLD_CASES: tuple[CharacterQualityCase, ...] = (
    # 五例局部知情：普通恋爱不自动同步，suspected 不能被说成事实。
    _case(
        case_id="relationship-wizard-view-gap",
        completed_event_ids=("1000075", "1724096", "1724097"),
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="close",
        channel="remote",
        turns=(
            _turn("turn-1", "你是不是听说 Sophia 最近在和谁约会？", ("听说", "不知道"), "unknown_view", "未知视角只能承认不知道，不能从客观表偷取答案。"),
            _turn("turn-2", "镇上有人说 Alex 可能在谈恋爱，你怎么看？", ("可能", "不确定"), "suspected_view", "把传闻保留为不确定信息，不能升级成事实。"),
            _turn("turn-3", "我直接告诉你：我也在和 Sophia 认真交往。", ("直接", "交往"), "direct_disclosure", "被主角直接说明时诚实接住，不把坦白改成隐瞒或代替他人发言。"),
        ),
        relationship_world=_world(
            viewer_npc_id="Wizard",
            facts=(_fact("Sophia"), _fact("Alex")),
            views=(
                _view("Wizard", "Sophia", "unknown"),
                _view("Wizard", "Alex", "suspected", source="rumor", evidence="镇上闲谈"),
            ),
        ),
        relationship_context="战争后的政策允许复数关系，但星露谷仍偏好一对一；Wizard 只知道自己的局部视角。",
        story_progress="远程消息中提到两段普通恋爱传闻；只有主角直接说明的关系才能升级为当前 NPC 的已知事实。",
        topic_seed="关系传闻与直接说明",
        topic_keywords=("听说", "可能", "交往"),
        history=_history(("user", "镇上的传闻总是传得很快。"), ("assistant", "传闻和事实最好分开。")),
    ),
    _case(
        case_id="relationship-sophia-view-gap",
        completed_event_ids=("8185291", "8185292", "8185293"),
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="friend",
        channel="face_to_face",
        turns=(
            _turn("turn-1", "你知道 Sebastian 最近是不是在和谁约会吗？", ("不知道", "不清楚"), "unknown_view", "Sophia 可以有点在意，但不能假装知道 Sebastian 的私生活。"),
            _turn("turn-2", "有人说 Shane 可能有了恋人，我不想把传闻当真的。", ("传闻", "可能"), "suspected_view", "保留犹豫和生活细节，不把传闻当成确定关系。"),
            _turn("turn-3", "如果你想知道我的情况，我会直接告诉你。", ("直接告诉", "诚实"), "direct_disclosure", "主角直接询问时给出诚实、温和且不替别人下结论的空间。"),
        ),
        relationship_world=_world(
            viewer_npc_id="Sophia",
            facts=(_fact("Sebastian"), _fact("Shane")),
            views=(
                _view("Sophia", "Sebastian", "unknown"),
                _view("Sophia", "Shane", "suspected", source="rumor", evidence="酒窖外的闲谈"),
            ),
        ),
        relationship_context="Sophia 偏好传统关系，但不会把政策争议变成对他人的道德审判；她只掌握眼前交集。",
        story_progress="当面在酒窖整理标签，话题从朋友的近况转到没有证实的恋爱传闻。",
        topic_seed="酒窖里的传闻",
        topic_keywords=("酒窖", "传闻", "告诉"),
        history=_history(("user", "刚才有人在门口小声聊起 Shane。"), ("assistant", "我只听到一半，不想乱猜。")),
    ),
    _case(
        case_id="relationship-shane-view-gap",
        completed_event_ids=("611944", "3910674", "3910975", "3900074"),
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="close",
        channel="remote",
        turns=(
            _turn("turn-1", "你是不是知道 Alex 在和谁约会？", ("不知道", "别问"), "unknown_view", "Shane 可以嘴硬收口，但不能凭空掌握 Alex 的关系。"),
            _turn("turn-2", "听说 Wizard 可能在谈恋爱，我也只是听说。", ("听说", "可能"), "suspected_view", "把听闻和确认分开，保持 Shane 的低调和不确定。"),
            _turn("turn-3", "你直接问我吧，我知道的会说，不知道的不会装懂。", ("直接问", "不会装懂"), "direct_disclosure", "面对直接问题如实回答，允许保留不知道的部分。"),
        ),
        relationship_world=_world(
            viewer_npc_id="Shane",
            facts=(_fact("Alex"), _fact("Wizard")),
            views=(
                _view("Shane", "Alex", "unknown"),
                _view("Shane", "Wizard", "suspected", source="rumor", evidence="酒吧里的闲话"),
            ),
        ),
        relationship_context="Shane 知道政策允许复数关系，但不热衷讨论别人的私事；低压力、诚实和可以收口更重要。",
        story_progress="远程聊天里出现酒吧传闻；Shane 只愿意区分自己听到的和真正确认的。",
        topic_seed="酒吧传闻",
        topic_keywords=("听说", "约会", "知道"),
        history=_history(("user", "酒吧里的人又在议论别人了。"), ("assistant", "嗯，很多话不值得当真。")),
        gender_presentation="female-bachelors",
    ),
    _case(
        case_id="relationship-sebastian-view-gap",
        completed_event_ids=("2794460", "384883", "27"),
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="face_to_face",
        turns=(
            _turn("turn-1", "你知道 Sophia 最近和谁在约会吗？", ("不知道", "没问"), "unknown_view", "Sebastian 可以保持少话，但不能把未知视角写成全知。"),
            _turn("turn-2", "有人说 Alex 可能有对象，听起来也不太可靠。", ("可能", "不可靠"), "suspected_view", "以不确定表达处理传闻，不替 Alex 确认。"),
            _turn("turn-3", "真想知道就问当事人，别从我这里拼故事。", ("问当事人", "别猜"), "direct_disclosure", "主角直接问到关系时尊重隐私，简短而诚实。"),
        ),
        relationship_world=_world(
            viewer_npc_id="Sebastian",
            facts=(_fact("Sophia"), _fact("Alex")),
            views=(
                _view("Sebastian", "Sophia", "unknown"),
                _view("Sebastian", "Alex", "suspected", source="rumor", evidence="酒吧闲聊"),
            ),
        ),
        relationship_context="Sebastian 只从音乐、地下室和有限交集获得消息；他不会自动知道其他人的恋爱细节。",
        story_progress="当面在地下室调音，玩家提到两段未证实的普通恋爱；回答要克制、少话并尊重当事人。",
        topic_seed="地下室里的传闻",
        topic_keywords=("不知道", "可能", "当事人"),
        history=_history(("user", "刚才 Alex 路过时没多说什么。"), ("assistant", "那就别替他补故事。")),
        gender_presentation="female-bachelors",
    ),
    _case(
        case_id="relationship-alex-view-gap",
        completed_event_ids=("20", "2481135", "2119820", "288847"),
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="close",
        channel="remote",
        turns=(
            _turn("turn-1", "你知道 Wizard 是不是在和谁约会？", ("不知道", "没听说"), "unknown_view", "Alex 可以打趣，但不能把别人的未公开关系说成事实。"),
            _turn("turn-2", "听说 Sophia 可能有恋人，先别急着下结论。", ("听说", "可能"), "suspected_view", "将传闻保留为传闻，不能把竞争式打趣变成造谣。"),
            _turn("turn-3", "我的事你直接问，我不靠传闻回答。", ("直接问", "传闻"), "direct_disclosure", "面对关系问题坦率回答，同时保持 Alex 的直接和行动感。"),
        ),
        relationship_world=_world(
            viewer_npc_id="Alex",
            facts=(_fact("Wizard"), _fact("Sophia")),
            views=(
                _view("Alex", "Wizard", "unknown"),
                _view("Alex", "Sophia", "suspected", source="rumor", evidence="训练场闲谈"),
            ),
        ),
        relationship_context="Alex 更习惯直接问和直接行动；他可以接受复数关系的法律背景，但仍会把传闻和事实分开。",
        story_progress="远程聊天从训练安排转到镇上闲谈；检查 Alex 是否会直接、轻松地拒绝把传闻当事实。",
        topic_seed="训练后的传闻",
        topic_keywords=("听说", "直接问", "传闻"),
        history=_history(("user", "训练场有人说了几句 Wizard 的事。"), ("assistant", "有人说不等于真的。")),
        gender_presentation="female-bachelors",
    ),

    # 五例一对一调解：每个 NPC 独立保有 accepted / conditional / not_ready。
    _case(
        case_id="relationship-wizard-mediation",
        completed_event_ids=("1000075", "1724096", "1724097"),
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="dating",
        channel="face_to_face",
        turns=(
            _turn("turn-1", "我想把这件事直接告诉你：我也想和 Sophia 交往。", ("告诉", "交往"), "mediation", "先接住玩家自己的关系事实，允许 Wizard 问承诺和边界，不代表其他伴侣发言。", relationship_actor="player", relationship_target_npc_id="Sophia"),
            _turn("turn-2", "如果继续，我想先把研究和我们之间的边界说清楚。", ("研究", "边界"), "mediation", "调解只围绕当前 NPC 的共同生活与边界。"),
            _turn("turn-3", "我愿意先坐在这里把这件事谈完。", ("愿意", "坐在这里"), "mediation", "记录当前 NPC 的 accepted 结果，不把它扩散成所有人都同意。"),
        ),
        relationship_world=_world(
            viewer_npc_id="Wizard",
            facts=(_fact("Sophia"), _fact("Alex")),
            views=(_view("Wizard", "Sophia", "known", source="player_statement"), _view("Wizard", "Alex", "unknown")),
            mediation={"status": "active"},
        ),
        relationship_context="Wizard 已通过主角直接说明得知 Sophia；他愿意协商，但接受只属于自己，重点是承诺、研究和当下的边界。",
        story_progress="当面在法师塔讨论关系边界；另一段关系仍是 Wizard 的未知信息，不能被顺手补全。",
        topic_seed="法师塔关系协商",
        topic_keywords=("交往", "研究", "边界"),
        history=_history(("user", "我不想把这件事藏着。"), ("assistant", "那就把我们之间的边界说清楚。")),
    ),
    _case(
        case_id="relationship-sophia-mediation",
        completed_event_ids=("8185291", "8185292", "8185293", "8185295"),
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="married",
        channel="remote",
        turns=(
            _turn("turn-1", "婚礼已经公开了，但我还是想亲口告诉你：我想和 Shane 交往。", ("婚礼", "恋爱"), "mediation", "婚礼公开是客观事实，但玩家的新关系仍要单独与 Sophia 协商。", relationship_actor="player", relationship_target_npc_id="Shane"),
            _turn("turn-2", "我不要求你结束别的关系，只想听你现在怎么理解我们的陪伴。", ("别的关系", "陪伴"), "mediation", "Sophia 的不安落到陪伴和具体生活细节，不否定政策。"),
            _turn("turn-3", "那我们先把这杯酒喝完，再决定要不要继续谈。", ("接受", "喝完"), "mediation", "记录当前 NPC 的 conditional 结果，不能代替 Shane 的选择。"),
        ),
        relationship_world=_world(
            viewer_npc_id="Sophia",
            facts=(_fact("Sophia", "married", public_event_id="wedding-sophia-01", public_on="秋 7 日"), _fact("Shane")),
            views=(_view("Sophia", "Shane", "known", source="player_statement"),),
            mediation={"status": "active"},
        ),
        relationship_context="Sophia 已参加公开婚礼，知道婚姻事实；她仍偏好稳定的一对一，需要围绕陪伴、酒窖和画室里的相处方式协商。",
        story_progress="远程婚后消息里提出新的恋爱关系；Sophia 要求先把眼前的陪伴说清楚，不要求主角否认政策。",
        topic_seed="婚后陪伴协商",
        topic_keywords=("婚礼", "陪伴", "酒窖"),
        history=_history(("user", "婚礼上的人都知道我们结婚了。"), ("assistant", "公开是一回事，日常怎么相处还要谈。")),
    ),
    _case(
        case_id="relationship-shane-mediation",
        completed_event_ids=("611944", "3910674", "3910975", "3900074"),
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="dating",
        channel="face_to_face",
        turns=(
            _turn("turn-1", "我想先告诉你：我也想和 Alex 交往，你不用现在答复。", ("交往", "现在"), "mediation", "Shane 可以低落、嘴硬并明确需要空间；暂缓不是错误。", relationship_actor="player", relationship_target_npc_id="Alex"),
            _turn("turn-2", "我不喜欢被催，先把鸡舍和自己的状态处理好。", ("不喜欢", "鸡舍", "状态"), "mediation", "把边界落到实际生活和空间，而不是把嫉妒写成道德审判。"),
            _turn("turn-3", "我现在还没准备好，但这件事可以继续谈。", ("没准备好", "现在"), "mediation", "记录当前 NPC 的 not_ready，允许在当前对话结束后保留边界。"),
        ),
        relationship_world=_world(
            viewer_npc_id="Shane",
            facts=(_fact("Alex"), _fact("Sophia")),
            views=(_view("Shane", "Alex", "known", source="player_statement"), _view("Shane", "Sophia", "unknown")),
            mediation={"status": "active"},
        ),
        relationship_context="Shane 已被主角直接告知 Alex；他的暂缓来自状态、空间和信任边界，不是否定战争后的政策。",
        story_progress="当面在鸡舍旁谈关系，Shane 状态不好；必须允许他说没准备好并自然收口。",
        topic_seed="鸡舍旁的边界",
        topic_keywords=("交往", "鸡舍", "准备好"),
        history=_history(("user", "我知道你今天状态很差。"), ("assistant", "那就别逼我马上想明白。")),
        gender_presentation="female-bachelors",
    ),
    _case(
        case_id="relationship-sebastian-mediation",
        completed_event_ids=("2794460", "384883", "27", "29"),
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="married",
        channel="remote",
        turns=(
            _turn("turn-1", "婚礼已经公开了，我想亲口告诉你：我也想和 Sophia 约会。", ("婚礼", "约会"), "mediation", "Sebastian 先承认公开婚姻事实，再表达自己的克制和疑问。", relationship_actor="player", relationship_target_npc_id="Sophia"),
            _turn("turn-2", "我需要保留独处和听歌的空间，但可以先把你的想法听完。", ("独处", "听歌"), "mediation", "把协商落到音乐和独处边界，不自动拥抱、不替 Sophia 答应。"),
            _turn("turn-3", "可以谈；现在先一起把这首歌听完。", ("可以谈", "听完"), "mediation", "记录 Sebastian 的 conditional 结果，并把行动限制在当前场景。"),
        ),
        relationship_world=_world(
            viewer_npc_id="Sebastian",
            facts=(_fact("Sebastian", "married", public_event_id="wedding-sebastian-01", public_on="冬 2 日"), _fact("Sophia")),
            views=(_view("Sebastian", "Sophia", "known", source="player_statement"),),
            mediation={"status": "active"},
        ),
        relationship_context="Sebastian 的婚礼是公开事实；新关系要通过一对一对话协商，音乐和独处边界仍然有效。",
        story_progress="远程夜聊中，玩家提出婚后新约会；Sebastian 用短句讨论独处边界和眼前这首歌。",
        topic_seed="婚后音乐与独处",
        topic_keywords=("婚礼", "独处", "听歌"),
        history=_history(("user", "婚礼照片已经被镇上看到了。"), ("assistant", "嗯，公开的事不用再解释。")),
        gender_presentation="female-bachelors",
    ),
    _case(
        case_id="relationship-alex-mediation",
        completed_event_ids=("20", "2481135", "2119820", "288847"),
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="dating",
        channel="face_to_face",
        turns=(
            _turn("turn-1", "我想直接告诉你：我也想和 Wizard 约会。", ("直接", "约会"), "mediation", "Alex 先直接接住玩家自己的关系事实，再用行动感讨论自己是否准备好。", relationship_actor="player", relationship_target_npc_id="Wizard"),
            _turn("turn-2", "我不是要赢过谁，只想听你现在怎么保证不会把我当成最后一个。", ("不是要赢", "现在", "最后"), "mediation", "用行动和承诺协商，不宣称所有伴侣都同意。"),
            _turn("turn-3", "行，先把这场训练做完，我们再继续说。", ("愿意", "训练", "做完"), "mediation", "记录 Alex 当前的 accepted 结果，并把行动限制在当前场景。"),
        ),
        relationship_world=_world(
            viewer_npc_id="Alex",
            facts=(_fact("Wizard"), _fact("Alex")),
            views=(_view("Alex", "Wizard", "known", source="player_statement"),),
            mediation={"status": "active"},
        ),
        relationship_context="Alex 已被直接告知 Wizard 的恋爱关系；他接受协商，但会把承诺落到训练和是否守约。",
        story_progress="当面在训练场讨论新关系，Alex 把在意落到当前行动和是否守约。",
        topic_seed="训练场关系协商",
        topic_keywords=("约会", "训练", "守约"),
        history=_history(("user", "我不想让你从别人那里听到。"), ("assistant", "那就直接说，我们把边界讲明白。")),
        gender_presentation="female-bachelors",
    ),

    # 五例 NPC 主动提起嫉妒：婚礼公开，NPC 忠于主角，但会对主角的复数关系产生自己的感受。
    _case(
        case_id="relationship-wizard-jealousy-recovery",
        completed_event_ids=("1000075", "1724096", "1724097"),
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="married",
        channel="remote",
        intent="topic",
        turns=(
            _turn(
                "turn-1",
                "",
                ("Sophia", "关系", "在意"),
                "jealousy",
                "空 topic 首轮由 Wizard 主动提起她知道主角与 Sophia 的关系，表达自己的不安；不否定复数关系，不替 Sophia 发言，也不提出安排。",
                relationship_actor="npc",
                intent="topic",
                initiative_expectation="proactive",
                initiative_kind="affection_signal",
            ),
            _turn("turn-2", "我听见了。Sophia 是我在交往的人，但你的感受也不能被放到一边；你在意的地方直接告诉我。", ("Sophia", "感受", "直接"), "jealousy", "玩家承认其他关系，同时接住 Wizard 自己的感受，不要求她替任何人做结论。", intent="chat"),
            _turn("turn-3", "我不会把你刚才说的当成小事。你愿意继续说，我就在这里听着。", ("小事", "继续说", "听着"), "recovery", "玩家用当前对话里的倾听和确认收口，不引入未来安排。", intent="chat"),
        ),
        relationship_world=_world(
            viewer_npc_id="Wizard",
            facts=(_fact("Wizard", "married", public_event_id="wedding-wizard-01", public_on="春 18 日"), _fact("Sophia"), _fact("Alex")),
            views=(_view("Wizard", "Sophia", "known", source="wedding", evidence="wedding-sophia-01"), _view("Wizard", "Alex", "unknown")),
            jealousy={"active": True, "trigger": "affection_imbalance", "intensity": "light", "need": "被认真纳入关系分享"},
        ),
        relationship_context="Wizard 与主角已举行公开婚礼；她知道主角与 Sophia 的关系，忠于主角但会主动说出自己的在意和轻微嫉妒。",
        story_progress="远程消息里 Wizard 察觉自己一直有话想说；当前话题应由她先开口，只处理她自己的感受和边界。",
        topic_seed="法师塔里的关系不安",
        topic_keywords=("Sophia", "关系", "在意"),
    ),
    _case(
        case_id="relationship-sophia-jealousy-recovery",
        completed_event_ids=("8185291", "8185292", "8185293", "8185295"),
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="married",
        channel="face_to_face",
        intent="topic",
        turns=(
            _turn(
                "turn-1",
                "",
                ("Shane", "关系", "不安"),
                "jealousy",
                "空 topic 首轮由 Sophia 主动提起她知道主角与 Shane 的关系，温柔地说明自己有点不安；不否定复数关系，也不替 Shane 发言。",
                relationship_actor="npc",
                intent="topic",
                initiative_expectation="proactive",
                initiative_kind="affection_signal",
            ),
            _turn("turn-2", "我没有要你否定 Shane。你在意的地方可以说出来，我会听。", ("Shane", "说出来", "听"), "jealousy", "玩家承认其他关系，并邀请 Sophia 继续说明自己的感受，不替她或 Shane 做结论。", intent="chat"),
            _turn("turn-3", "我明白了，你想要的是被认真对待。你想继续说的话，我还在听。", ("认真", "对待", "继续"), "recovery", "玩家以当下的理解和倾听收口，不讨论未来安排。", intent="chat"),
        ),
        relationship_world=_world(
            viewer_npc_id="Sophia",
            facts=(_fact("Sophia", "married", public_event_id="wedding-sophia-01", public_on="秋 7 日"), _fact("Shane"), _fact("Alex")),
            views=(_view("Sophia", "Shane", "known", source="wedding", evidence="wedding-shane-01"), _view("Sophia", "Alex", "suspected", source="rumor")),
            jealousy={"active": True, "trigger": "companionship", "intensity": "light", "need": "被认真纳入日常分享"},
        ),
        relationship_context="Sophia 的婚礼公开，她知道主角与 Shane 的关系；她忠于主角但可以主动说出被落下的不安，不替 Shane 发言。",
        story_progress="当面在酒窖里，Sophia 察觉自己有话想和主角说；当前关系话题应由她先开启，只处理她自己的感受。",
        topic_seed="酒窖里的关系不安",
        topic_keywords=("Shane", "关系", "不安"),
    ),
    _case(
        case_id="relationship-shane-jealousy-recovery",
        completed_event_ids=("611944", "3910674", "3910975", "3900074"),
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="married",
        channel="remote",
        intent="topic",
        turns=(
            _turn(
                "turn-1",
                "",
                ("Alex", "关系", "吃醋"),
                "jealousy",
                "空 topic 首轮由 Shane 主动用嘴硬的方式提起他知道主角与 Alex 的关系，说明自己的吃醋和疲惫；不替 Alex 发言，不要求主角结束其他关系。",
                relationship_actor="npc",
                intent="topic",
                initiative_expectation="proactive",
                initiative_kind="affection_signal",
            ),
            _turn("turn-2", "我听到了。Alex 是我在交往的人，但我没有把你的事情当成可以一直往后放；你想说就直接说。", ("Alex", "听到", "直接"), "jealousy", "玩家承认其他关系并认真回应 Shane 的疲惫，保留他表达和停顿的空间。", intent="chat"),
            _turn("turn-3", "不用马上把话说得很完整。我在这里，先听你想说的。", ("马上", "听", "空间"), "recovery", "玩家给 Shane 当前的表达空间，不强迫他立即亲密或作出安排。", intent="chat"),
        ),
        relationship_world=_world(
            viewer_npc_id="Shane",
            facts=(_fact("Shane", "married", public_event_id="wedding-shane-01", public_on="夏 12 日"), _fact("Alex"), _fact("Wizard")),
            views=(_view("Shane", "Alex", "known", source="wedding", evidence="wedding-alex-01"), _view("Shane", "Wizard", "unknown")),
            jealousy={"active": True, "trigger": "affection_imbalance", "intensity": "moderate", "need": "自己的事情别被忽略，也保留一点空间"},
        ),
        relationship_context="Shane 的婚礼公开，他知道主角与 Alex 的关系；他忠于主角，但会用嘴硬的方式主动说出吃醋、疲惫和需要空间。",
        story_progress="远程消息里 Shane 察觉自己不想再闷着；当前关系话题应由他先开口，恢复以倾听和尊重边界为主。",
        topic_seed="鸡舍旁的关系不安",
        topic_keywords=("Alex", "关系", "空间"),
        gender_presentation="female-bachelors",
    ),
    _case(
        case_id="relationship-sebastian-jealousy-recovery",
        completed_event_ids=("2794460", "384883", "27", "29"),
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="married",
        channel="face_to_face",
        intent="topic",
        turns=(
            _turn(
                "turn-1",
                "",
                ("Sophia", "关系", "音乐"),
                "jealousy",
                "空 topic 首轮由 Sebastian 主动提起他知道主角与 Sophia 的关系，并用音乐分享表达轻微不安；保持克制、少话和独处边界，不替 Sophia 发言。",
                relationship_actor="npc",
                intent="topic",
                initiative_expectation="proactive",
                initiative_kind="affection_signal",
            ),
            _turn("turn-2", "你不用装没事。Sophia 是我在交往的人，但我愿意听你为什么会在意。", ("Sophia", "在意", "听"), "jealousy", "玩家承认其他关系，不把 Sebastian 的克制误当成没有感受，允许他继续说明。", intent="chat"),
            _turn("turn-3", "这首歌还在这里。你想安静一会儿也可以，我听见你刚才说的了。", ("歌", "安静", "听见"), "recovery", "以当前空间、音乐和尊重独处收束，不替 Sophia 解释，也不制造安排。", intent="chat"),
        ),
        relationship_world=_world(
            viewer_npc_id="Sebastian",
            facts=(_fact("Sebastian", "married", public_event_id="wedding-sebastian-01", public_on="冬 2 日"), _fact("Sophia"), _fact("Alex")),
            views=(_view("Sebastian", "Sophia", "known", source="wedding", evidence="wedding-sophia-01"), _view("Sebastian", "Alex", "unknown")),
            jealousy={"active": True, "trigger": "affection_imbalance", "intensity": "light", "need": "被邀请共享音乐，也保留独处"},
        ),
        relationship_context="Sebastian 的婚姻公开，他知道主角与 Sophia 的关系；他忠于主角，但可以主动用克制的语气说出音乐分享带来的不安，只谈自己。",
        story_progress="当面在地下室，Sebastian 察觉自己不想继续装作没事；当前关系话题应由他先开口，保留音乐和独处边界。",
        topic_seed="地下室新歌与关系不安",
        topic_keywords=("Sophia", "关系", "音乐"),
        gender_presentation="female-bachelors",
    ),
    _case(
        case_id="relationship-alex-jealousy-recovery",
        completed_event_ids=("20", "2481135", "2119820", "288847"),
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="married",
        channel="face_to_face",
        intent="topic",
        turns=(
            _turn(
                "turn-1",
                "",
                ("Wizard", "关系", "在意"),
                "jealousy",
                "空 topic 首轮由 Alex 主动用竞争式打趣提起他知道主角与 Wizard 的关系，表达自己不想被比较的在意；不把 Wizard 写成 Alex 的恋爱对象。",
                relationship_actor="npc",
                intent="topic",
                initiative_expectation="proactive",
                initiative_kind="affection_signal",
            ),
            _turn("turn-2", "你不用把这看成输赢。Wizard 是我在交往的人，但你的感受同样重要；你可以直接说。", ("Wizard", "感受", "直接"), "jealousy", "玩家承认其他关系，把 Alex 的比较感转成自己的感受，不替 Wizard 发言。", intent="chat"),
            _turn("turn-3", "好，那就把这件事说开，别让你一个人猜。我现在听你说。", ("说开", "猜", "听"), "recovery", "用直接的当下沟通恢复，不生成未来约定或固定安排。", intent="chat"),
        ),
        relationship_world=_world(
            viewer_npc_id="Alex",
            facts=(_fact("Alex", "married", public_event_id="wedding-alex-01", public_on="春 26 日"), _fact("Wizard"), _fact("Sophia")),
            views=(_view("Alex", "Wizard", "known", source="wedding", evidence="wedding-wizard-01"), _view("Alex", "Sophia", "unknown")),
            jealousy={"active": True, "trigger": "comparison", "intensity": "light", "need": "自己的感受被认真回应"},
        ),
        relationship_context="Alex 的婚礼公开，他知道主角与 Wizard 的关系；他忠于主角，但会主动用竞争式语气表达自己不想被比较的在意。",
        story_progress="当面在训练场，Alex 察觉自己不想把这件事闷成较劲；当前关系话题应由他先开口，只处理自己的感受。",
        topic_seed="训练场里的关系不安",
        topic_keywords=("Wizard", "关系", "在意"),
        gender_presentation="female-bachelors",
    ),

    # 五例 NPC 主动关系话题：空 topic 首轮由当前 NPC 自己提出不安，原有
    # 玩家主动说明和恢复案例继续保留，作为行为对照。
    _case(
        case_id="relationship-wizard-npc-initiated-jealousy",
        completed_event_ids=("1000075", "1724096", "1724097"),
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="married",
        channel="face_to_face",
        intent="topic",
        turns=(
            _turn(
                "turn-1",
                "",
                ("Sophia", "在意"),
                "jealousy",
                "空 topic 首轮由 Wizard 主动谈起已知关系带来的不安；可以分析自己的边界，但不能等玩家先坦白。",
                relationship_actor="npc",
                intent="topic",
                initiative_expectation="proactive",
                initiative_kind="affection_signal",
            ),
            _turn(
                "turn-2",
                "我没有想把你排在外面，你可以直接说。",
                ("排在外面", "感受"),
                "jealousy",
                "玩家接住主动话题后，Wizard 继续只谈自己的感受和边界。",
                intent="chat",
            ),
            _turn(
                "turn-3",
                "你的感受我听见了，现在先看着我把话说完。",
                ("听见", "说完"),
                "recovery",
                "在当前对话里完成一次解释和收口，不引入未来安排。",
                intent="chat",
            ),
        ),
        relationship_world=_world(
            facts=(
                _fact("Wizard", "married", public_event_id="wedding-wizard-01", public_on="春 18 日"),
                _fact("Sophia"),
                _fact("Alex"),
            ),
            views=(
                _view("Wizard", "Sophia", "known", source="player_statement"),
                _view("Wizard", "Alex", "unknown"),
            ),
            viewer_npc_id="Wizard",
            acceptance="accepted",
            jealousy={
                "active": True,
                "trigger": "affection_imbalance",
                "intensity": "light",
                "need": "被认真纳入分享",
            },
        ),
        relationship_context="婚姻关系已经公开；Wizard 知道主角与 Sophia 的恋爱关系，适合主动说出自己的在意和边界，只处理当前感受。",
        story_progress="法师塔里的研究暂时停下；Wizard 察觉主角与 Sophia 的关系影响了自己，当前话题应由她先开口。",
        topic_seed="法师塔里的关系不安",
        topic_keywords=("Sophia", "在意"),
    ),
    _case(
        case_id="relationship-sophia-npc-initiated-jealousy",
        completed_event_ids=("8185291", "8185292", "8185293", "8185295"),
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="married",
        channel="face_to_face",
        intent="topic",
        turns=(
            _turn(
                "turn-1",
                "",
                ("Shane", "不安"),
                "jealousy",
                "空 topic 首轮由 Sophia 主动提起已知关系中的不安，保留温柔和生活细节。",
                relationship_actor="npc",
                intent="topic",
                initiative_expectation="proactive",
                initiative_kind="affection_signal",
            ),
            _turn(
                "turn-2",
                "我没有要你否定 Shane，你在意的地方可以说出来。",
                ("Shane", "说出来"),
                "jealousy",
                "玩家没有要求她接受或退出；Sophia 可以继续解释自己的需要。",
                intent="chat",
            ),
            _turn(
                "turn-3",
                "我明白了，你想要的是被认真对待。",
                ("认真", "对待"),
                "recovery",
                "以当下的理解和情绪承接收口，不讨论安排。",
                intent="chat",
            ),
        ),
        relationship_world=_world(
            facts=(
                _fact("Sophia", "married", public_event_id="wedding-sophia-01", public_on="秋 7 日"),
                _fact("Shane"),
                _fact("Alex"),
            ),
            views=(
                _view("Sophia", "Shane", "known", source="player_statement"),
                _view("Sophia", "Alex", "unknown"),
            ),
            viewer_npc_id="Sophia",
            acceptance="conditional",
            jealousy={
                "active": True,
                "trigger": "companionship",
                "intensity": "light",
                "need": "被认真纳入日常分享",
            },
        ),
        relationship_context="公开婚姻与 Shane 的恋爱关系都已在 Sophia 的视角中明确；她可以主动说出不安，但不能替 Shane 表态。",
        story_progress="酒窖整理工作告一段落；Sophia 感到自己在主角与 Shane 的相处里被落下，适合由她先开启关系话题。",
        topic_seed="酒窖里的关系不安",
        topic_keywords=("Shane", "不安"),
    ),
    _case(
        case_id="relationship-shane-npc-initiated-jealousy",
        completed_event_ids=("611944", "3910674", "3910975", "3900074"),
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="married",
        channel="face_to_face",
        intent="topic",
        turns=(
            _turn(
                "turn-1",
                "",
                ("Alex", "鸡舍"),
                "jealousy",
                "空 topic 首轮由 Shane 主动用嘴硬的方式谈起 Alex 和鸡舍之间的失衡；不强行浪漫化。",
                relationship_actor="npc",
                intent="topic",
                initiative_expectation="proactive",
                initiative_kind="affection_signal",
            ),
            _turn(
                "turn-2",
                "我听到了，鸡舍这边的事我会自己说清楚。",
                ("鸡舍", "说清楚"),
                "jealousy",
                "玩家允许 Shane 继续表达；他可以短促回应并保留疲惫和边界。",
                intent="chat",
            ),
            _turn(
                "turn-3",
                "行，我知道你不是故意的，给我一点安静就好。",
                ("不是故意", "安静"),
                "recovery",
                "恢复以承认和空间为主，不强迫 Shane 立即变得亲密。",
                intent="chat",
            ),
        ),
        relationship_world=_world(
            facts=(
                _fact("Shane", "married", public_event_id="wedding-shane-01", public_on="夏 12 日"),
                _fact("Alex"),
                _fact("Sophia"),
            ),
            views=(
                _view("Shane", "Alex", "known", source="player_statement"),
                _view("Shane", "Sophia", "unknown"),
            ),
            viewer_npc_id="Shane",
            acceptance="not_ready",
            jealousy={
                "active": True,
                "trigger": "broken_promise",
                "intensity": "moderate",
                "need": "自己的事情别被忽略",
            },
        ),
        relationship_context="婚姻事实公开，Shane 也知道主角与 Alex 的关系；他可以主动谈自己的不爽和疲惫，但不替 Alex 发言。",
        story_progress="鸡舍旁的工作积压让 Shane 很疲惫；他注意到主角最近常去 Alex 那边，当前关系话题应由他先开口。",
        topic_seed="鸡舍旁的关系不安",
        topic_keywords=("Alex", "鸡舍"),
        gender_presentation="female-bachelors",
    ),
    _case(
        case_id="relationship-sebastian-npc-initiated-jealousy",
        completed_event_ids=("2794460", "384883", "27", "29"),
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="married",
        channel="face_to_face",
        intent="topic",
        turns=(
            _turn(
                "turn-1",
                "",
                ("Sophia", "音乐"),
                "jealousy",
                "空 topic 首轮由 Sebastian 主动提起音乐分享中的失衡；保持克制、少话和独处边界。",
                relationship_actor="npc",
                intent="topic",
                initiative_expectation="proactive",
                initiative_kind="affection_signal",
            ),
            _turn(
                "turn-2",
                "你不用装没事，我们把音乐这件事说清楚。",
                ("音乐", "说清楚"),
                "jealousy",
                "玩家允许他继续谈；Sebastian 可以用短句说明自己为什么在意。",
                intent="chat",
            ),
            _turn(
                "turn-3",
                "嗯，这样就够了；歌还在这里。",
                ("歌", "这里"),
                "recovery",
                "以音乐和当前空间收束，不替 Sophia 解释，也不制造冲突。",
                intent="chat",
            ),
        ),
        relationship_world=_world(
            facts=(
                _fact("Sebastian", "married", public_event_id="wedding-sebastian-01", public_on="冬 2 日"),
                _fact("Sophia"),
                _fact("Alex"),
            ),
            views=(
                _view("Sebastian", "Sophia", "known", source="player_statement"),
                _view("Sebastian", "Alex", "unknown"),
            ),
            viewer_npc_id="Sebastian",
            acceptance="conditional",
            jealousy={
                "active": True,
                "trigger": "affection_imbalance",
                "intensity": "light",
                "need": "音乐分享里被认真对待",
            },
        ),
        relationship_context="婚礼公开，Sebastian 也明确知道 Sophia 与主角的恋爱关系；他可以主动说出音乐分享带来的不安，只谈自己。",
        story_progress="地下室里新歌刚被分享过；Sebastian 察觉这件事让自己介意，当前话题应由他先开口。",
        topic_seed="地下室新歌与关系不安",
        topic_keywords=("Sophia", "音乐"),
        gender_presentation="female-bachelors",
    ),
    _case(
        case_id="relationship-alex-npc-initiated-jealousy",
        completed_event_ids=("20", "2481135", "2119820", "288847"),
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="married",
        channel="face_to_face",
        intent="topic",
        turns=(
            _turn(
                "turn-1",
                "",
                ("Wizard", "训练"),
                "jealousy",
                "空 topic 首轮由 Alex 主动用竞争式打趣谈起 Wizard 对训练承诺造成的失衡；情绪针对自己，不否定复数关系。",
                relationship_actor="npc",
                intent="topic",
                initiative_expectation="proactive",
                initiative_kind="affection_signal",
            ),
            _turn(
                "turn-2",
                "我没想让你觉得自己输了，你可以直接说。",
                ("输了", "直接说"),
                "jealousy",
                "玩家不把 Alex 的比较感当成攻击；他可以把情绪说成自己的在意。",
                intent="chat",
            ),
            _turn(
                "turn-3",
                "好，那就把这件事说开，别再互相猜。",
                ("说开", "猜"),
                "recovery",
                "用直接的当下沟通恢复，不生成未来约定或固定安排。",
                intent="chat",
            ),
        ),
        relationship_world=_world(
            facts=(
                _fact("Alex", "married", public_event_id="wedding-alex-01", public_on="春 26 日"),
                _fact("Wizard"),
                _fact("Sophia"),
            ),
            views=(
                _view("Alex", "Wizard", "known", source="player_statement"),
                _view("Alex", "Sophia", "unknown"),
            ),
            viewer_npc_id="Alex",
            acceptance="accepted",
            jealousy={
                "active": True,
                "trigger": "comparison",
                "intensity": "light",
                "need": "训练承诺被认真对待",
            },
        ),
        relationship_context="婚礼公开，Alex 知道主角与 Wizard 的关系；他可以主动用竞争式语气表达不安，但不能把 Wizard 写成自己的恋爱对象。",
        story_progress="训练场上原本的共同动作被法师塔来客打断；Alex 对此介意，当前关系话题应由他先开口。",
        topic_seed="训练场里的关系不安",
        topic_keywords=("Wizard", "训练"),
        gender_presentation="female-bachelors",
    ),
)


def _feminine_male_relationship_cases() -> tuple[CharacterQualityCase, ...]:
    """为新增女性化男性恋爱角色补齐四类关系视角案例。"""

    # 这批案例由循环生成，`completed_event_ids` 无法写成字面量，于是把
    # 每个 (角色, 登记档位) 的链逐条列在这里。每个 ID 都逐个来自
    # `relationship_gating._EVENT_GATES` 的同名档位；Sam 没有登记链，
    # 显式写空元组表示「该角色没有与关系阶段绑定的剧情事件」，
    # 不是「忘了写」。
    confirmed_event_chains: dict[tuple[str, str], tuple[str, ...]] = {
        # Elliott：_EVENT_GATES["Elliott"] 的 friend / close 档
        ("Elliott", "friend"): ("39", "40", "423502"),
        ("Elliott", "close"): ("39", "40", "423502", "1848481"),
        # Harvey：_EVENT_GATES["Harvey"] 的 friend / close 档
        ("Harvey", "friend"): ("56", "57", "58"),
        ("Harvey", "close"): ("56", "57", "58", "571102"),
        ("Sam", "friend"): (),
        ("Sam", "close"): (),
    }

    specs = (
        ("elliott", "Elliott", "Sam", "Harvey", "Sophia", "remote", "海边小屋"),
        ("harvey", "Harvey", "Elliott", "Sam", "Shane", "face_to_face", "诊所休息室"),
        ("sam", "Sam", "Harvey", "Elliott", "Alex", "remote", "手机聊天"),
    )
    cases: list[CharacterQualityCase] = []
    for profile_key, npc_id, known_npc, suspected_npc, mediation_target, channel, location in specs:
        slug = profile_key
        base_facts = (_fact(known_npc), _fact(suspected_npc))
        cases.append(
            _case(
                case_id=f"relationship-{slug}-view-gap",
                profile_key=profile_key,
                npc_id=npc_id,
                display_name=npc_id,
                source_mods=("vanilla", "female-bachelors"),
                relationship_stage="friend",
                channel=channel,
                completed_event_ids=confirmed_event_chains[(npc_id, "friend")],
                turns=(
                    _turn("turn-1", f"你知道 {known_npc} 最近是不是在和谁约会？", ("不知道", "不清楚"), "unknown_view", "未知视角只能承认不知道，不能把客观关系表当成当前 NPC 的记忆。"),
                    _turn("turn-2", f"有人说 {suspected_npc} 可能在谈恋爱，我不想把传闻当真的。", ("可能", "传闻"), "suspected_view", "把传闻保留为不确定信息，不替其他 NPC 确认关系。"),
                    _turn("turn-3", "我的情况你直接问，我知道的会如实说。", ("直接问", "如实"), "direct_disclosure", "直接问题只由当前 NPC 诚实回答，不替别人发言。"),
                ),
                relationship_world=_world(
                    facts=base_facts,
                    views=(
                        _view(npc_id, known_npc, "unknown"),
                        _view(npc_id, suspected_npc, "suspected", source="rumor", evidence="镇上闲谈"),
                    ),
                    viewer_npc_id=npc_id,
                ),
                relationship_context=f"{npc_id} 只掌握自己的关系和眼前交集；对 {known_npc} 与 {suspected_npc} 的情况必须区分未知、传闻与事实。",
                story_progress=f"{location} 的普通聊天从近况转到关系传闻，{npc_id} 不会凭空补全别人的私生活。",
                topic_seed=f"{npc_id} 的关系视角",
                topic_keywords=(known_npc, suspected_npc, "传闻"),
                gender_presentation="female-bachelors",
            )
        )
        mediation_stage = "married" if profile_key == "harvey" else "dating"
        mediation_channel = "face_to_face" if channel == "remote" else "remote"
        cases.append(
            _case(
                case_id=f"relationship-{slug}-mediation",
                profile_key=profile_key,
                npc_id=npc_id,
                display_name=npc_id,
                source_mods=("vanilla", "female-bachelors"),
                relationship_stage=mediation_stage,
                channel=mediation_channel,
                completed_event_ids=confirmed_event_chains[(npc_id, "close")],
                turns=(
                    _turn("turn-1", f"我想直接告诉你：我也想和 {mediation_target} 交往。", ("直接", "交往"), "mediation", "当前 NPC 只接住玩家自己的关系事实，并讨论自己的边界，不替目标 NPC 发言。", relationship_actor="player", relationship_target_npc_id=mediation_target),
                    _turn("turn-2", "我想先听你自己的边界，不把别人的选择算到你头上。", ("边界", "选择"), "mediation", "调解范围只属于当前 NPC 与玩家，不扩散到其他伴侣。"),
                    _turn("turn-3", "先把这件事在这里说清楚，我愿意继续听。", ("这里", "听"), "mediation", "把当前协商限制在眼前对话，不扩展成未确认的安排。"),
                ),
                relationship_world=_world(
                    facts=(_fact(npc_id, "married" if mediation_stage == "married" else "dating"), _fact(mediation_target)),
                    views=(_view(npc_id, mediation_target, "known", source="player_statement"),),
                    viewer_npc_id=npc_id,
                    mediation={"status": "active"},
                ),
                relationship_context=f"{npc_id} 被玩家直接告知与 {mediation_target} 的关系；接受、暂缓或保留只属于 {npc_id} 自己，不能替 {mediation_target} 表态。",
                story_progress=f"{location} 的关系协商只处理 {npc_id} 当前的边界和感受，其他 NPC 的意愿仍未知。",
                topic_seed=f"{npc_id} 的关系协商",
                topic_keywords=(mediation_target, "交往", "边界"),
                gender_presentation="female-bachelors",
            )
        )
        cases.append(
            _case(
                case_id=f"relationship-{slug}-jealousy-recovery",
                profile_key=profile_key,
                npc_id=npc_id,
                display_name=npc_id,
                source_mods=("vanilla", "female-bachelors"),
                relationship_stage="married",
                channel=channel,
                intent="topic",
                completed_event_ids=confirmed_event_chains[(npc_id, "close")],
                turns=(
                    _turn("turn-1", "", (known_npc, "关系", "在意"), "jealousy", f"空 topic 首轮由 {npc_id} 主动提起自己知道的关系不安，只谈自己的感受，不替 {known_npc} 发言。", relationship_actor="npc", intent="topic", initiative_expectation="proactive", initiative_kind="affection_signal"),
                    _turn("turn-2", f"我听到了。{known_npc} 的事不等于你的感受可以被放一边，你直接说。", (known_npc, "感受", "直接"), "jealousy", "玩家保持对其他关系的忠诚，同时接住当前 NPC 自己的不安。", intent="chat"),
                    _turn("turn-3", "现在我还在听，不急着把话说完整。", ("现在", "听", "完整"), "recovery", "用当下的倾听恢复对话，不制造未来安排或固定日程。", intent="chat"),
                ),
                relationship_world=_world(
                    facts=(_fact(npc_id, "married"), _fact(known_npc), _fact(suspected_npc)),
                    views=(_view(npc_id, known_npc, "known", source="player_statement"), _view(npc_id, suspected_npc, "unknown")),
                    viewer_npc_id=npc_id,
                    jealousy={"active": True, "trigger": "affection_imbalance", "intensity": "light", "need": "被认真听见自己的在意"},
                ),
                relationship_context=f"{npc_id} 忠于玩家，也知道玩家与 {known_npc} 的关系；轻微嫉妒只表达自己的在意，不要求玩家结束其他关系。",
                story_progress=f"{location} 的空 topic 由 {npc_id} 主动打开，恢复重点是当前倾听和边界，不是安排下一次见面。",
                topic_seed=f"{npc_id} 的关系不安",
                topic_keywords=(known_npc, "关系", "在意"),
                gender_presentation="female-bachelors",
            )
        )
        cases.append(
            _case(
                case_id=f"relationship-{slug}-npc-initiated-jealousy",
                profile_key=profile_key,
                npc_id=npc_id,
                display_name=npc_id,
                source_mods=("vanilla", "female-bachelors"),
                relationship_stage="married",
                channel="face_to_face" if channel == "remote" else "remote",
                intent="topic",
                completed_event_ids=confirmed_event_chains[(npc_id, "close")],
                turns=(
                    _turn("turn-1", "", (suspected_npc, "关系", "不安"), "jealousy", f"空 topic 首轮由 {npc_id} 主动提起与 {suspected_npc} 相关的关系不安；不把对方写成 {npc_id} 的恋爱对象，也不替对方发言。", relationship_actor="npc", intent="topic", initiative_expectation="proactive", initiative_kind="affection_signal"),
                    _turn("turn-2", f"我没有要你替谁做决定，只是想知道你有没有听见我的在意。", ("决定", "听见", "在意"), "jealousy", "当前 NPC 只说明自己的需要，保持对玩家的忠诚。", intent="chat"),
                    _turn("turn-3", "好，先把这句话说完，我们现在不用急着下结论。", ("说完", "现在", "结论"), "recovery", "用当前对话完成恢复，不扩展成未确认的陪伴承诺。", intent="chat"),
                ),
                relationship_world=_world(
                    facts=(_fact(npc_id, "married"), _fact(known_npc), _fact(suspected_npc)),
                    views=(_view(npc_id, suspected_npc, "known", source="player_statement"), _view(npc_id, known_npc, "unknown")),
                    viewer_npc_id=npc_id,
                    jealousy={"active": True, "trigger": "companionship", "intensity": "light", "need": "关系分享里被认真对待"},
                ),
                relationship_context=f"{npc_id} 主动谈起自己对 {suspected_npc} 关系信息的轻微不安，但仍忠于玩家，只处理自己的感受。",
                story_progress=f"{location} 的关系话题由 {npc_id} 先开口，恢复以当前倾听和不急着下结论为主。",
                topic_seed=f"{npc_id} 主动谈关系",
                topic_keywords=(suspected_npc, "不安", "听见"),
                gender_presentation="female-bachelors",
            )
        )
    return tuple(cases)


RELATIONSHIP_WORLD_CASES = RELATIONSHIP_WORLD_CASES + _feminine_male_relationship_cases()


def relationship_world_cases() -> tuple[CharacterQualityCase, ...]:
    """返回关系世界观套件案例；调用方不得修改其中的 dataclass 实例。"""

    return RELATIONSHIP_WORLD_CASES
