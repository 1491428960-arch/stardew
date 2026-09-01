from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping


@dataclass(frozen=True)
class CharacterQualityTurn:
    turn_id: str
    message: str
    expected_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    evaluation_focus: str = ""


@dataclass(frozen=True)
class CharacterQualityCase:
    case_id: str
    profile_key: str
    npc_id: str
    display_name: str
    source_mods: tuple[str, ...]
    relationship_stage: str
    channel: str
    message: str
    history: tuple[dict[str, str], ...] = ()
    expected_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    game_state: tuple[tuple[str, object], ...] = ()
    story_progress: str = ""
    turns: tuple[CharacterQualityTurn, ...] = ()

    def dialogue_turns(self) -> tuple[CharacterQualityTurn, ...]:
        if self.turns:
            return self.turns
        return (
            CharacterQualityTurn(
                turn_id="turn-1",
                message=self.message,
                expected_terms=self.expected_terms,
                forbidden_terms=self.forbidden_terms,
                evaluation_focus="检查第一轮是否自然回应当前场景和话题。",
            ),
        )


@dataclass(frozen=True)
class CharacterProfileConfig:
    profile_key: str
    npc_id: str
    display_name: str
    source_mods: tuple[str, ...]
    case_ids: tuple[str, ...]


DEFAULT_CHARACTER_PROFILES: dict[str, CharacterProfileConfig] = {
    "wizard_rasmodia": CharacterProfileConfig(
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        case_ids=(
            "wizard-daily",
            "wizard-follow-up",
            "wizard-remote-invite",
            "wizard-close-background",
        ),
    ),
    "sophia": CharacterProfileConfig(
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        case_ids=(
            "sophia-daily",
            "sophia-vineyard",
            "sophia-face-follow-up",
            "sophia-close-background",
        ),
    ),
    "shane": CharacterProfileConfig(
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        case_ids=(
            "shane-coop",
            "shane-remote-care",
            "shane-follow-up",
            "shane-close-boundary",
        ),
    ),
    "sebastian": CharacterProfileConfig(
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        case_ids=(
            "sebastian-bike",
            "sebastian-rain",
            "sebastian-follow-up",
        ),
    ),
    "alex": CharacterProfileConfig(
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        case_ids=(
            "alex-training",
            "alex-remote-invite",
            "alex-follow-up",
            "alex-close-background",
        ),
    ),
}


def _game_state(**values: object) -> tuple[tuple[str, object], ...]:
    return tuple((key, value) for key, value in values.items() if value not in (None, ""))


_BASE_CASES: tuple[CharacterQualityCase, ...] = (
    CharacterQualityCase(
        case_id="wizard-daily",
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="acquaintance",
        channel="remote",
        message="最近过得怎么样？",
        expected_terms=("还", "事做"),
        forbidden_terms=("星界", "奥术", "元素", "预言"),
        game_state=_game_state(
            season="春",
            date="春 1 日",
            weather="晴天",
            time=800,
            location="法师塔",
            friendshipHearts=2,
        ),
        story_progress="初到山谷：刚认识法师，尚未触发法师塔相关事件",
    ),
    CharacterQualityCase(
        case_id="wizard-follow-up",
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="friend",
        channel="face_to_face",
        message="那第三组现在稳定了吗？",
        history=(
            {"role": "user", "content": "你先看看第三组。"},
            {"role": "assistant", "content": "我先核对记录。"},
        ),
        expected_terms=("第三组", "重测"),
        forbidden_terms=("星界", "预言"),
        game_state=_game_state(
            season="夏",
            date="夏 14 日",
            weather="下雨",
            time=1830,
            location="法师塔",
            friendshipHearts=6,
        ),
        story_progress="已确认第三组数据异常：正在进行第二轮复测",
    ),
    CharacterQualityCase(
        case_id="wizard-remote-invite",
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="friend",
        channel="remote",
        message="改天一起核对一下记录？",
        expected_terms=("时间", "核对", "可以"),
        forbidden_terms=("神秘仪式", "预言"),
        game_state=_game_state(
            season="秋",
            date="秋 22 日",
            weather="阴天",
            time=2100,
            location="手机聊天",
            friendshipHearts=6,
        ),
        story_progress="第三组复测已完成：线上提出邀约，尚未约定当面时间",
    ),
    CharacterQualityCase(
        case_id="sophia-daily",
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="acquaintance",
        channel="remote",
        message="今天葡萄园忙不忙？",
        expected_terms=("葡萄", "忙"),
        game_state=_game_state(
            season="春",
            date="春 5 日",
            weather="晴天",
            time=900,
            location="葡萄园",
            friendshipHearts=2,
        ),
        story_progress="刚认识：第一次从线上问起葡萄园的日常工作",
    ),
    CharacterQualityCase(
        case_id="sophia-vineyard",
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="friend",
        channel="face_to_face",
        message="要不要一起去看看新摘的葡萄？",
        expected_terms=("葡萄", "一起"),
        game_state=_game_state(
            season="夏",
            date="夏 14 日",
            weather="晴天",
            time=1400,
            location="葡萄园",
            friendshipHearts=6,
        ),
        story_progress="今年第一批葡萄已经采摘：朋友阶段的当面邀约",
    ),
    CharacterQualityCase(
        case_id="sophia-face-follow-up",
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="friend",
        channel="face_to_face",
        message="刚才那桶酒的味道怎么样？",
        history=({"role": "user", "content": "我们刚才闻过新酿的葡萄酒。"},),
        expected_terms=("酒", "葡萄"),
        game_state=_game_state(
            season="秋",
            date="秋 18 日",
            weather="阴天",
            time=1700,
            location="葡萄园酒窖",
            friendshipHearts=6,
        ),
        story_progress="刚打开新酿的酒桶：继续刚才的当面品尝话题",
    ),
    CharacterQualityCase(
        case_id="shane-coop",
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="acquaintance",
        channel="face_to_face",
        message="鸡舍今天忙吗？",
        expected_terms=("鸡舍", "还行"),
        game_state=_game_state(
            season="春",
            date="春 3 日",
            weather="小雨",
            time=1000,
            location="鸡舍",
            friendshipHearts=2,
        ),
        story_progress="刚认识：在鸡舍门口进行第一次当面寒暄",
    ),
    CharacterQualityCase(
        case_id="shane-remote-care",
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="remote",
        message="你今天有没有好好休息？",
        expected_terms=("休息", "还没"),
        game_state=_game_state(
            season="冬",
            date="冬 12 日",
            weather="阴天",
            time=2200,
            location="手机聊天",
            friendshipHearts=6,
        ),
        story_progress="朋友阶段：鸡舍交接正常，但 Shane 明确表示不想长聊",
    ),
    CharacterQualityCase(
        case_id="shane-follow-up",
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="face_to_face",
        message="那批鸡饲料后来送到了吗？",
        history=({"role": "user", "content": "鸡饲料还没送到。"},),
        expected_terms=("饲料", "到了"),
        game_state=_game_state(
            season="夏",
            date="夏 20 日",
            weather="晴天",
            time=800,
            location="牧场鸡舍",
            friendshipHearts=6,
        ),
        story_progress="鸡饲料延迟尚未解决：当面追问上一轮留下的实际事项",
    ),
    CharacterQualityCase(
        case_id="sebastian-bike",
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="acquaintance",
        channel="remote",
        message="最近还骑摩托车出去吗？",
        expected_terms=("摩托车", "出去"),
        game_state=_game_state(
            season="春",
            date="春 8 日",
            weather="阴天",
            time=1800,
            location="手机聊天",
            friendshipHearts=2,
        ),
        story_progress="刚认识：线上询问摩托车近况，不主动深入私人话题",
    ),
    CharacterQualityCase(
        case_id="sebastian-rain",
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="face_to_face",
        message="下雨天你一般会做什么？",
        expected_terms=("电脑", "房间", "雨"),
        game_state=_game_state(
            season="秋",
            date="秋 16 日",
            weather="下雨",
            time=2100,
            location="房间",
            friendshipHearts=6,
        ),
        story_progress="朋友阶段：雨天留在房间，话题停留在具体日常安排",
    ),
    CharacterQualityCase(
        case_id="sebastian-follow-up",
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="face_to_face",
        message="那段代码后来修好了吗？",
        history=({"role": "user", "content": "你说那段代码还有个 bug。"},),
        expected_terms=("代码", "修"),
        game_state=_game_state(
            season="冬",
            date="冬 7 日",
            weather="下雪",
            time=1930,
            location="房间",
            friendshipHearts=6,
        ),
        story_progress="代码 bug 尚未确认修好：继续上一轮的技术话题",
    ),
    CharacterQualityCase(
        case_id="alex-training",
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="acquaintance",
        channel="face_to_face",
        message="今天训练得怎么样？",
        expected_terms=("训练", "完成"),
        game_state=_game_state(
            season="春",
            date="春 9 日",
            weather="晴天",
            time=1600,
            location="运动场",
            friendshipHearts=2,
        ),
        story_progress="刚认识：第一次在运动场聊今天的训练",
    ),
    CharacterQualityCase(
        case_id="alex-remote-invite",
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="remote",
        message="下次一起练练？",
        expected_terms=("一起", "训练"),
        game_state=_game_state(
            season="夏",
            date="夏 21 日",
            weather="晴天",
            time=1900,
            location="手机聊天",
            friendshipHearts=6,
        ),
        story_progress="朋友阶段：线上发出训练邀约，等待确定下次安排",
    ),
    CharacterQualityCase(
        case_id="alex-follow-up",
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="face_to_face",
        message="你昨天的训练完成了吗？",
        history=({"role": "user", "content": "昨天最后一组很难。"},),
        expected_terms=("训练", "完成"),
        game_state=_game_state(
            season="秋",
            date="秋 3 日",
            weather="有风",
            time=1700,
            location="运动场",
            friendshipHearts=6,
        ),
        story_progress="昨天最后一组训练留下未完成项：当面继续追问进度",
    ),
    CharacterQualityCase(
        case_id="caroline-close-background",
        profile_key="caroline",
        npc_id="Caroline",
        display_name="Caroline",
        source_mods=("vanilla",),
        relationship_stage="close",
        channel="face_to_face",
        message="玛妮最近还好吗？",
        history=(
            {"role": "user", "content": "你上次说起过玛妮和牧场的事。"},
            {"role": "assistant", "content": "嗯，她最近一直在照料动物。"},
        ),
        expected_terms=("玛妮", "牧场"),
        game_state=_game_state(
            season="春",
            date="春 24 日",
            weather="晴天",
            time=1500,
            location="杂货店",
            friendshipHearts=10,
            relationship="未婚",
        ),
        story_progress="亲近阶段：玩家已经听 Caroline 提过茶园和 Marnie，正在当面继续聊镇上熟人。",
    ),
    CharacterQualityCase(
        case_id="sebastian-married-life",
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="married",
        channel="face_to_face",
        message="今晚房间里还要留点安静时间吗？",
        history=(
            {"role": "user", "content": "我今晚想先把厨房收拾好。"},
        ),
        expected_terms=("安静", "房间"),
        forbidden_terms=("永远", "命中注定"),
        game_state=_game_state(
            season="冬",
            date="冬 18 日",
            weather="下雪",
            time=1930,
            location="农舍",
            friendshipHearts=14,
            marriageStatus="married",
        ),
        story_progress="已婚阶段：共同生活安排已经确认，讨论今晚如何兼顾家务和独处时间。",
    ),
    CharacterQualityCase(
        case_id="wizard-close-background",
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="close",
        channel="face_to_face",
        message="你为什么一直住在这座塔里？",
        expected_terms=("塔", "住"),
        forbidden_terms=("命中注定", "预言"),
        game_state=_game_state(
            season="冬",
            date="冬 9 日",
            weather="下雪",
            time=1930,
            location="法师塔",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：玩家已经建立信任，开始询问 Rasmodia 的生活选择；她可以分享塔内生活，但不应凭空补写未确认的过去。",
    ),
    CharacterQualityCase(
        case_id="sophia-close-background",
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="close",
        channel="face_to_face",
        message="你还想一直留在葡萄园吗，还是有别的打算？",
        expected_terms=("葡萄园", "打算"),
        game_state=_game_state(
            season="秋",
            date="秋 20 日",
            weather="晴天",
            time=1600,
            location="葡萄园",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：玩家已经知道 Sophia 喜欢葡萄园和绘画，开始聊她对未来的想法；不能替她决定离开或留下。",
    ),
    CharacterQualityCase(
        case_id="shane-close-boundary",
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="close",
        channel="face_to_face",
        message="你最近是不是又睡不好？",
        expected_terms=("睡", "问"),
        game_state=_game_state(
            season="冬",
            date="冬 16 日",
            weather="阴天",
            time=2100,
            location="牧场厨房",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：Shane 承认状态不佳，但被连续追问时会明确要求空间；测试他能否冷淡收束，而不是突然变成温柔长篇。",
    ),
    CharacterQualityCase(
        case_id="alex-close-background",
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="close",
        channel="face_to_face",
        message="你还想去当职业球员吗？",
        expected_terms=("职业", "球员"),
        game_state=_game_state(
            season="夏",
            date="夏 10 日",
            weather="晴天",
            time=1800,
            location="海滩",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：玩家已经知道 Alex 的职业目标，也见过他嘴硬的一面；允许谈梦想和担心，但不能把每句变成励志演讲。",
    ),
    CharacterQualityCase(
        case_id="marnie-friend-family",
        profile_key="marnie",
        npc_id="Marnie",
        display_name="Marnie",
        source_mods=("vanilla",),
        relationship_stage="close",
        channel="face_to_face",
        message="Shane 最近还好吗？",
        expected_terms=("Shane", "最近"),
        game_state=_game_state(
            season="春",
            date="春 18 日",
            weather="晴天",
            time=1100,
            location="玛妮的牧场",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：玩家与 Marnie 熟悉，知道她照料牧场和家人；可以谈 Shane 的近况，但不能替 Shane 透露未说过的隐私。",
    ),
    CharacterQualityCase(
        case_id="linus-friend-nature",
        profile_key="linus",
        npc_id="Linus",
        display_name="Linus",
        source_mods=("vanilla",),
        relationship_stage="close",
        channel="face_to_face",
        message="你住在山上的帐篷里，冬天会不会太冷？",
        expected_terms=("帐篷", "冷"),
        game_state=_game_state(
            season="冬",
            date="冬 4 日",
            weather="下雪",
            time=1700,
            location="煤矿森林",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：玩家尊重 Linus 的生活方式，开始关心冬季生活；回答应保留他的独立和对自然的熟悉，不把他写成等待被拯救的人。",
    ),
)


_FOLLOW_UP_TURNS: dict[str, tuple[CharacterQualityTurn, CharacterQualityTurn]] = {
    "wizard-daily": (
        CharacterQualityTurn(
            "turn-2",
            "这段时间是在塔里忙，还是也会出去走走？",
            ("塔", "忙"),
            ("星界", "奥术", "元素", "预言"),
            "看她是否在初识阶段保持简短克制，并继续回答法师塔的日常。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "等你有空了，我再来找你聊聊，可以吗？",
            ("有空", "聊"),
            ("星界", "奥术", "元素", "预言"),
            "看线上收尾是否自然，不凭空升级成神秘事件或亲密承诺。",
        ),
    ),
    "wizard-follow-up": (
        CharacterQualityTurn(
            "turn-2",
            "那第二组要从哪一步开始重测？",
            ("第二组", "重测"),
            ("星界", "预言"),
            "看她是否承接第三组异常，并把工作话题推进到下一步。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "我把记录留在桌上，你看完告诉我结论。",
            ("记录", "结论"),
            ("星界", "预言"),
            "看她是否对具体记录作出可执行的回应，而不是泛泛总结。",
        ),
    ),
    "wizard-remote-invite": (
        CharacterQualityTurn(
            "turn-2",
            "周末下午方便吗？",
            ("周末", "方便", "时间"),
            ("神秘仪式", "预言"),
            "看线上邀约是否先确认时间，不把聊天写成已经见面。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "那周日下午在法师塔见面，你觉得合适吗？",
            ("周日", "见面"),
            ("神秘仪式", "预言"),
            "看邀约能否自然推进到待确认的当面安排，并保留线上边界。",
        ),
    ),
    "sophia-daily": (
        CharacterQualityTurn(
            "turn-2",
            "东边那排藤架还要多久能收？",
            ("藤架", "收"),
            (),
            "看她是否具体回答葡萄园的工作，不每轮重复同一句新藤抽芽。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "忙完记得喝口水，别一直站着。",
            ("喝", "水"),
            (),
            "看她是否自然接住关心并保持熟悉阶段的分寸。",
        ),
    ),
    "sophia-vineyard": (
        CharacterQualityTurn(
            "turn-2",
            "先看哪一筐？颜色深的还是刚摘的？",
            ("哪一筐", "刚摘"),
            (),
            "看她是否把邀约落到眼前的葡萄，而不是机械回扣藤架。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "要是味道不错，晚上给你留一杯。",
            ("味道", "留"),
            (),
            "看当面话题是否有轻松的朋友式收尾。",
        ),
    ),
    "sophia-face-follow-up": (
        CharacterQualityTurn(
            "turn-2",
            "酸味是不是比上一批更明显？",
            ("酸味", "上一批"),
            (),
            "看她是否承接品尝结果，给出具体感受而非只说葡萄园。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "我再尝一小口，帮你记下感觉。",
            ("尝", "记"),
            (),
            "看她是否让品酒话题继续推进，并保留自然的当面动作。",
        ),
    ),
    "shane-coop": (
        CharacterQualityTurn(
            "turn-2",
            "鸡都还好吗？",
            ("鸡", "还好"),
            (),
            "看初识阶段是否保持冷淡短答，不主动展开长谈。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "好，那我不耽误你干活了。",
            ("不耽误", "干活"),
            (),
            "看他是否允许对话自然结束，而不是强行制造新话题。",
        ),
    ),
    "shane-remote-care": (
        CharacterQualityTurn(
            "turn-2",
            "那你先睡一会儿，鸡舍我明天再问。",
            ("睡", "明天"),
            (),
            "看朋友阶段的关心是否简短直接，不把远程聊天写成长篇安慰。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "行，别勉强自己，晚点再聊。",
            ("别", "聊"),
            (),
            "看他是否接受关心并保留随时结束对话的边界。",
        ),
    ),
    "shane-follow-up": (
        CharacterQualityTurn(
            "turn-2",
            "还没到的话，今天要不要我帮你问一声？",
            ("饲料", "帮"),
            (),
            "看他是否承接饲料延迟，并对实际问题给出短促回应。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "行，到了跟我说一声。",
            ("到了", "说"),
            (),
            "看对话是否以明确事项收尾，不额外制造情绪戏。",
        ),
    ),
    "sebastian-bike": (
        CharacterQualityTurn(
            "turn-2",
            "最近有没有找到适合骑出去的路？",
            ("骑", "路"),
            (),
            "看他是否在初识阶段谈具体路线，同时保持私人边界。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "下次别骑太晚，镇外黑得快。",
            ("骑", "太晚"),
            (),
            "看他是否接住安全提醒，用简短实际的方式继续聊天。",
        ),
    ),
    "sebastian-rain": (
        CharacterQualityTurn(
            "turn-2",
            "你写代码的时候会听音乐吗？",
            ("代码", "音乐"),
            (),
            "看雨天室内话题是否从电脑自然展开，而不是回扣天气本身。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "要不要一起去看场电影？",
            ("一起", "电影"),
            (),
            "看朋友阶段的当面邀约是否克制自然。",
        ),
    ),
    "sebastian-follow-up": (
        CharacterQualityTurn(
            "turn-2",
            "是逻辑问题还是接口没接好？",
            ("逻辑", "接口"),
            (),
            "看他是否承接具体 bug，并以技术细节推进话题。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "卡住了就先放一放，别熬太晚。",
            ("熬", "太晚"),
            (),
            "看他是否接受实际关心，不把普通提醒写成戏剧化表白。",
        ),
    ),
    "alex-training": (
        CharacterQualityTurn(
            "turn-2",
            "今天练的是力量还是速度？",
            ("力量", "速度"),
            (),
            "看初识阶段是否继续聊训练细节，保持外向但不过度自夸。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "下次我给你计时，看你能不能再快点。",
            ("计时", "快"),
            (),
            "看他是否把话题推进到具体行动，而不是书面化鼓励。",
        ),
    ),
    "alex-remote-invite": (
        CharacterQualityTurn(
            "turn-2",
            "那就找个你不忙的下午？",
            ("下午", "不忙"),
            (),
            "看线上邀约是否先协商时间，不提前写成已经碰面。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "地点你定，先说好别临时放我鸽子。",
            ("地点", "鸽子"),
            (),
            "看他是否以轻松直接的方式确定邀约边界。",
        ),
    ),
    "alex-follow-up": (
        CharacterQualityTurn(
            "turn-2",
            "现在做完了吗，还是只差最后一组？",
            ("最后一组", "做完"),
            (),
            "看他是否承接昨天训练的具体难点，不泛泛谈努力。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "不错，明天还练，我陪你跑一段。",
            ("明天", "陪"),
            (),
            "看朋友阶段的鼓励是否落到具体行动并保持自然口语。",
        ),
    ),
    "caroline-close-background": (
        CharacterQualityTurn(
            "turn-2",
            "茶园这几天还好吗？",
            ("茶园", "这几天"),
            (),
            "看亲近阶段是否能从 Marnie 自然谈到 Caroline 自己的花园和茶园，而不是只复述关系资料。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "下次我带点茶来，我们慢慢聊。",
            ("茶", "聊"),
            (),
            "看背景话题能否落到具体的日常邀约，并保持当面语境。",
        ),
    ),
    "sebastian-married-life": (
        CharacterQualityTurn(
            "turn-2",
            "厨房我来收尾，你去把电脑关了？",
            ("厨房", "电脑"),
            (),
            "看已婚阶段是否承接家务和房间安排，表达亲近但仍然简短。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "好，收拾完我们各待一会儿，想聊了再叫我。",
            ("收拾", "聊"),
            (),
            "看高好感关系中的边界和独处是否具体、平等，而不是泛泛表白。",
        ),
    ),
    "wizard-close-background": (
        CharacterQualityTurn(
            "turn-2",
            "你在这里住得习惯吗？",
            ("住", "习惯"),
            ("命中注定", "预言"),
            "看亲近阶段是否从背景问题落回塔内生活，不用神秘话术代替回答。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "如果你不想说，就先算了。",
            ("不想", "算了"),
            ("命中注定", "预言"),
            "看她能否接受玩家给出的边界，不把亲近误写成必须坦白。",
        ),
    ),
    "sophia-close-background": (
        CharacterQualityTurn(
            "turn-2",
            "你画画的时候也会想这些吗？",
            ("画", "想"),
            (),
            "看她能否把未来话题自然连接到绘画，而不是每句都回到藤架或新酒。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "那下次把新画带给我看看？",
            ("下次", "画"),
            (),
            "看亲近阶段的邀约是否轻柔具体，并保留由 Sophia 决定是否分享的空间。",
        ),
    ),
    "shane-close-boundary": (
        CharacterQualityTurn(
            "turn-2",
            "好，那我不问了，你想说的时候再说。",
            ("不问", "说"),
            (),
            "看 Shane 是否在被尊重后仍保持短促、略带防备的说话方式。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "那我去看看鸡了，你先歇着。",
            ("鸡", "歇"),
            (),
            "看他能否用具体行动结束一轮艰难对话，不继续制造情绪独白。",
        ),
    ),
    "alex-close-background": (
        CharacterQualityTurn(
            "turn-2",
            "你现在最担心的是什么？",
            ("担心", "目标"),
            (),
            "看亲近阶段是否承认目标之外的顾虑，但仍保持 Alex 直接、不绕弯的口吻。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "先不聊这个了，我们去海滩走走？",
            ("海滩", "走"),
            (),
            "看他能否把脆弱话题落回普通的共同活动，而不是继续励志说教。",
        ),
    ),
    "marnie-friend-family": (
        CharacterQualityTurn(
            "turn-2",
            "你打算什么时候把新草料送到牧场？",
            ("草料", "牧场"),
            (),
            "看 Marnie 是否从 Shane 的近况回到自己照料牧场的具体日常。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "Jas 今天也在吗？",
            ("Jas", "今天"),
            (),
            "看她能否自然提到家人，同时不把 Shane 的隐私扩写成剧情。",
        ),
    ),
    "linus-friend-nature": (
        CharacterQualityTurn(
            "turn-2",
            "你今天在山里找到什么了？",
            ("山", "找到"),
            (),
            "看 Linus 是否从居住条件自然转到采集和观察，而不是接受被救助的叙事。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "如果你愿意，我可以带些木柴过来。",
            ("木柴", "愿意"),
            (),
            "看他能否接受或婉拒具体帮助，保留独立和礼貌的边界。",
        ),
    ),
}


def _materialize_quality_turns(case: CharacterQualityCase) -> CharacterQualityCase:
    first_turn = CharacterQualityTurn(
        "turn-1",
        case.message,
        case.expected_terms,
        case.forbidden_terms,
        "检查第一轮是否自然回应当前场景、渠道和话题。",
    )
    follow_ups = _FOLLOW_UP_TURNS.get(case.case_id, ())
    if len(follow_ups) != 2:
        raise ValueError(f"角色质量案例缺少两轮续聊：{case.case_id}")
    return replace(case, turns=(first_turn, *follow_ups))


DEFAULT_CASES: tuple[CharacterQualityCase, ...] = tuple(
    _materialize_quality_turns(case) for case in _BASE_CASES
)


_CASES_BY_ID = {case.case_id: case for case in DEFAULT_CASES}


def case_by_id(case_id: str) -> CharacterQualityCase:
    try:
        return _CASES_BY_ID[case_id]
    except KeyError as exc:
        raise KeyError(f"未知角色质量场景：{case_id}") from exc


def quality_case_catalog() -> list[dict[str, object]]:
    """返回给测试浏览器使用的脱敏质量案例目录。"""

    catalog: list[dict[str, object]] = []
    for case in DEFAULT_CASES:
        turns = case.dialogue_turns()
        category = (
            "上下文续聊"
            if case.history
            else "远程渠道"
            if case.channel == "remote"
            else "日常状态"
        )
        catalog.append(
            {
                "caseId": case.case_id,
                "profileKey": case.profile_key,
                "npcId": case.npc_id,
                "displayName": case.display_name,
                "sourceMods": list(case.source_mods),
                "relationshipStage": case.relationship_stage,
                "channel": case.channel,
                "category": category,
                "playerInput": case.message,
                "turnCount": len(turns),
                "turns": [
                    {
                        "turnId": turn.turn_id,
                        "playerInput": turn.message,
                        "expectedTerms": list(turn.expected_terms),
                        "forbiddenTerms": list(turn.forbidden_terms),
                        "evaluationFocus": turn.evaluation_focus,
                    }
                    for turn in turns
                ],
                "history": [dict(item) for item in case.history],
                "expectedTerms": list(case.expected_terms),
                "forbiddenTerms": list(case.forbidden_terms),
                "gameState": dict(case.game_state),
                "storyProgress": case.story_progress,
            }
        )
    return catalog


_FORMAL_MARKERS = (
    "综合来看",
    "总体而言",
    "具有重要意义",
    "建议持续关注",
    "后续发展",
    "综上所述",
)
_GENERIC_MARKERS = (
    "此事",
    "这件事具有",
    "建议持续关注",
    "后续发展",
    "值得重视",
    "总体而言",
)
_REMOTE_ONLY_MARKERS = ("我现在就在你面前", "到我这里来", "当面再说")
_FACE_TO_FACE_MARKERS = ("发消息给我", "线上再聊", "下次视频")

_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "训练": ("训练", "锻炼", "练完", "练了", "练", "健身", "跑步", "跑完", "五公里", "配速", "动作"),
    "完成": ("完成", "做完", "练完", "结束", "搞定"),
    "鸡舍": ("鸡舍", "鸡棚", "鸡窝", "食槽", "窝"),
    "还行": ("还行", "还好", "凑合", "没事", "一般", "不算太忙", "不太忙"),
    "还": ("还", "还好", "还行", "凑合", "顺利", "平稳", "没乱"),
    "事做": ("事做", "事情", "工作", "活", "记录"),
    "饲料": ("饲料", "鸡食", "鸡粮", "粮食"),
    "到了": ("到了", "送到", "送来了", "已经到"),
    "摩托车": ("摩托车", "机车", "车"),
    "出去": ("出去", "出门", "骑出去"),
    "电脑": ("电脑", "笔记本"),
    "房间": ("房间", "屋里", "房里"),
    "雨": ("雨", "下雨", "雨天"),
    "代码": ("代码", "程序", "bug", "漏洞"),
    "修": ("修", "修好", "改好", "解决"),
    "休息": ("休息", "歇", "睡", "放松", "躺床上", "躺着"),
    "还没": ("还没", "没有", "没来得及"),
    "葡萄": ("葡萄", "葡萄园", "葡萄藤", "藤架", "收成"),
    "酒": ("酒", "葡萄酒", "酒味"),
    "一起": ("一起", "一块", "一同"),
    "忙": ("忙", "忙碌", "有空", "闲"),
    "第三组": ("第三组", "第三批", "那组"),
    "重测": ("重测", "再测", "重新测", "复测"),
    "时间": ("时间", "哪天", "什么时候", "改天"),
    "核对": ("核对", "对一下", "检查一下", "看一下"),
    "可以": ("可以", "行", "好", "没问题"),
}


def _term_variants(term: str) -> tuple[str, ...]:
    return _TERM_ALIASES.get(term, (term,))


def _term_matches(term: str, text: str) -> tuple[str, ...]:
    return tuple(variant for variant in _term_variants(term) if variant.casefold() in text.casefold())


def _history_continues(
    case: CharacterQualityCase,
    text: str,
    *,
    history: tuple[dict[str, str], ...] | list[dict[str, str]] | None = None,
    expected_terms: tuple[str, ...] | None = None,
) -> bool:
    lowered = text.casefold()
    active_history = case.history if history is None else history
    active_expected_terms = (
        case.expected_terms if expected_terms is None else expected_terms
    )
    history_text = " ".join(
        item.get("content", "")
        for item in active_history
        if isinstance(item.get("content"), str)
    ).casefold()
    if not history_text:
        return True

    # 续聊必须带回“对象”本身，不能只命中“送到了/还没”等泛化进展词。
    # 评测用例把第一个 expected term 作为当前话题对象，后面的词通常是状态或动作。
    anchor_terms = active_expected_terms[:1]
    history_anchors = {
        term
        for term in anchor_terms
        if len(term.strip()) >= 1
        and any(alias.casefold() in history_text for alias in _term_variants(term))
    }
    if history_anchors:
        return any(
            any(alias.casefold() in lowered for alias in _term_variants(term))
            for term in history_anchors
        )
    for item in active_history:
        content = item.get("content", "").strip()
        if not content:
            continue
        if content.casefold() in lowered:
            return True
        meaningful = [
            content[index : index + size]
            for size in (4, 3, 2)
            for index in range(max(0, len(content) - size + 1))
        ]
        if any(token.casefold() in lowered for token in meaningful):
            return True
    return False


def score_character_reply(
    case: CharacterQualityCase,
    reply: str,
    *,
    turn: CharacterQualityTurn | None = None,
    history: tuple[dict[str, str], ...] | list[dict[str, str]] | None = None,
) -> dict[str, object]:
    text = reply.strip()
    lowered = text.casefold()
    expected_terms = turn.expected_terms if turn is not None else case.expected_terms
    forbidden_terms = turn.forbidden_terms if turn is not None else case.forbidden_terms
    evidence_matches = {
        term: list(_term_matches(term, text))
        for term in expected_terms
        if _term_matches(term, text)
    }
    expected_hits = len(evidence_matches)
    exact_expected_hits = sum(
        1 for term in expected_terms if term.casefold() in lowered
    )
    forbidden_hits = sum(
        1 for term in forbidden_terms if term.casefold() in lowered
    )
    tags: set[str] = set()
    if not text:
        tags.add("empty_reply")
    if len(text) > 120 or any(marker in text for marker in _FORMAL_MARKERS):
        tags.add("too_formal")
    if any(marker in text for marker in _GENERIC_MARKERS):
        tags.add("generic_voice")
    if forbidden_hits:
        tags.add("invented_lore")
    if expected_terms and expected_hits == 0:
        tags.add("missing_expected_evidence")
    active_history = case.history if history is None else history
    continuity = _history_continues(
        case,
        text,
        history=active_history,
        expected_terms=expected_terms,
    )
    if active_history and not continuity:
        tags.add("missing_continuity_evidence")
    if case.channel == "remote" and any(
        marker in text for marker in _REMOTE_ONLY_MARKERS
    ):
        tags.add("wrong_channel")
    if case.channel == "face_to_face" and any(
        marker in text for marker in _FACE_TO_FACE_MARKERS
    ):
        tags.add("wrong_channel")

    return {
        "expectedHits": expected_hits,
        "exactExpectedHits": exact_expected_hits,
        "topicEvidence": bool(evidence_matches),
        "evidenceMatches": evidence_matches,
        "forbiddenHits": forbidden_hits,
        "continuity": continuity,
        "replyLength": len(text),
        "tags": tags,
        "passed": bool(text)
        and forbidden_hits == 0
        and "missing_expected_evidence" not in tags
        and "missing_continuity_evidence" not in tags,
    }
