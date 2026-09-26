"""`reply_scrub` 的行为锁。

每一条用例都对应一个**实测出现过**的形态，不是假想的。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.reply_scrub import scrub_reply


# --- 实际出现过的碎片形态 ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # i18n 标记（`bef2-stranger-28`）
        ("罐子里还剩大概六勺，_CELLPHONE_MAINMENU_ 斯嘉丽明天要来。",
         "罐子里还剩大概六勺，斯嘉丽明天要来。"),
        # 标记粘在中文词尾（`depth-nolateral2`）
        ("那床毯子_GE……你要是想窝着，我可以把电视打开。",
         "那床毯子……你要是想窝着，我可以把电视打开。"),
        # 标记语法（`ac-stranger-36`）
        ("还有一点点浅蓝——而且{{<purple>}}翻过来的时候，底下藏着一小片绿色光斑{{</purple>}}。",
         "还有一点点浅蓝——而且翻过来的时候，底下藏着一小片绿色光斑。"),
        # C# 类名当人名（`bef2-stranger-40`）
        ("翻出一盒没贴标签的精灵石标本，ResourceManager 说是上次市集调剂来的。",
         "翻出一盒没贴标签的精灵石标本，说是上次市集调剂来的。"),
        # 中文词被换成英文（`ab-kimi-1`）
        ("一个人待着的时候， silence 会自己变得很大。",
         "一个人待着的时候，会自己变得很大。"),
        # 句首英文、无空格（`ac-stranger-4`）
        ("嗯……！ soil今天挺干净的，我刚翻完葡萄架下面的土。",
         "嗯……！今天挺干净的，我刚翻完葡萄架下面的土。"),
        # 多词短语（`ac-stranger-15`）
        ("它们总是往有光的那边挪， rooting pattern 好看极了。",
         "它们总是往有光的那边挪，好看极了。"),
        # 首字母缩略（`ac2-dating-8`）
        ("是最开始买错的那种粉色，Rgb调了几次都不对。",
         "是最开始买错的那种粉色，调了几次都不对。"),
        # 游戏术语（`cc-kimi-v11-dating-7`）
        ("我刚把晒好的蓝 Buff 收进筐，指尖还沾着那股海的涩味。",
         "我刚把晒好的蓝收进筐，指尖还沾着那股海的涩味。"),
        # 英文名词（`cc2-v11-stranger-29`）
        ("有些颜色特别好看，是新的 shipment。",
         "有些颜色特别好看，是新的。"),
        # 被截断的残片（`cc2-v11-stranger-3`）
        ("手边这堆绒布刚裁好。utting了一半才想起来忘了留缝份。",
         "手边这堆绒布刚裁好。了一半才想起来忘了留缝份。"),
        # 假名（`bef2-stranger-28`）
        ("她喝得多。ティーほかもない……就是说，要不要顺路带一包？",
         "她喝得多。……就是说，要不要顺路带一包？"),
    ],
)
def test_scraps_known_fragment_shapes(raw: str, expected: str) -> None:
    assert scrub_reply(raw) == expected


# --- 不许误伤 ---------------------------------------------------------------


def test_untouched_text_is_returned_identically() -> None:
    """没有碎片时必须**逐字**返回 —— 包括行尾双空格。

    早期版本顺手把 `  \\n` 压成 `\\n`，在 216 轮「改动」里占了绝大多数，
    而那是 markdown 硬换行，有语义。测试钉死这一点。
    """

    raw = "嘿，你看这个——刚在酒窖角落翻出一小坛。  \n\n给你留着，你哪天有空过来尝尝？"

    assert scrub_reply(raw) == raw


def test_pure_english_reply_is_left_alone() -> None:
    """整段不是中文 ⇒ 一个字都不碰。

    那是另一类问题（模型整段跑英文），在这里动手只会把整句删光。
    """

    raw = "I found a jar of wine in the cellar. Do you want some?"

    assert scrub_reply(raw) == raw


@pytest.mark.parametrize(
    "raw",
    [
        "",                     # 空
        "……",                   # 只有标点
        "好。",                 # 中文太少（不足 2 字）不处理
        "OK",
    ],
)
def test_degenerate_inputs_pass_through(raw: str) -> None:
    assert scrub_reply(raw) == raw


def test_chinese_punctuation_is_not_eaten() -> None:
    """删掉碎片后不能把中文标点一起吃掉。"""

    out = scrub_reply("我刚把布料收好， cut 了一半。你别笑我。")

    assert "，" in out
    assert "。" in out
    assert "cut" not in out


def test_url_inside_chinese_text_survives() -> None:
    """正文里的网址不该被当碎片删掉（它的左邻是空格、右邻是中文标点，
    但整体含 `.` `/` `:`，不在拉丁词字符集内）。"""

    raw = "你看这个 https://example.com/abc 就是我说的那种花纹。"

    # 至少不能把整段删空
    assert "example" in scrub_reply(raw)


def test_the_demo_marker_survives() -> None:
    """`FakeProvider` 的降级提示必须逐字保留。

    它写作「本地演示·非真实 AI」，是在告诉用户**这不是真实 AI 回复**。
    早期版本把 `AI` 当碎片删掉，提示变成「本地演示·非真实」——
    **一句在骗人的提示，比一句夹了英文的提示糟得多。**

    这条也是清洗规则的一般教训：第一个要问的不是「能不能删干净」，
    而是「会不会删掉不该删的」。
    """

    marker = "【本地演示·非真实 AI】"
    raw = f"{marker}：春天、雨天、上午确实会改变一天的安排。"

    out = scrub_reply(raw)

    assert marker in out
    assert out == raw


# --- 行尾碎片（2026-09-26 新增）---------------------------------------------
#
# 实测形态（`victor-ab-before2-20260926-120422` 第 2 轮输出末尾）：
#     ...卸载了。\n\n你玩什么？ounced
# 左邻是中文标点、**右邻是句尾** —— 而 `_LATIN` 的前瞻要求右邻也是中文，
# 于是句尾的碎片一路漏出出口。这是 `_LATIN` 的边界，不是新一类问题。


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("你玩什么？ounced", "你玩什么？"),
        ("前阵子卡在水牢，卸载了。\n\n你玩什么？ounced",
         "前阵子卡在水牢，卸载了。\n\n你玩什么？"),
        # 碎片与行尾之间还有空白时，同样删干净
        ("他说下雨就收摊。 cancelled", "他说下雨就收摊。"),
    ],
)
def test_scraps_trailing_fragment(raw: str, expected: str) -> None:
    assert scrub_reply(raw) == expected


def test_trailing_url_is_not_eaten() -> None:
    """行尾的网址整体含 `:` `/` `.`，不在拉丁词字符集内，不能被当碎片删掉。"""

    out = scrub_reply("你看这个 https://example.com/abc")

    assert "example" in out
    assert "/abc" in out


def test_trailing_english_line_is_left_alone() -> None:
    """整段中文后面跟一整行英文时，左邻是换行、不在 `_CJK_OR_PUNCT` 里，不匹配。

    纯英文回复是另一类问题，见 `test_pure_english_reply_is_left_alone`。
    """

    out = scrub_reply("我读了那本书。\n\nGreat book about farming.")

    assert "Great book" in out

