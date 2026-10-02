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
    """没有碎片时必须**逐字**返回 —— 包括段落**内部**的双空格。

    早期版本顺手把 `  \\n` 压成 `\\n`，在 216 轮「改动」里占了绝大多数，
    而那是 markdown 硬换行，有语义。测试钉死这一点。

    ⚠ 2026-10-02 起**换行本身**会被收掉（用户要求「别分行」，见
    `test_paragraph_breaks_are_joined`），所以样本改用不含换行的句子 ——
    双空格的保护范围随之明确为「段落内部」：紧挨换行的空白随换行一起走，
    因为那些空白已经没有可断的行了（`reply_scrub._NEWLINE`）。
    """

    raw = "嘿，你看这个——刚在酒窖角落翻出一小坛。  给你留着，你哪天有空过来尝尝？"

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


# --- 英文角色名会被擦掉（2026-09-27 复核钉死）-------------------------------
#
# ⚠ 我一度以为 `guard._allowed_english` 与 `_KEEP_LATIN` 是漏了同步，就把两处
# 接成同源 —— `test_api.py::test_fake_dialogue_returns_structured_response`
# 立刻变红，而**它是对的**。两处判的压根不是一回事，详见
# `reply_scrub._KEEP_LATIN` 的注释：guard 宽（放行角色名，免得白重试），
# 这里窄（中文台词里露英文名就是错的）。**两者是配合工作的。**
#
# ⚠ 下面钉死的是**当前设计行为**，不是「这个行为没有代价」：
# 模型该写「阿比盖尔」却写了 `Abigail` 时，guard 因放行而不重试，名字到了这里
# 被删，**句子会残缺**（「我那天在的店里碰见了」）。根因在模型没写中文名，
# 不在清洗 —— 清洗只是把英文挡在玩家视线之外。代价已记档（条目 62）。
#
# 句首的名字左邻不是中文，`_LATIN` 不匹配 —— 2026-09-27 曾在这里**如实钉住**
# 「它会一路漏到玩家眼前」。**2026-09-28 已修**：`_LATIN_AT_HEAD` 接管
# 「行首 + 空格 + 汉字」这一形态，下面最后三条断言随之更新。
# ⚠ 另外两类**刻意不碰**，一并钉住：冒号前缀（兜底文案的说话人标识）与
# 英文后紧跟标点的形态（删了会留下孤立逗号，比留着更怪）。


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("以前会和 Abigail 还有 Sebastian 定下规矩。",
         "以前会和还有定下规矩。"),
        ("我那天在 Pierre 的店里碰见 Marnie 了。",
         "我那天在的店里碰见了。"),
        ("这是 SVE 里的 Olivia。",
         "这是里的。"),
        # 句首名字（后跟空格 + 汉字）：2026-09-28 起由 `_LATIN_AT_HEAD` 擦掉
        ("Shane 说他明天要去镇上。",
         "说他明天要去镇上。"),
        # ⚠ 刻意不碰：冒号前缀是说话人标识，删了玩家会看到「：我们改天再聊。」
        ("Rasmodia：我们改天再聊。",
         "Rasmodia：我们改天再聊。"),
        # ⚠ 刻意不碰：英文后紧跟标点，删了会留下孤立逗号
        ("Alex，你来了。",
         "Alex，你来了。"),
        # 2026-09-28：**品牌名放行**，与角色名分开对待。
        # 原版中文自己就写「鹈鹕镇 Joja 超市」（`personas.py:114` 引 Morris 初见台词），
        # 全库扫出 401 处。删掉它是**静默损坏** —— 输出通顺、没有告警：
        #     「我在 Joja 上班。」 -> 「我在上班。」（在 Joja 工作 ≠ 在上班）
        # 判据是「原版中文里出现过」，由语料决定，不靠人猜（见 `reply_scrub._KEEP_LATIN`）。
        ("我在 Joja 上班。",
         "我在 Joja 上班。"),
        ("Joja 超市的东西比皮埃尔那边便宜。",
         "Joja 超市的东西比皮埃尔那边便宜。"),
        ("我今天去了 Joja。",
         "我今天去了 Joja。"),
        # 反面：角色名没有这个豁免，仍然该删（上一条 `Shane` 的用例）。
        # 品牌名放行**不等于**英文整体放行。
        ("我昨天在 Joja 碰到 Shane 了。",
         "我昨天在 Joja 碰到了。"),
        # 大小写与变体：名单一律小写 + 比对时 `.casefold()`（与 `guard` 一致）。
        # 精确匹配时这三条都会被删成「我在上班。」—— 同一个静默损坏换了拼写。
        ("我在 joja 上班。",
         "我在 joja 上班。"),
        ("我在 JOJA 上班。",
         "我在 JOJA 上班。"),
        ("我在 JojaMart 上班。",
         "我在 JojaMart 上班。"),
        # 当初那条「AI」教训的**小写变体**也必须放行：
        # 「本地演示·非真实 ai」以前会变成「本地演示·非真实」（一句在骗人的提示）。
        ("本地演示·非真实 ai",
         "本地演示·非真实 ai"),
    ],
)
def test_mod_english_identifiers_are_scrubbed(raw: str, expected: str) -> None:
    assert scrub_reply(raw) == expected


def test_scrap_is_still_scrapped_after_whitelisting_names() -> None:
    """放行 `AI` 之外，真正的碎片仍然要被删 —— 别把口子开太大。"""

    out = scrub_reply("我刚把晒好的蓝 Buff 收进筐，指尖还沾着那股海的涩味。")

    assert "Buff" not in out
    assert "蓝" in out and "收进筐" in out


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
        # 2026-10-02 起换行一并收掉，所以期望里的 `\n\n` 不再保留
        ("前阵子卡在水牢，卸载了。\n\n你玩什么？ounced",
         "前阵子卡在水牢，卸载了。你玩什么？"),
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


def test_trailing_english_line_after_a_paragraph_break() -> None:
    """⚠ 2026-10-02 **行为变更**：行尾英文的左邻不再是换行。

    旧行为：左邻是换行、不在 `_CJK_OR_PUNCT` 里，`_LATIN_AT_TAIL` 不匹配它，
    整行英文一路漏到玩家眼前（见下一条注释里的旧说明）。

    新行为：段落换行在清洗时先被收掉，左邻变成中文标点 —— 但**只对行尾
    没有标点的形态生效**。`_LATIN_AT_TAIL` 的前瞻是 `(?=[ \\t]*$)`，
    句尾那个 `.` 会让它回溯失败。所以下面两条结果的差异**不是取舍**，
    而是那条正则本来就有这个边界（同 `_LATIN` 一脉），这里如实钉住变更后的结果。

    ⚠ 这个边界是我先猜错、被这条测试纠正回来的：我以为「整行英文都会被删」。
    """

    # 行尾无标点：落进射程，被删
    assert (
        scrub_reply("那本书我看完了。\n\nGreat book about farming")
        == "那本书我看完了。"
    )

    # 行尾有标点：前瞻失败，英文保留 —— 与改动前一致，只是中间少了那个空行
    out = scrub_reply("我读了那本书。\n\nGreat book about farming.")

    assert out == "我读了那本书。Great book about farming."
    assert "Great book" in out


# --- 段落换行会被压掉（2026-10-02 用户要求）---------------------------------
#
# 用户在游戏里看到回复中间有个突兀的空行，说「看着奇怪，别分行，
# 两段接成一句」。形态高度一致 —— 模型习惯先甩一句短的、空行、再展开：
#     嘿！\n\n我刚从矿洞那边回来——那边第三层有块石头，敲开里面居然是水晶。
# 实测采样的 206 处含换行回复里，**205 处是 `\n\n`**，只有 1 处是单个换行。
#
# 位置在游戏对话框里最刺眼：那是一个单行气泡，空行既不是排版也不是停顿。
# 中文本来就靠标点断句，所以**直接拼接**、不补任何字符。
#
# ⚠ 纯英文回复仍然整段不碰（中文判定在换行处理之前）—— 那是另一类问题，
# 见 `test_pure_english_reply_is_left_alone`，在这里动手只会把整句删光。


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 实测形态
        ("嘿！\n\n我刚从矿洞那边回来。",
         "嘿！我刚从矿洞那边回来。"),
        # 换行两侧的空白一并收掉，不留「。  给你」这种双空格
        ("刚翻出一小坛。  \n\n给你留着。",
         "刚翻出一小坛。给你留着。"),
        # 单个换行同样不留
        ("你确定吗？\n那我先走了。",
         "你确定吗？那我先走了。"),
        # 连续三个以上换行
        ("嗯。\n\n\n后来呢？",
         "嗯。后来呢？"),
        # CRLF（Windows 行尾）
        ("先这样。\r\n\r\n回头再说。",
         "先这样。回头再说。"),
    ],
)
def test_paragraph_breaks_are_joined(raw: str, expected: str) -> None:
    assert scrub_reply(raw) == expected


# --- 半角省略号（2026-09-27 新增）-------------------------------------------
#
# 实测形态（`docs/active-work.md` 条目 60 的真实生成验证，`fall-9-sam`）：
#     呃，就那种...滑板鞋，高帮的，侧边有条纹。
#
# 三个半角句点夹在中文之间。`_LATIN` 要求以 `[A-Za-z]` 开头，`format_issue`
# 的四类噪声（markdown / stage_direction / english / leading_punctuation）
# 也都不认它，于是它一路漏到玩家眼前。
#
# ⚠ **只收两个及以上**，单个 `.` 一个都不碰：`3.14`、`Mr.`、文件名、
# URL 里的点都要留。半角逗号／叹号／问号同理不收 —— 收了就会把 `1,000`
# 变成 `1，000`，那是误伤。
#
# 这条规则走**清理**而不是**重试**：`format_issue` 命中会真的重发一次请求，
# 而这里删掉就好，零成本 —— 与文件头「不改 prompt、不加指令」的定位一致。


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 实测形态
        ("呃，就那种...滑板鞋，高帮的，侧边有条纹。",
         "呃，就那种……滑板鞋，高帮的，侧边有条纹。"),
        # 夹在中文标点之间
        ("我想了想……嗯..算了。",
         "我想了想……嗯……算了。"),
        # 句尾
        ("他说他也许会来...",
         "他说他也许会来……"),
        # 行尾（后面还有一段）
        ("你确定吗...\n\n那我先走了。",
         "你确定吗……那我先走了。"),
        # 多于三个点
        ("等等....我忘了。",
         "等等……我忘了。"),
    ],
)
def test_halfwidth_ellipsis_becomes_chinese(raw: str, expected: str) -> None:
    assert scrub_reply(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "圆周率大概是 3.14 吧。",
        "价格是一千, 二百个金币。",
        "总价 1,000 金币，你数数。",
        "Mr. Qi 说要保密。",
        "你看这个 https://example.com/a..b 是我瞎编的。",
    ],
)
def test_single_dot_and_halfwidth_comma_are_not_touched(raw: str) -> None:
    """单个 `.` 与半角 `,` 必须原样留下 —— 它们在数字、缩写、URL 里是合法的。

    这是清洗规则的一般教训（见 `test_the_demo_marker_survives`）：
    先问「会不会删掉不该删的」，再问「能不能删干净」。
    """

    assert scrub_reply(raw) == raw

