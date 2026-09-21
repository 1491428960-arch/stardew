"""`_TOPIC_GROUNDING_MARKERS` 的「刚X」覆盖补丁（2026-09-21）。

背景（语料口径，见 `.tmp/topic_corpus.jsonl`——1334 条真实「找话题」首轮回复，
取自 `artifacts/character-quality-eval/*/results.jsonl`）：

* 364 条含「刚X」形态（27.3%）；
* 旧表 15 词只认「我刚」「刚发现」「刚翻」三种「刚」系写法，把其中 163 条
  （占语料 12.2%，占「刚X」44.8%）判成「无来源」——「刚把这片葡萄浇了水」
  这种明明带来源的句子，只因为没有「我刚」三个字就被漏掉；
* 补表后降到 3 条（0.2%，占「刚X」0.8%），剩下 3 条全是「你刚来…」，
  那是在引用玩家，**本来就不该**算 NPC 自己的来源。

这个补丁只动**放行侧**：标记命中只会让 `missing_opening_grounding` 少拦、
不会多拦，所以它不增加误伤。语料实测：门2（指代起句）命中 11 条，
补表前后都拦 11 条，**0 条从拦变放行**。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.guard import (
    _TOPIC_GROUNDING_MARKERS,
    missing_opening_grounding,
)
from stardew_ai_bridge.prompts import PromptBuilder

# 方案点名要补的五个形态。
USER_NAMED_FORMS = ("刚把", "刚给", "刚好", "刚收", "刚弄")

# 语料里真实出现、旧表认不出的自身来源句。每项：(用例名, 表里的形态词, 原句)。
CORPUS_SOURCED_FORMS = (
    ("刚把", "刚把", "葡萄园还算好，刚把这片葡萄浇了水，没太忙。"),
    ("刚给", "刚给", "这周确实有点忙，刚给几串快熟的葡萄浇过水了。"),
    ("刚收", "刚收", "葡萄园刚收完一批葡萄呢，虽然不多但看着还是挺开心的。"),
    ("刚弄", "刚弄", "刚弄好个新歌单，你要听听吗？"),
    ("刚摘", "刚摘", "要是能一起去看那些刚摘下的果实，我大概会高兴得晕过去吧。"),
    ("刚铺", "刚铺", "走吧，小心别踩坏刚铺好的藤蔓，我想请你喝我亲手酿的第一批酒。"),
    ("刚下班", "刚下", "嘿，刚下班，今天店里人多得离谱。"),
    ("刚下山", "刚下", "刚下山转了一圈，风比昨天硬，山顶那边大概要变天了。"),
    ("刚调", "刚调", "这首刚调完的回放你听听，第二段鼓点那里我还在犹豫。"),
    ("刚在", "刚在", "唔，刚在改一段代码，把存档里的时间戳格式修了下。"),
    ("刚从", "刚从", "刚从诊所回来，手上还带着消毒水的味道。"),
    ("刚洗", "刚洗", "休息？呵，刚洗掉一身泥灰就躺下了，也算是不错了吧。"),
    ("刚烧", "刚烧", "塔里的炉子刚烧上水，这雨一下，倒是正好。"),
    ("刚读", "刚读", "刚读完你发给我的那一章，脑子里还停在那句关于旧船的段落上。"),
    ("刚排", "刚排", "这首刚排完的回放你听听——第二段鼓点那里我还在犹豫。"),
    ("刚醒", "刚醒", "酒窖里这杯新酿刚醒开，我本来想先记一笔发酵的味道。"),
)


def _topic_messages() -> list[dict[str, str]]:
    identity = {
        "npcId": "Sophia",
        "displayName": "Sophia",
        "stageProfile": {"stage": "dating"},
        "voiceStyle": {
            "signatureMoves": [
                "谈到绘画、酿造或刚发现的小事时，先脱口说出第一反应（哇、等等、你看）。"
            ]
        },
    }
    context = {
        "npcIdentity": identity,
        "qualityContext": {},
        "interaction": {"intent": "topic", "channel": "face_to_face"},
        "gameState": {"relationshipStage": "dating", "location": "FarmHouse"},
        "history": [],
    }
    return PromptBuilder().build(context, "")


# --- 补表本身 ----------------------------------------------------------------


@pytest.mark.parametrize("marker", USER_NAMED_FORMS)
def test_user_named_forms_are_in_the_table(marker: str) -> None:
    assert marker in _TOPIC_GROUNDING_MARKERS


@pytest.mark.parametrize(
    ("marker", "sentence"),
    [pytest.param(item[1], item[2], id=item[0]) for item in CORPUS_SOURCED_FORMS],
)
def test_corpus_sourced_forms_are_recognized(marker: str, sentence: str) -> None:
    assert marker in _TOPIC_GROUNDING_MARKERS
    assert any(m in sentence for m in _TOPIC_GROUNDING_MARKERS)


def test_the_original_markers_survive() -> None:
    """补表只增不删。"""

    original = (
        "我刚", "我最近", "刚才", "刚发现", "刚翻", "今天", "昨晚", "上次",
        "看到", "听到", "想起", "正在", "有一", "一张", "一首",
    )

    for marker in original:
        assert marker in _TOPIC_GROUNDING_MARKERS


def test_citing_the_player_is_not_a_source() -> None:
    """「你刚来」说的是玩家，不是 NPC 自己的来源句——刻意不收进表。

    语料里 3 条「刚X」漏判全是这个形态，属于**正确**保留。
    """

    assert "刚来" not in _TOPIC_GROUNDING_MARKERS


def test_the_bare_character_is_not_a_marker() -> None:
    """单字「刚」绝不能进表——它会把任何含「刚」的句子都放行。"""

    assert "刚" not in _TOPIC_GROUNDING_MARKERS


def test_the_ambiguous_form_is_recorded_as_low_precision() -> None:
    """「刚好」按方案收进表，但它在本表里精度最低（多为副词「恰好」）。

    语料 17 次出现里约 15 次是副词：「刚好我也想活动活动」「雨声刚好能盖过」
    「你来得刚好」。这里只钉住它确实在表里（方案要求），风险记录在
    `guard.py` 的注释里，供将来收紧拦截时优先复核。
    """

    assert "刚好" in _TOPIC_GROUNDING_MARKERS


# --- 端到端：补表确实改变了 guard 的判定方向 ---------------------------------


def test_a_gang_source_sentence_now_clears_the_guard() -> None:
    """补表前会被拦、补表后放行的形态——这是补丁的直接效果。

    句子刻意避开「我刚」：那三个字旧表就认，用它证明不了补表起了作用。
    """

    reply = "那张唱片还在转——刚收完葡萄，我手上全是土。你等会儿过来吗？"
    messages = _topic_messages()

    assert "我刚" not in reply
    assert "刚收" in reply
    assert missing_opening_grounding(messages, reply) is False


def test_a_truly_headless_opening_is_still_blocked() -> None:
    """补表是放行侧补丁，不该把真正的「没头没尾」也放过去。"""

    messages = _topic_messages()

    assert missing_opening_grounding(messages, "那件事你听说了吗？") is True
    assert missing_opening_grounding(messages, "后来还是没送来，真让人头疼。") is True


def test_an_opaque_opening_without_any_source_still_fails() -> None:
    """没有来源标记的指代起句照旧被拦，补表没有把门槛拆掉。"""

    messages = _topic_messages()

    for reply in (
        "那个东西你什么时候能带来？",
        "你还记得吧，就是那件事。",
        "后来怎么样了？",
    ):
        assert missing_opening_grounding(messages, reply) is True
