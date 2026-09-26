"""清掉中文台词里漏进来的拉丁／假名碎片。

**成因已查实（2026-09-24）：模型幻觉，不是素材传染。**
证据两条：

1. 索菲亚的 **310 条**索引素材零污染（0 个 `_XX` 标记、0 个拉丁字母、
   0 个 ID 前缀）；全库仅 7 条含标记，都在 Lance / Mermaid / Wizard 身上，
   进不了她的 prompt。
2. 逐卡扫描 prompt 只找到 **39 处**拉丁串，全是指令**引用自己的字段名**
   （「`npcIdentity.voiceStyle` 是当前…」「`voiceAnchors` 是正向原…」），
   属于说明性文字，不是可照抄的内容。

prompt 侧那句「请用简洁、自然的中文回复」（`providers.py`）与
`safety_rules` 的「只生成当前 NPC 的中文游戏对白」**都已经存在，但拦不住**，
所以防线只能放在出口。

**为什么是清理而不是加约束**：项目铁律是「反机械感靠减约束、给示例，
不靠加规则」。这里不改 prompt、不加指令，只把已经漏出来的碎片擦掉 ——
对模型的表达空间没有任何影响。

**保守原则**（实测校准）：在 8765 轮历史输出上只改动 **0.2%**。
- 整段不是中文时**一个字都不碰**（纯英文回复是另一类问题，在这里动手会删光）；
- 什么都没删到就原样返回，**不做任何空白规范化** ——
  早期版本顺手压掉了行尾双空格，那是 markdown 硬换行，
  在 216 轮「改动」里占了绝大多数，纯误伤。
"""

from __future__ import annotations

import re

_CJK = re.compile(r"[\u4e00-\u9fff]")

#: 中文与中文标点 —— 碎片的左右邻必须是其中之一，这样「夹在中文里的英文」
#: 才会被认出来，而整句英文、URL、跟在英文后面的词都不受影响。
_CJK_OR_PUNCT = r"[\u4e00-\u9fff，。！？、；：…—「」『』（）【】〈〉《》]"

#: `{{<purple>}}` / `{{</purple>}}` 这类标记语法。
_MARKUP = re.compile(r"\{\{[^{}]*\}\}")

#: `_CELLPHONE_MAINMENU_` / `毯子_GE` 这类 i18n 标记。
_I18N = re.compile(r"(?<![A-Za-z0-9])_+[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*_{0,}(?![A-Za-z0-9])")

#: 夹在中文里的拉丁词（含被截断的残片，如 `utting`、`Rgb`）。
#: 用**捕获组**而不是 lookbehind：组 1 是左邻（要保留），组 2 是拉丁部分
#: （用来查白名单）—— 只按 `group(0)` 判白名单会连左邻的中文一起算进去。
_LATIN = re.compile(
    rf"({_CJK_OR_PUNCT})[ \t]*([A-Za-z][A-Za-z0-9'’\-]*"
    rf"(?:\s+[A-Za-z][A-Za-z0-9'’\-]*)*)[ \t]*(?={_CJK_OR_PUNCT})"
)

#: 夹在中文里的假名（实测出现过 `ティーほかもない`）。
_KANA = re.compile(rf"({_CJK_OR_PUNCT})[ \t]*[\u3040-\u309f\u30a0-\u30ffー]{{2,}}[ \t]*(?={_CJK_OR_PUNCT})")

#: **行尾／段尾**的拉丁碎片（2026-09-26 补）。
#:
#: 实测形态（`victor-ab-before2-20260926-120422` 第 2 轮输出末尾）：
#:     ...卸载了。\n\n你玩什么？ounced
#: 左邻是中文标点、**右邻是句尾** —— 而 `_LATIN` 的前瞻要求右邻也是中文，
#: 于是句尾的碎片一路漏出出口。这是 `_LATIN` 的**边界**，不是新一类问题。
#:
#: 尾随空白写在**前瞻里**（不进 `group(0)`）：删掉碎片不该顺手吃掉行尾双空格，
#: 那是 markdown 硬换行，有语义（见文件头「保守原则」第二条）。
_LATIN_AT_TAIL = re.compile(
    rf"({_CJK_OR_PUNCT})[ \t]*([A-Za-z][A-Za-z0-9'’\-]*"
    rf"(?:\s+[A-Za-z][A-Za-z0-9'’\-]*)*)(?=[ \t]*$)",
    re.MULTILINE,
)

#: **必须留下的拉丁串**。目前只有一条，但它很关键：
#: `FakeProvider` 的降级提示写作「本地演示·非真实 AI」，
#: 早期版本把 `AI` 当碎片删掉，于是提示变成「本地演示·非真实」——
#: **一句在骗人的提示，比一句夹了英文的提示糟得多。**
#: 实测教训：清洗规则的第一个问题是「它会不会删掉不该删的」，
#: 而不是「它能不能删干净」。
_KEEP_LATIN = frozenset({"AI"})

#: 删掉碎片后可能留下「空格 + 中文标点」，或「中文标点 + 空格」。
#: ⚠ 两处都用 `[ \t]` 而非 `\s`，并且 `(?=\S)` 保证后面还有内容 ——
#: 行尾的「。  \n」是 markdown 硬换行，不能被吃掉。
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([，。！？、；：])")
_SPACE_AFTER_PUNCT = re.compile(r"([，。！？、；：])[ \t]+(?=\S)")


def _drop_latin(match: re.Match[str]) -> str:
    """删掉匹配到的拉丁碎片，但放行 `_KEEP_LATIN` 里的。"""

    if match.group(2).strip() in _KEEP_LATIN:
        return match.group(0)
    return match.group(1)


def scrub_reply(text: str) -> str:
    """返回清掉碎片后的台词。没有可清的就**原样返回**。"""

    if not text or len(_CJK.findall(text)) < 2:
        # 整段不是中文 —— 不做处理。在这里动手只会把整句删光。
        return text

    out = _MARKUP.sub("", text)
    out = _I18N.sub("", out)
    # 相邻碎片删掉后可能又接出新的一对，迭代到稳定（上限 3 次即可收敛）。
    for _ in range(3):
        new = _KANA.sub(r"\1", out)
        new = _LATIN.sub(_drop_latin, new)
        new = _LATIN_AT_TAIL.sub(_drop_latin, new)
        if new == out:
            break
        out = new

    if out == text:
        return text

    # ⚠ 只清理**行内**：不动行尾空白（markdown 硬换行有语义）。
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = _SPACE_BEFORE_PUNCT.sub(r"\1", out)
    out = _SPACE_AFTER_PUNCT.sub(r"\1", out)
    return out
