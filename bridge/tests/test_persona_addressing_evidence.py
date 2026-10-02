# -*- coding: utf-8 -*-
"""`addressing.player` 的逐条实证与"不许再混英文"的回归闸（2026-09-24）。

背景（`docs/report-overnight-dialogue-2026-09-23.md` §5.1）：
`9388765` 一次性给 30+ 角色批量写入 `addressing.player`，大多数填模板值「朋友」、
SVE 的 5 个填「农场主」，**没有逐角色核对原话**；同时 9 个条目留着英文
`"you"`、Wizard 留着 `"traveler"`。

本文件钉两件事：

1. **全库不许再出现英文值** —— 这是 `you` / `traveler` 那批问题的通用闸：
   一次遍历就能抓住，不依赖某几个角色被点名。
2. **本轮按原话改过的 6 条**逐条钉住，并在 evidence 里写清出处，
   避免下次批量覆盖时又被模板值冲掉。

口径（用户原话）：「主要是要自然一点，像真实对话，也要像这个人该说的话」——
所以这个字段写的是**角色对玩家的日常对白里真实出现的称呼方式**，
不是"关系定位"。

⚠ 边界（如实记录）：**「朋友」到底是称呼词还是关系定位，全库没有权威定义**，
两种读法都留给用户拍板；因此本文件**只**钉本轮有直接原话实证的那几条 +
英文残留这条硬 bug，不钉其余 17 条「朋友」与 Claire / Victor 的「农场主」。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PERSONA_DIR = ROOT / "data" / "personas"

# 允许的非中文字符（值里会用到中文引号「」与全角标点，不含 ASCII 字母）
_ASCII_LETTER = re.compile(r"[A-Za-z]")


def _profiles(path: Path) -> list[tuple[str, dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    personas = data.get("personas") if isinstance(data, dict) else None
    if not isinstance(personas, dict):
        return []
    return [(key, value) for key, value in personas.items() if isinstance(value, dict)]


def _iter_addressing_player():
    """遍历全库每个角色的 `addressing.player`（缺失的跳过）。"""

    for path in sorted(PERSONA_DIR.glob("*.json")):
        for npc, profile in _profiles(path):
            addressing = profile.get("addressing")
            if not isinstance(addressing, dict):
                continue
            player = addressing.get("player")
            if isinstance(player, str) and player:
                yield path.name, npc, player


def test_no_persona_file_sends_an_english_addressing_value() -> None:
    """通用闸：`addressing.player` 不许再混英文（`you` / `traveler` 那批）。

    这条是"防止再被批量覆盖"的主力 —— 它不依赖角色名单，
    任何一次批量写入只要带进英文字母就会红。
    """

    offenders = [
        f"{filename}:{npc} = {player!r}"
        for filename, npc, player in _iter_addressing_player()
        if _ASCII_LETTER.search(player)
    ]

    assert offenders == []


def test_every_persona_with_dialogue_evidence_has_a_player_address() -> None:
    """抽查守卫：本轮补过字段的两个角色不许再退回"字段缺失"。

    `Sophia` 的唯一来源是 `sve.json`（vanilla 没有她），缺了就是运行时空值。
    """

    sve = PERSONA_DIR / "sve.json"
    profiles = {npc: profile for npc, profile in _profiles(sve)}

    assert profiles["Sophia"]["addressing"]["player"] == "你"


# --- 本轮按原话改过的 6 条 + 2 条英文残留 -------------------------------------
#
# evidence 写的是**出处**，不是解释：下次有人要改这些值，先看那一行原话再说。

ADDRESSING_CASES = (
    (
        "sve.json",
        "Olivia",
        "亲爱的",
        "Olivia/Dialogue.json/Introduction「亲爱的，欢迎来到星露谷」；"
        "全库 211 处，非婚后（Introduction / Gift* / Phone / funLeave 都有）。",
    ),
    (
        "vanilla.json",
        "Sandy",
        "甜心",
        "Sandy.zh-CN.json/Mon「哈喽，甜心！」（Fri、Sun8 同）；"
        "「亲爱的」只在 AcceptGift_(O)StardropTea 出现 1 处。",
    ),
    (
        "sve.json",
        "Lance",
        "亲爱的",
        "Lance.CharacterDialogue.032「你好，亲爱的。你今天有探险家公会的事要处理吧？」；"
        "全库 22 处（另见 CharacterDialogue.008）。",
    ),
    (
        "vanilla.json",
        "Wizard",
        "年轻人",
        "Wizard.zh-CN.json/Introduction「我很久前就预见到你的到来了，年轻的@。」"
        "与 Mon 同款；原值 \"traveler\" 是英文残留且无原话依据。",
    ),
)


@pytest.mark.parametrize(
    ("filename", "npc", "expected", "evidence"),
    ADDRESSING_CASES,
    ids=lambda item: item if isinstance(item, str) and len(item) < 20 else "",
)
def test_addressing_matches_the_characters_own_lines(
    filename: str,
    npc: str,
    expected: str,
    evidence: str,
) -> None:
    """有直接原话实证的几条：值必须等于原话里的称呼（出处见 evidence）。"""

    profiles = {key: value for key, value in _profiles(PERSONA_DIR / filename)}

    assert profiles[npc]["addressing"]["player"] == expected, evidence


# 性别相关的那几条单独钉：它们**不能**写成单一字面，见下方说明。
GENDER_DEPENDENT = (
    (
        "vanilla.json",
        "Willy",
        "小伙子",
        "小姑娘",
        "年轻人",
        "Willy.zh-CN.json/Mon「你好啊，孩子。^你好啊，小姑娘。」（^ 是原版的性别分支）；"
        "summer_19 / fishCaught_163 / fishCaught_682 / accept_869 / MovieInvitation "
        "都是「小伙子^小姑娘」；Introduction「看到有年轻人搬进谷里」是中性说法。",
    ),
    (
        "vanilla.json",
        "George",
        "小伙子",
        "小姐",
        "年轻人",
        "George.zh-CN.json/Thu「我现在没空聊天，小伙子。^我现在没空聊天，小姐。」；"
        "「年轻人」6 处且性别中性（GreenRain_2 / Wed10 / winter_1 等）。",
    ),
    (
        "sve.json",
        "Morris",
        "先生",
        "小姐",
        "农场主",
        "ExtraDialogue.zh-CN.json 的键名自己就分了性别："
        "Morris_CommunityDevelopmentForm_PlayerMale「先生，我为您拿到了…」／"
        "_PlayerFemale「小姐，我为您拿到了…」；SVE Morris.4hearts.15「好的，先生……」、"
        "Morris.2hearts.01「你好，女士！」；中性兜底取自他的 Introduction「啊，是农场主@呀」。",
    ),
    (
        "vanilla.json",
        "Vincent",
        "先生",
        "女士",
        "你",
        "Vincent.zh-CN.json/Sun（stranger）「你好啊，先生！」；Tue6（friend）"
        "「你能为我保守个秘密吗，先生？^…女士？」（`^` 是原版的性别分支）；"
        "中性兜底用他自己的「你」。",
    ),
    (
        "vanilla.json",
        "Jas",
        "先生",
        "小姐",
        "你",
        "Jas.zh-CN.json/Mon4（acquaintance）「嗨，@先生。」与 Sat8（close）"
        "「你总是这么好，@先生。」；原版把玩家名写成 `@`，去掉名字后留下的正是「先生」；"
        "中性兜底用她自己的「你」。",
    ),
    (
        "vanilla.json",
        "Marnie",
        "先生",
        "小姐",
        "你",
        "Marnie.zh-CN.json/Mon（stranger）「我爱动物，@先生。」；"
        "全库搜「亲爱的」在她**本人文件里 0 处** ⇒ 原值没有依据；"
        "中性兜底用她自己的「你」。",
    ),
)


@pytest.mark.parametrize(
    ("filename", "npc", "male", "female", "neutral", "evidence"),
    GENDER_DEPENDENT,
    ids=lambda item: item if isinstance(item, str) and len(item) < 20 else "",
)
def test_gender_dependent_addressing_states_the_condition_and_a_neutral_fallback(
    filename: str,
    npc: str,
    male: str,
    female: str,
    neutral: str,
    evidence: str,
) -> None:
    """称呼随玩家性别变化的 6 个角色：值里必须**写明条件**并给中性兜底。

    为什么不写成「小伙子/小姑娘」这种裸并列：
    prompt 里**没有玩家性别事实**（`_STATE_FIELDS` 无 `gender`，SMAPI 也只发 NPC 的
    `gender`，从不读 `Game1.player`），裸并列对模型就是一个"二选一但没有依据"的
    提示，它只能随机挑或原样打印斜杠。写明条件 + 给一个角色自己用过的中性说法
    （「年轻人」／「农场主」），模型至少知道这是性别分支，不确定时可以避开称呼 ——
    真实对话里本来也不必每句都带称呼。

    真正的根治是让 SMAPI 把 `Game1.player.IsMale` 一起发过来，那超出本轮改动面
    （`data/personas/*.json` + 测试），已作为建议上报。
    """

    profiles = {key: value for key, value in _profiles(PERSONA_DIR / filename)}
    value = profiles[npc]["addressing"]["player"]

    assert "性别" in value, f"{npc} 没写明性别条件：{value!r}"
    for form in (male, female, neutral):
        assert form in value, f"{npc} 缺 {form}：{value!r}（依据：{evidence}）"


# --- 玩家性别通道（2026-09-24）--------------------------------------------------
#
# 上面那几条钉的是「**写法**里写明了性别条件」。但条件要能兑现，还缺**依据** ——
# 而这正是本轮的发现：`gameState.gender` 是 **NPC 的**性别
# （`GameStateCollector.cs` 读的是 `npc.Gender`），**玩家性别从来没进过请求**，
# 所以 Willy / George / Morris 三条**恒落「不确定」分支**，实际只输出「年轻人／农场主」
# —— 而那不是这三人的原话。
#
# 2026-09-24 补上 `playerGender` 通道（C# DTO → Bridge 模型 → `mod_overlay` 卡，
# **紧挨 `addressing`**，值映射成写法里逐字相同的「男 / 女」）。
#
# 这里钉两组必须同时成立的事：
#   · **发性别时条件能兑现**（男→男、女→女，含大小写容错）；
#   · **不发时不许猜**（不给这个键，模型落「不确定」那一支）。


def _mod_overlay_card(npc: str, mods: list[str], player_gender: object) -> dict:
    """走线上同一条紧凑路径，取 `mod_overlay` 卡（`addressing` 就在这张卡里）。"""

    from stardew_ai_bridge.app import _build_context

    state: dict[str, object] = {
        "npcId": npc,
        "displayName": npc,
        "gender": "Male",
        "location": "Town",
        "season": "spring",
        "date": "5",
        "weather": "clear",
        "time": 900,
        "friendship": 100,
        "friendshipHearts": 0,
        "relationship": "stranger",
    }
    if player_gender is not None:
        state["playerGender"] = player_gender
    payload = {
        "npcId": npc,
        "displayName": npc,
        "message": "你好，我想学钓鱼。",
        "intent": "chat",
        "provider": "fake",
        "compactPrompt": True,
        "channel": "face_to_face",
        "sourceMods": mods,
        "recentFacts": [],
        "history": [],
        "gameState": state,
    }
    context, prompt = _build_context(payload, compact_prompt=True)
    assert context.get("_runtime_compact") is True
    card = next(item for item in prompt if item.get("name") == "mod_overlay")
    return json.loads(card["content"])


@pytest.mark.parametrize(
    ("npc", "mods", "player_gender", "expected"),
    [
        ("Willy", ["vanilla"], "Male", "男"),
        ("Willy", ["vanilla"], "Female", "女"),
        # 大小写容错：C# 发的是 `Male`/`Female`，但别指望永远是那个大小写。
        ("Morris", ["SVE", "vanilla"], "female", "女"),
        # 认不出的值**不发**这个键 —— 给了错的性别比不给更糟。
        ("Willy", ["vanilla"], "Unknown", None),
        # 不发（旧 DLL）= 与加这个字段之前完全一致。
        ("Willy", ["vanilla"], None, None),
    ],
)
def test_player_gender_reaches_the_addressing_card(
    npc: str, mods: list[str], player_gender: object, expected: str | None
) -> None:
    overlay = _mod_overlay_card(npc, mods, player_gender)

    assert "addressing" in overlay, "addressing 必须与 playerGender 同卡"
    assert overlay.get("playerGender") == expected


def test_the_gender_value_matches_the_addressing_wording() -> None:
    """卡里发出去的中文必须与写法里那两个字**逐字相同**，否则模型对不上。"""

    overlay = _mod_overlay_card("Willy", ["vanilla"], "Male")
    wording = overlay["addressing"]["player"]

    assert "性别" in wording
    assert f"男「小伙子」" in wording
    assert f"{overlay['playerGender']}「小伙子」" in wording
