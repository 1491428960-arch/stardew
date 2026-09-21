"""判定词表扩容（2026-09-23）的回归。

起因是素材缺口审计（`.tmp/facet-coverage/REPORT.md`）：180 条去重后的
`preferredTopics` 里 **69 条（38%）判不出任何生活面**，而 `rotation_topic_slot` 的
候选筛选会直接跳过判不出面的条目 —— 它们**永远不会被选成本轮落点**。审计的结论是
"先扩词表"：它是唯一**零素材成本**的动作（素材一条不加，就能救活现有条目）。

本文件钉住三件事：

1. **补进来的 14 个词各自落在正确的面上**，含"「花园」为什么归爱好而不是工作"这条
   归位判据（与 2026-09-21 把运动词从工作面移入爱好面同一条判据）；
2. **5 个真实误判不再发生** —— 3 个是被真实对白逼出来的**收窄**
   （`吃(?![掉亏力惊苦])` / `发明(?![^，。；！？]{0,4}游戏)` / `(?<!什么)风`），
   2 个是漏词（邻居、女儿/儿子）。收窄的两侧都要测：误判不再发生，
   而**同一条正则该管的地方照旧命中**（"吃掉"不算吃喝，"吃披萨"仍然算）；
3. **既有素材的主面不许漂走** —— 尤其是刻意不收单字「酒」这条取舍，
   以及扩容唯一造成的那处漂移（Shane「工作压力」）改用素材字面改写来应对。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from stardew_ai_bridge.stage_policy import (
    _LIFE_FACET_PATTERNS,
    _facet_hits,
    _facet_of_topic,
)

ROOT = Path(__file__).resolve().parents[2]
PERSONAS_DIR = ROOT / "data" / "personas"


# --- 1. 补进来的 14 个词各自落在正确的面上 ------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 工作面：审计里最刺眼的一条 —— 「工作」这两个字本身不在词表里
        ("我在这镇上当了二十多年的镇长，这工作不轻松。", "工作或手艺"),
        ("我的爷爷也是农夫。", "工作或手艺"),
        # 吃喝：酒吧（与「酒馆」同义）、厨房（做饭的场所）、冰淇淋／甜点
        ("我每周都会去一次酒吧。", "吃喝"),
        ("希望你喜欢新的厨房。", "吃喝"),
        ("用自家产牛奶做出来的新鲜牛奶冰淇淋是我的最爱！", "吃喝"),
        ("我最近在琢磨一道新的甜点。", "吃喝"),
        # 镇上或邻里：表里原有「邻里」，真实对白写的是「邻居」
        ("我的一位邻居送来了一篮樱桃。", "镇上或邻里"),
        # 家人朋友：表里只有「孩子」，而 NPC 谈子女是最日常的话
        ("你遇见我的儿子塞巴斯蒂安了吗？", "家人朋友"),
        ("我女儿玛鲁真让人省心。", "家人朋友"),
        # 过去的回忆：「记得那」三连放宽成「记得」
        ("我记得我读到过关于那片农田的新闻。", "过去的回忆"),
        # 爱好或消遣：锻炼（与「运动」同义）、花园、电视、动漫
        ("想要保持健康的话，锻炼必不可少。", "爱好或消遣"),
        ("花园和花朵是我一天里最安静的时候。", "爱好或消遣"),
        ("在这样的日子里，我只想窝在毯子里看电视。", "爱好或消遣"),
        ("终于等到动漫展了！", "爱好或消遣"),
    ],
)
def test_new_words_land_on_their_intended_facet(text: str, expected: str) -> None:
    assert _facet_of_topic(text) == expected, f"{text} 没落到 {expected}"


def test_garden_belongs_to_hobbies_not_work() -> None:
    """「花园」的**归位判据**（与运动词那次同一条）。

    星露谷居民自家院子里的花是**消遣**，营生那一侧已经由「农场／牧场／土地／作物」
    承担。所以"花园"必须只命中爱好面 —— 若有人把它挪回工作面，本条会红。
    """

    hits = _facet_hits("花园和花朵")

    assert hits == {"爱好或消遣"}
    assert "工作或手艺" not in hits


# --- 2. 五个真实误判：三个收窄 + 两个漏词 -------------------------------------


def test_alex_is_not_eaten_as_food_and_drink() -> None:
    """**跨词边界误抓**：Alex「我担心你会被史莱姆**吃掉**」曾判成"吃喝"。

    真话是"担心"（自己的状态或烦恼）；"吃掉"是一个词，与进食无关。
    这一轮的判据是"关心玩家的安危"，不是"吃"。
    """

    text = "我知道你很强壮，但是有时候我担心你会被史莱姆吃掉。"

    hits = _facet_hits(text)

    assert "吃喝" not in hits, "「吃掉」又被当成进食了"
    assert "自己的状态或烦恼" in hits


@pytest.mark.parametrize("text", ["吃亏", "吃力", "吃惊", "吃苦"])
def test_non_eating_chi_compounds_are_not_food_and_drink(text: str) -> None:
    """同一条负向断言的其余成员：这四个搭配在语料里都不是进食。"""

    assert "吃喝" not in _facet_hits(f"这件事让我有点{text}。")


@pytest.mark.parametrize("text", ["我很喜欢吃披萨。", "他吃掉了三块披萨。", "刚吃了早餐。"])
def test_real_eating_still_reads_as_food_and_drink(text: str) -> None:
    """收窄的**另一侧**：真正在吃东西的句子照旧命中（排的是搭配，不是"吃"字）。"""

    assert "吃喝" in _facet_hits(text), text


def test_jas_inventing_a_game_is_play_not_craft() -> None:
    """**跨面误抓**：Jas「所以我得自己**发明**游戏」曾判成"工作或手艺"。

    孩子自己编游戏规则是**玩**，不是手艺。断言只排除"发明…游戏"这一种搭配。
    """

    hits = _facet_hits("谢恩经常不在，玛妮姑妈又很忙……所以我得自己发明游戏。")

    assert "工作或手艺" not in hits, "「发明游戏」又被当成工作了"
    assert "爱好或消遣" in hits


@pytest.mark.parametrize(
    "text",
    ["他发明了新的灌溉系统。", "这个发明改变了整个农场。", "他发明了一种新的计数方法。"],
)
def test_real_invention_still_belongs_to_work(text: str) -> None:
    """收窄的另一侧：与"游戏"无关的"发明"照旧归工作面。"""

    assert "工作或手艺" in _facet_hits(text), text


def test_kent_asking_what_wind_blew_him_in_is_not_weather() -> None:
    """**习语误抓**：Kent「什么**风**把你吹来了」曾判成"天气季节"。

    单字"风"太宽，而"什么风把你吹来了"是习语。断言只排除这一个紧邻搭配。
    """

    hits = _facet_hits("什么风把你吹来了？")

    assert "天气季节" not in hits, "习语又被当成天气了"


@pytest.mark.parametrize("text", ["海风里退潮后的那片沙滩", "今天风不大，适合出海。"])
def test_real_weather_wind_still_matches(text: str) -> None:
    """收窄的另一侧：真正的天气说法照旧命中（"海风"本来就是单独列的一项）。"""

    assert "天气季节" in _facet_hits(text), text


def test_risk_is_not_weather() -> None:
    """**第四处误判**（2026-09-22 第 4 批）：`风` → `(?<!什么)风(?!险)`。

    「**风险**」与天气无关，却是"风"字最常见的搭配之一。它出现在两条**冒险者**
    素材的条目名里 —— Lance「冒险者准则和风险判断」、Marlon「经验和风险判断」——
    两条都被派到"天气季节"：对冒险者来说那既是不存在的一面，又会让换面统计把
    "他刚聊了天气"记上一笔。

    与"什么风"那次同样的取舍：**只排除这一个紧邻搭配**，`风` 后接任何其它字
    （风雨／风车／风口）照旧命中。

    修完之后两条素材各自归位，而归位结果正说明这条收窄是对的：

    * Lance「冒险者准则和**风险**判断」→ 落到"工作或手艺"（"**冒险**"命中）——
      冒险者的准则本来就该在工作面，而不是在一个他根本没有素材的天气面；
    * Marlon「经验和**风险**判断」→ 判不出面（该条没有别的面词）。这也好过派到一个
      假面上：判不出面的条目至少不会被误计成"他刚聊了天气"。
    """

    assert "天气季节" not in _facet_hits("冒险者准则和风险判断")
    assert _facet_of_topic("冒险者准则和风险判断") == "工作或手艺"
    assert _facet_of_topic("经验和风险判断") is None


@pytest.mark.parametrize("text", ["外面风雨很大，别出海。", "风车转得飞快。", "风口那儿最冷。"])
def test_wind_before_other_characters_still_matches(text: str) -> None:
    """收窄的另一侧：「风险」以外的"风"字搭配一条都没跟着走。"""

    assert "天气季节" in _facet_hits(text), text


def test_neighbor_and_children_by_gender_are_no_longer_missing() -> None:
    """两个**漏词**：审批报告里"写了也判不出面"的候选正是被它们卡住的。

    * 「邻居」：表里只有「邻里」，而 Claire 的原话写的是"我的一位邻居"；
    * 「儿子／女儿」：表里只有「孩子」，Robin 的原话"你遇见我的儿子塞巴斯蒂安了吗？"
      因此判不出面，候选表里只好改写成"孩子"——补词之后**不必再改写**。
    """

    assert _facet_of_topic("我的一位邻居送来了一篮樱桃。") == "镇上或邻里"
    assert _facet_of_topic("你遇见我的儿子塞巴斯蒂安了吗？") == "家人朋友"
    assert _facet_of_topic("我女儿玛鲁真让人省心。") == "家人朋友"


# --- 3. 既有素材的主面不许漂走 ------------------------------------------------


def test_the_single_character_jiu_is_still_not_in_any_facet() -> None:
    """**沿用 2026-09-22 的取舍**：单字「酒」仍然不在任何面里。

    它是多义语素（酒馆／酒店／酒保属"吃喝"），而 `_facet_of_topic` 按声明顺序取
    第一个命中 —— 工作面声明在前，收它会把「酒馆里喝一杯」这类素材的主面从"吃喝"
    漂到"工作或手艺"，全部角色的 `narrow_topic_pool` / `suggestedTopic` 跟着变。

    代价（Pierre 的苹果酒、Victor 的葡萄酒永远判不出"吃喝"）已被接受，本轮不翻案，
    也不收「苹果酒」这种"带酒字的整词"。
    """

    assert _facet_of_topic("酒馆里今天人多得很。") == "吃喝"
    assert _facet_of_topic("晚上去酒馆喝一杯吧。") == "吃喝"
    assert _facet_hits("招牌的香料南瓜苹果酒") == set(), "「苹果酒」不该被收进来"
    assert _facet_hits("酒怎么样") == set(), "孤立的「酒」字不该带面语义"


def test_shane_stress_entry_was_rewritten_not_ruled_out() -> None:
    """扩容唯一造成的那处漂移，以及它的处理方式。

    「工作」进词表后，Shane 的「工作压力」主面会从"自己的状态或烦恼"漂到"工作或手艺"
    （工作面声明序在前）。判得不算错，但它让 Shane 的素材覆盖面从 2 面掉到 1 面 ——
    与"素材要够换面"的方向相反。处理方式是**改素材字面**（"忙起来那股压力"），
    而不是给词表加特例：扩容是"让素材可被识别"，不该让**已有**素材失去识别。
    """

    assert _facet_of_topic("工作压力") == "工作或手艺"  # 漂移本身（记录事实）
    assert _facet_of_topic("忙起来那股压力") == "自己的状态或烦恼"
    assert "工作" not in "忙起来那股压力"  # 改写就是把那个词让出去


# --- 4. 被救活的既有素材（审计里"判不出面"的那批） ---------------------------


def _persona_topics() -> dict[str, dict[str, str]]:
    """{canonical_id: {topic: 来源文件}}，多来源取并集。"""

    out: dict[str, dict[str, str]] = {}
    for path in sorted(PERSONAS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, profile in (payload.get("personas") or {}).items():
            voice_style = (profile or {}).get("voiceStyle")
            topics = (
                voice_style.get("preferredTopics") if isinstance(voice_style, dict) else None
            )
            for topic in topics or []:
                out.setdefault(str(name), {})[str(topic)] = path.name
    return out


# 审计报告点名的那 5 条"判不出面"的现有素材：扩容后必须各自落面、且落对。
REVIVED_BY_THE_WIDER_WORDLIST = {
    ("Claire", "工作与日常适应"): "工作或手艺",
    ("Robin", "木匠店的工作"): "工作或手艺",
    ("Wizard", "塔内工作"): "工作或手艺",
    ("Evelyn", "花园和花朵"): "爱好或消遣",
    ("George", "家里和花园的日常"): "爱好或消遣",
}


@pytest.mark.parametrize(
    ("npc_id", "topic", "expected"),
    [(npc, topic, facet) for (npc, topic), facet in REVIVED_BY_THE_WIDER_WORDLIST.items()],
)
def test_existing_material_revived_by_the_wider_wordlist(
    npc_id: str, topic: str, expected: str
) -> None:
    """零素材成本的收益：这 5 条一个字的素材都没加，只是终于判得出面了。"""

    topics = _persona_topics()

    assert npc_id in topics and topic in topics[npc_id], f"{npc_id} 里找不到「{topic}」"
    assert _facet_of_topic(topic) == expected


def test_wordlist_still_declares_nine_facets_in_the_same_order() -> None:
    """面名与**声明顺序**是"哪一面优先"的唯一配置，扩容不许动它。

    `_facet_of_topic` 取第一个命中面，所以顺序一变，全部角色的主面映射跟着变。
    """

    assert [name for name, _ in _LIFE_FACET_PATTERNS] == [
        "工作或手艺",
        "吃喝",
        "天气季节",
        "镇上或邻里",
        "家人朋友",
        "玩家自己",
        "自己的状态或烦恼",
        "过去的回忆",
        "爱好或消遣",
    ]


@pytest.mark.parametrize(("name", "pattern"), list(_LIFE_FACET_PATTERNS))
def test_every_facet_pattern_compiles(name: str, pattern: str) -> None:
    re.compile(pattern)


# --- 5. 第 6 批扩容（2026-09-22）：6 个词、1 处收窄、4 条救活 ------------------
#
# 这一批与第 3 批的性质不同：第 3 批是**审计驱动**（扫出 69 条判不出面的素材，
# 补词去救活它们）；第 6 批是**对白驱动** —— 第 5 批为了不扩词表，把三条原话
# 改写成"词表认得的说法"（「气候」→「天气」、「姐妹」→「妹妹」），本批把词表
# 补上、把原话还回去。所以它的验收口径是两句：
#
# * **零漂移**：对现有 277 条 `preferredTopics` 逐条重跑，救活 0、漂移 0、丢失 0
#   （第 5 批已经把它们改写成规避词表的说法了，所以这里本来就没有可救的）；
# * **还回原话之后判得对**：下面第 3 组逐句钉住那 4 条被规避的原话。
#
# 唯一的收窄是「爱好和平」（动词读音）—— 单义检查在全库 16 条「爱好」用例里
# 抓到的唯一一处多义，按第 3 批的先例**只排除这一个紧邻搭配**。


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 家人朋友：配偶与姐妹。Birdie 的核心剧情就是"海盗的妻子"，
        # 而"姐妹"是 Emily 的原话用词（第 5 批被迫改写成"妹妹"）
        ("我丈夫是那艘沉船的船长。", "家人朋友"),
        ("我妻子也知道我不是一个普通人。", "家人朋友"),
        ("我和海莉是姐妹，这事我跟你说过吗？", "家人朋友"),
        # 天气季节：气候与暖和
        ("这里的气候全年温暖宜人……", "天气季节"),
        ("这里的天气一年到头都暖和。", "天气季节"),
        # 爱好或消遣
        ("要是自己有个什么爱好就好了。", "爱好或消遣"),
    ],
)
def test_sixth_batch_words_land_on_their_intended_facet(text: str, expected: str) -> None:
    assert _facet_of_topic(text) == expected, f"{text} 没落到 {expected}"


def test_hobby_peace_is_a_verb_not_a_hobby() -> None:
    """**本批唯一的收窄**：「爱好」另有一个动词读音（"爱好和平"）。

    单义检查在全库 16 条「爱好」用例里抓到这一处 —— 它指的是"爱好和平"，
    与"兴趣"无关。按第 3 批的先例只排除这一个紧邻搭配（`爱好(?!和平)`）。
    """

    text = "这个岛上的居民很爱好和平，不会对我们构成威胁。"

    assert "爱好或消遣" not in _facet_hits(text), "「爱好和平」又被当成兴趣了"
    assert _facet_of_topic(text) == "镇上或邻里"  # 它本来该落的面


@pytest.mark.parametrize(
    "text",
    [
        "这是我的一个秘密爱好……我已经练习好几个月了。",
        "几年前，我开始把画画作为爱好。",
        "亲爱的，我知道你会说我是个红酒狂热爱好者……",
    ],
)
def test_real_hobby_still_matches_after_the_narrowing(text: str) -> None:
    """收窄的另一侧：真正的"爱好／爱好者"照旧命中。"""

    assert "爱好或消遣" in _facet_hits(text), text


@pytest.mark.parametrize(
    ("text", "main", "trap"),
    [
        # 「暖和」13 条用例的语义全是温度，但它对**主面**的影响必须逐条核对：
        # 这一句里"烤"已经在更靠前的"吃喝"面命中了，所以天气面抢不走主面
        ("你看起来打湿了一点？为何不在火边烤暖和一点？", "吃喝", "天气季节"),
        # 「爱好」加在最后一个面，对任何已命中别的面的句子都没有主面影响
        ("几年前，我开始把画画作为爱好。", "工作或手艺", "爱好或消遣"),
        (
            "亲爱的，我知道你会说我是个红酒狂热爱好者，但你应该考虑在节日汤里加一点…",
            "吃喝",  # "汤"在吃喝面（第 2 位）先命中；"热"（天气，第 3 位）抢不走
            "爱好或消遣",
        ),
        # 「丈夫」「妻子」加在"家人朋友"（第 5 位），不许抢走更靠前的面
        ("嗯，你是对的。我也担心我的妻子和孩子。", "家人朋友", None),
    ],
)
def test_sixth_batch_words_never_steal_the_main_facet(
    text: str, main: str, trap: str | None
) -> None:
    """新词只能让判定更宽，**不许改变任何已有句子的主面**。

    这一条是"只允许救活与判得更准，不允许已有素材失去识别"的逐句版本：
    `_facet_of_topic` 按声明顺序取第一个命中，所以一个加在**靠前面**的词
    （「气候」「暖和」在天气面＝第 3 位）有能力把后面几个面的主面抢走。
    实测 277 条素材里 0 条发生这种漂移，这里把最容易出事的三类句子钉死。
    """

    assert _facet_of_topic(text) == main
    if trap:
        assert _facet_of_topic(text) != trap


# 第 5 批为了规避词表而改写掉的原话：词表补上之后，它们判得对了吗。
REVIVED_BY_RESTORING_THE_ORIGINAL_LINES = {
    # Emily：原话里"姐妹"不在词表，改写成了「海莉是我妹妹」。
    # 还要注意主面：原话含"你说过"（→"玩家自己"），是**更靠后**的面，
    # 所以「姐妹」一进来主面就从"玩家自己"换成"家人朋友" —— 这条判得更准。
    # 第 7 批已把原话还进素材（此前那句改写「海莉是我妹妹」已从数据里删除）。
    ("Emily", "我和海莉是姐妹，这事我跟你说过吗？"): "家人朋友",
    # Birdie：原话里的"气候"不在词表，改写成了「这里的天气一年到头都暖和」
    ("Birdie", "孩子，这里的气候全年温暖宜人……很适合我这把老骨头……"): "天气季节",
    # Birdie 的家人面：任务 130「海盗的妻子」，此前整面判不出来
    ("Birdie", "我丈夫是那艘沉船的船长。"): "家人朋友",
    # Pam：原话判不出爱好面，第 5 批没有采用；第 7 批把它写进了素材
    ("Pam", "要是自己有个什么爱好就好了。"): "爱好或消遣",
}


@pytest.mark.parametrize(
    ("npc_id", "sentence", "expected"),
    [(npc, sentence, facet) for (npc, sentence), facet in REVIVED_BY_RESTORING_THE_ORIGINAL_LINES.items()],
)
def test_original_lines_revived_by_the_sixth_batch(npc_id: str, sentence: str, expected: str) -> None:
    """这四条就是第 6 批扩词表的**全部收益**，逐句钉住。

    参数里的 `npc_id` 只为可读性（说明这句话是谁说的），断言本身在句子层面。
    第 6 批写这条时只有 Emily 与 Birdie 的原话真的进了素材；**第 7 批把 Pam 那条
    也补进了 `data/personas/vanilla.json`**（见 `test_topic_slot_rotation.py` 的
    `RESTORED_TO_THE_ORIGINAL_LINE` 与 `test_pam_finally_has_a_hobby_facet`），
    到这里四条全部落地。
    """

    assert _facet_of_topic(sentence) == expected, f"{npc_id} 的这条原话没落到 {expected}"
