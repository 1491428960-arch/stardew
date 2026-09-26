"""角色语言指纹：从原文统计「他怎么说」，并与手写人设的语言层对照。

## 为什么要有这一层（2026-09-26）

`data/personas/*.json` 的语言层字段（`openers` / `speechParticleHints` /
`sentencePattern` / `signatureMoves`）**是手写的抽象概括**，与原文差距很大。
刘易斯一例：原文日常对话 71 条、分句后中位 12 字、三成带省略号、语气字最高频是「啊」，
而 persona 的 `openers` 写着「你好，最近小镇还算平稳。」这类 10~15 字完整礼貌句、
`speechParticleHints` 只有 `["啊", "哦"]`。**模型是严格照着一份写错的说明书在演。**
本模块把「他怎么说」变成可复现的统计，供人设改写时有据可依。

## 分界：什么该统计、什么必须保留手写

- **「他该说什么」保留手写** —— `coreTraits` / `knowledgeRules` / `stageProfiles` /
  `avoid` 是行为约束与内容边界，统计替代不了，也不该替代。
- **「他怎么说」由本模块从原文统计** —— 句长、省略号/感叹号比例、语气字、句首习惯、
  高频短语、代表原话。

## 证据分级：不能对所有角色用同一口径

语料的 `evidenceKind` 有四类，其中只有前三类能回答「他平时怎么说话」：

| evidenceKind | 来源 | 算出声证据？ |
|---|---|---|
| `dialogue` | `Characters/Dialogue/*.json` | ✅ |
| `marriage_dialogue` | 婚后对白 | ✅ |
| `extra_dialogue` | `Data/ExtraDialogue` | ✅ |
| `event_dialogue` | 事件脚本（剧情节拍） | ❌ 仅供参考 |

⚠ **必须读 `resolvedText`，不能读 `text`** —— 语料里的 `text` 保存的是 Content Patcher
的**原始模板**（`{{i18n:Sophia.CharacterDialogue.001}}`），中文原文在 `resolvedText`
（20260923 批次：8509/14063 条有，仅 310 条真的没解析出来）。只读 `text` 的后果
不是报错，而是**看起来很正常的假数字**：SVE 角色（Sophia / Olivia / Victor / Claire /
Lance / Andy …）的全部日常对白会按键名字符串统计，指纹写成「句长中位 35、语气字 0」，
读起来像「这个角色说话很长、不用语气词」。**「索菲亚没有日常对白」这个结论就是这么
做出来的** —— 实际她有 313 条。取值口径统一收在 `dialogue_text()` 一处。

## 语言层字段的真实去路（读 `prompts.py` 核实，2026-09-26）

进 prompt 的**实际**路径与上限跟直觉不同，写多了不一定有用：

| 字段 | 进 prompt | 上限（`_compact_voice_style`, prompts.py:3146） |
|---|---|---|
| `tone` | ✅ | 1 条 / 120 字 |
| `sentencePattern` | ✅ | 2 条 / 65 字 |
| `signatureMoves` | ✅ | 2 条 / 140 字 |
| `openers` | ✅ | 4 条 / 60 字 |
| `speechParticleHints` | ✅ | **只取前 4 个**（`limit=4`） |
| `closers` | ✅ | 4 条 / 60 字（**2026-09-26 补入白名单**，此前是死数据） |

取值顺序（`prompts.py:3198-3206`）是 **`speechParticleHints` 优先**，
为空时才退回从 `openers` 首字里抽（且首字必须落在 `_INTERJECTION_HEADS` 里，
**那张表不含「嚯」**）。⇒ **写第 5、6 个语气字是净损失：占位但不生效。**
本模块的 `persona_voice_gaps()` 专门把这些「数据有、没发出去」的位置报出来。

## 两个长度口径都要给，因为它们回答不同的问题

- `utteranceLength` —— **一条发言**有多长，用来判断 `openers` 是否写得太长（openers 是
  一条完整发言）。
- `sentenceLength` —— 按 `。！？…` 分句后**一句话**有多长，用来描述模型落笔时的节奏。

只给一个都会误导：刘易斯的发言中位 41 字，而分句后只有 12 字。
"""

from __future__ import annotations

import collections
import json
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

# 叹词表**不抄第二份**：`prompts._INTERJECTION_HEADS` 决定「openers 的首字能不能当颗粒
# 抽出来」，审计必须用同一份数据判断，否则它说的和线上做的会分叉。两者是不是同一个
# 对象由 `tests/test_voice_fingerprint.py` 用 `is` 钉住。
from stardew_ai_bridge.prompts import _INTERJECTION_HEADS as INTERJECTION_HEADS

#: 能当作「他平时怎么说话」的证据类型。`event_dialogue` 是剧情节拍，不算。
SPOKEN_EVIDENCE_KINDS = frozenset({"dialogue", "marriage_dialogue", "extra_dialogue"})

#: `prompts.py::_compact_voice_style` 里 `speechParticleHints` 的实际上限。
#: 这里另立常量是为了让审计能说出「第 5 个以后不生效」；两者是否一致由
#: `tests/test_voice_fingerprint.py::test_prompt_really_keeps_only_four_particles`
#: 调**真实 prompt 函数**钉住，而不是靠人记住。
PROMPT_PARTICLE_LIMIT = 4

#: `prompts.py::_compact_voice_style` 里 `closers` 的实际上限（条数）。
#: 2026-09-26 补进白名单之前它是**死数据**（41/44 个角色写了平均 3 条一条都没发出去）；
#: 现在是「超出的条数占位但不生效」，与 `PROMPT_PARTICLE_LIMIT` 同型。
PROMPT_CLOSERS_LIMIT = 4

#: 语气字候选。比 `prompts.py::_INTERJECTION_HEADS` 宽：后者是「能从 openers 抽出来当
#: 颗粒」的白名单（不含「嚯」「哪」「哟」），这里是**统计用**的字表，只关心原文里
#: 出现过什么，不预设哪个字合格。
#: 语气字统计表（**全文字频**用）。
#:
#: ⚠ **必须是 `prompts._INTERJECTION_HEADS` 的超集**，并有闸钉住
#: （`test_particle_chars_cover_every_interjection_head`）。两者不一致会造出一个
#: 静默的假结论：句首能当叹词、却不在本表里的字，全文频次永远记 0，
#: 于是声明它的角色会被判成「凭空写的字（high）」。
#: 实测踩过：「嗨」在语料里出现 **142 次**、句首 133 次，却因为不在表里，
#: 让 8 个角色被误报 high（「哈」129 次、「欸」7 次同理）。
PARTICLE_CHARS = "啊哦嗯呀嘿呃嘛吧呢啦噢哎唉唔咦哇嚯哪哟诶嗨欸哈"

#: 出声证据少于这个条数时中位数不稳定，标 `thin` 提醒而不是当判据用。
THIN_EVIDENCE_THRESHOLD = 30

_PAGE_BREAK = re.compile(r"#\$[a-z0-9]#")
#: `$h` `$s` `$6` 这类表情/延迟标记。**必须避开 `#$e#`**：`$e` 也长得像表情标记，
#: 直接删会把分页符破坏成 `##`。所以加负向后顾跳过 `#` 后面那个。
_EMOTE = re.compile(r"(?<!#)\$[a-z0-9]")

#: **带参数的**对话脚本指令：`$c <颜色>#` 换色、`$p <条件>#` 前置条件、`$1 <键>#`、
#: `$q` / `$r` 分支。参数**一定以空格开头** —— 这是和单字符标记的分界线：
#: `$h#$e#` 里的 `#` 属于后面的分页符而不是 `$h` 的参数，把它当参数吃掉会让
#: `#$e#` 退化成 `$e#`（实测这样造出 669 条 `#` 残留）。
_DIALOGUE_COMMAND = re.compile(r"#?\$(?:c|p|q|r|d|k|1)[ \t][^#\n]*#")

#: 互斥分支指令（`$q` 问句 / `$r` 各回答）。
_BRANCH_COMMAND = re.compile(r"#?\$(?:q|r)[ \t][^#\n]*#")


def _drop_branch_tail(text: str) -> str:
    """`$q` / `$r` 是**互斥分支**，不是连着的台词。

    只保留第一段、其余整段丢弃。否则「我不知道。我们会变成鬼魂。我们会上天堂。」
    会被当成一个人一口气说的话 —— 句长、语气字、样本全被污染。实测 215 条记录
    含这类指令（Abigail 的问句对白最多）。
    """

    spans = list(_BRANCH_COMMAND.finditer(text))
    if len(spans) > 1:
        return text[: spans[1].start()]
    return text
_BLANK = re.compile(r"[ \t]+")
_SENTENCE_SPLIT = re.compile(r"[。！？…\n]+")
#: 性别变体：`${子^女}$` 是「男用『子』、女用『女』」。prompt 里**没有玩家性别**
#: （见 `stardew-persona-addressing-field` 的结论），所以统计只能取第一个变体，
#: 并在报告里声明这个偏差。
_GENDER_VARIANT = re.compile(r"\$\{([^{}]*?)\^([^{}]*?)\}\$")
#: 未被解析的 i18n 引用 —— 它是**键名不是台词**。花括号数宽松：CP 用
#: `{{i18n:...}}`，别的 mod 会留单花括号 `{i18n:Wellwick.dialogue.Mon8}`。
_UNRESOLVED_I18N = re.compile(r"\{\{?\s*i18n\s*:", re.IGNORECASE)
#: 语料里可能残留、但**语义不明**的标记。不静默删除，只统计并上报。
_UNKNOWN_MARKERS = ("%", "*", "{", "}", "[", "]")

_ELLIPSIS = "\u2026"
_EXCLAMATION = "\uff01"
_QUESTION = "\uff1f"
_DASH = "\u2014"


def is_unresolved_i18n(text: object) -> bool:
    """文本是不是一条**没有解析出来**的 CP i18n 引用（键名，不是台词）。"""

    return bool(_UNRESOLVED_I18N.search(str(text if text is not None else "")))


def dialogue_text(record: Mapping[str, Any]) -> str:
    """取一条语料记录的**可读台词**。

    ⚠ **这是本管线最容易踩空的一处**：语料里的 `text` 保存的是 **CP 原始模板**
    （`corpus.py::_apply_i18n_resolution` 的设计是「原始 text 不被覆盖」），
    解析出来的中文在 `resolvedText`（20260923 批次里 8509/14063 条有）。

    只读 `text` 的后果不是报错，而是**看起来很正常的一堆数字**：SVE 角色
    （Sophia / Olivia / Victor / Claire / Lance / Andy …）的全部日常对白会被当成
    `{{i18n:Sophia.CharacterDialogue.001}}` 这类键名字符串统计，指纹于是写成
    「句长中位 35、语气字 0」—— 读起来像「这个角色说话很长、不用语气词」，
    实际是拿键名算的。**「语料里没有她的日常对白」这个结论就是这么做出来的。**
    """

    resolved = record.get("resolvedText")
    if isinstance(resolved, str) and resolved.strip() and not is_unresolved_i18n(resolved):
        return resolved
    raw = str(record.get("text") or "")
    return "" if is_unresolved_i18n(raw) else raw


def _replace_page_break(match: re.Match[str]) -> str:
    """`#$e#` 是分页符，语义等于换行 → 当句界。

    前后**任意一侧已经是句末标点**时都不能再补一个，否则会造出
    「你不这么觉得吗？。然而」这种双标点 —— 它既进样本，也会让分句多切一刀。
    两侧都要看：`#$e#` 写在对白中间时后面往往跟着「。」（实测 Evelyn 的
    「是小南瓜形状的哦#$e#。」会变成「哦。。」）。
    """

    before = match.string[match.start() - 1] if match.start() else ""
    after = match.string[match.end()] if match.end() < len(match.string) else ""
    if before in "。！？…\n" or after in "。！？…":
        return ""
    return "。"


def clean_dialogue_text(text: object) -> str:
    """清掉语料里残留的游戏标记 —— 这是管线原先整个缺掉的一环。

    - `#$e#` / `#$b#` 是**分页符**，语义等于换行，统一成句号当句界；
    - `$c` / `$p` / `$q` / `$r` / `$1` 是**对话脚本指令**，直接删；其中 `$q` / `$r`
      是互斥分支，只保留第一段（见 `_drop_branch_tail`）；
    - `${子^女}$` 是性别变体，取第一个（prompt 里没有玩家性别，见常量注释）；
    - `$h` `$s` `$6` 这类是表情/延迟标记，直接删；
    - `@` 是玩家名占位，语料里的实际读法就是「你」（与 `prompts._text` 一致）；
    - `|` 是**随机变体分隔**（原文随机取其一），统计只取第一个变体，避免把
      两个互斥的说法拼成一句话。

    **顺序有依赖，改之前先读这段：**
    ① 分支截断与指令删除要在表情标记之前 —— `$c 0.5#` 会被 `_EMOTE` 先啃掉 `$c`，
       之后就再也认不出这是一条指令了；
    ② 表情标记要在分页符之前 —— 原文里它常紧跟句末标点（`…去了。$6#$b#…`），
       若先处理分页符，它前面看到的是 `$6` 而不是标点，于是补一个句号，
       删掉 `$6` 之后就成了「去了。。」（实测 **290 条**记录命中）。
    """

    raw = str(text if text is not None else "")
    out = _drop_branch_tail(raw)
    out = _DIALOGUE_COMMAND.sub("", out)
    out = _EMOTE.sub("", out)
    out = _PAGE_BREAK.sub(_replace_page_break, out)
    out = out.split("|")[0]
    out = _GENDER_VARIANT.sub(lambda match: match.group(1), out)
    out = out.replace("@", "你")
    out = _BLANK.sub(" ", out)
    return out.strip()


def split_sentences(text: str) -> list[str]:
    """按句末标点分句。逗号**不**分句 —— 这里量的是「说出口的一句话」。"""

    return [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]


def residual_markers(texts: Iterable[str]) -> dict[str, int]:
    """统计语义不明的残留标记出现次数，供人工决定要不要清。"""

    counts: collections.Counter[str] = collections.Counter()
    for text in texts:
        for marker in _UNKNOWN_MARKERS:
            hits = text.count(marker)
            if hits:
                counts[marker] += hits
    return dict(counts)


def _percentile(values: Sequence[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction) - 1))
    return int(ordered[index])


def _length_block(lengths: Sequence[int]) -> dict[str, int]:
    if not lengths:
        return {"count": 0, "median": 0, "p90": 0, "min": 0, "max": 0}
    return {
        "count": len(lengths),
        "median": float(statistics.median(lengths)),
        "p90": _percentile(lengths, 0.9),
        "min": int(min(lengths)),
        "max": int(max(lengths)),
    }


def _rate(hits: int, total: int) -> float:
    return round(hits / total, 4) if total else 0.0


def phrase_counter(sentences: Sequence[str], *, min_count: int = 3) -> list[list[Any]]:
    """2~4 字高频片段。噪声大，只作为「他常挂嘴边什么」的候选，不作判据。"""

    phrases: collections.Counter[str] = collections.Counter()
    for sentence in sentences:
        body = re.sub(r"[，。！？…、；：\u2014\-—]", "", sentence)
        for size in (2, 3, 4):
            for start in range(len(body) - size + 1):
                phrase = body[start : start + size]
                if re.fullmatch(r"[\u4e00-\u9fff]+", phrase):
                    phrases[phrase] += 1
    return [[p, n] for p, n in phrases.most_common(40) if n >= min_count][:10]


def build_fingerprint(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """给**一个角色**的语料记录算语言指纹。

    `records` 是该角色在对话语料里的全部记录（`npcId` / `text` / `evidenceKind`）。
    """

    spoken: list[str] = []
    event: list[str] = []
    unresolved = 0
    for record in records:
        text = dialogue_text(record)
        if not text.strip():
            if str(record.get("evidenceKind") or "") in SPOKEN_EVIDENCE_KINDS:
                unresolved += 1
            continue
        if str(record.get("evidenceKind") or "") in SPOKEN_EVIDENCE_KINDS:
            spoken.append(text)
        else:
            event.append(text)

    cleaned = [clean_dialogue_text(text) for text in spoken]
    cleaned = [text for text in cleaned if text]
    sentences = [s for text in cleaned for s in split_sentences(text)]

    particles = collections.Counter(ch for text in cleaned for ch in text if ch in PARTICLE_CHARS)
    heads = collections.Counter(s[0] for s in sentences if s)

    utterance_lengths = [len(text) for text in cleaned]
    sentence_lengths = [len(s) for s in sentences]

    if len(cleaned) >= THIN_EVIDENCE_THRESHOLD:
        level = "spoken"
    elif cleaned:
        level = "thin"
    elif event:
        level = "event_only"
    else:
        level = "none"

    return {
        "spokenCount": len(cleaned),
        "eventCount": len(event),
        "unresolvedCount": unresolved,
        "evidenceLevel": level,
        "utteranceLength": _length_block(utterance_lengths),
        "sentenceLength": _length_block(sentence_lengths),
        "rates": {
            "ellipsis": _rate(sum(1 for t in cleaned if _ELLIPSIS in t), len(cleaned)),
            "exclamation": _rate(sum(1 for t in cleaned if _EXCLAMATION in t), len(cleaned)),
            "question": _rate(sum(1 for t in cleaned if _QUESTION in t), len(cleaned)),
            "dash": _rate(sum(1 for t in cleaned if _DASH in t), len(cleaned)),
        },
        # **全量**存，不截前 N 个：审计要判「某个语气字在原文里是不是 0 次」，
        # 只留 top10 会把排在第 11 位之后的真实用字误报成「凭想象写的」。
        "particles": [[ch, n] for ch, n in particles.most_common()],
        "sentenceHeads": [[ch, n] for ch, n in heads.most_common(6)],
        "phrases": phrase_counter(sentences),
        "samples": {
            "shortest": sorted(cleaned, key=len)[:8],
            "typical": _typical_samples(cleaned, 6),
        },
    }


def _typical_samples(texts: Sequence[str], count: int) -> list[str]:
    """取接近中位长度的发言 —— 最短的那批往往短到看不出语气。"""

    if not texts:
        return []
    median = statistics.median(len(t) for t in texts)
    ordered = sorted(texts, key=lambda t: abs(len(t) - median))
    return ordered[:count]


def persona_particles(voice_style: Mapping[str, Any]) -> list[str]:
    """人设声明的语气字（保持声明顺序 —— prompt 只取前几个，顺序有语义）。"""

    if not isinstance(voice_style, Mapping):
        return []
    raw = voice_style.get("speechParticleHints")
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def persona_voice_gaps(
    voice_style: Mapping[str, Any],
    fingerprint: Mapping[str, Any],
    *,
    particle_floor: int = 3,
) -> list[dict[str, str]]:
    """把「人设的语言层」与「原文指纹」的落差列成可执行的问题清单。

    只报**能算出来**的事实，不做文风判断。每条带 `code` / `severity` / `detail`。
    """

    if not isinstance(voice_style, Mapping):
        return []

    gaps: list[dict[str, str]] = []
    level = str(fingerprint.get("evidenceLevel") or "none")
    if level in {"none", "event_only"}:
        gaps.append(
            {
                "code": "no_spoken_evidence",
                "severity": "medium",
                "detail": (
                    f"出声证据 {fingerprint.get('spokenCount', 0)} 条"
                    f"（事件 {fingerprint.get('eventCount', 0)} 条）——"
                    "无法据此判断平时怎么说话，别用事件台词代替"
                ),
            }
        )
        return gaps

    counts = {
        str(char): int(n)
        for char, n in (fingerprint.get("particles") or [])
    }
    declared = persona_particles(voice_style)

    absent = [ch for ch in declared if counts.get(ch, 0) == 0]
    if absent:
        gaps.append(
            {
                "code": "particle_not_in_corpus",
                "severity": "high",
                "detail": f"声明了原文里 0 次的语气字 {'、'.join(absent)} —— 是凭想象写的",
            }
        )

    frequent = [ch for ch, n in counts.items() if n >= particle_floor][:5]
    missing = [ch for ch in frequent if ch not in declared]
    if missing:
        gaps.append(
            {
                "code": "particle_missing",
                "severity": "medium",
                "detail": (
                    f"原文高频语气字 {'、'.join(missing)} 没写进 speechParticleHints"
                    f"（原文计数 {' '.join(f'{c}{counts[c]}' for c in missing)}）"
                ),
            }
        )

    if len(declared) > PROMPT_PARTICLE_LIMIT:
        dropped = declared[PROMPT_PARTICLE_LIMIT:]
        gaps.append(
            {
                "code": "particle_over_prompt_limit",
                "severity": "medium",
                "detail": (
                    f"写了 {len(declared)} 个，prompt 只取前 {PROMPT_PARTICLE_LIMIT} 个 —— "
                    f"{'、'.join(dropped)} 不生效（要么删掉、要么把更该生效的排前面）"
                ),
            }
        )

    openers = voice_style.get("openers")
    opener_items = (
        [str(item) for item in openers if str(item).strip()]
        if isinstance(openers, (list, tuple))
        else []
    )
    if not declared and opener_items:
        heads = [item[0] for item in opener_items if item]
        extractable = [head for head in heads if head in INTERJECTION_HEADS]
        if not extractable:
            gaps.append(
                {
                    "code": "no_particle_anywhere",
                    "severity": "medium",
                    "detail": (
                        "speechParticleHints 为空，而 openers 首字都不是叹词 —— "
                        "语气颗粒的兜底提取会抽出空列表，prompt 里一个颗粒都没有"
                    ),
                }
            )

    if opener_items:
        median = float(fingerprint.get("utteranceLength", {}).get("median") or 0)
        p90 = float(fingerprint.get("utteranceLength", {}).get("p90") or 0)
        average = sum(len(item) for item in opener_items) / len(opener_items)
        if median and average > max(p90, median * 1.5):
            gaps.append(
                {
                    "code": "openers_longer_than_corpus",
                    "severity": "medium",
                    "detail": (
                        f"openers 平均 {average:.1f} 字，原文一条发言中位 {median:.0f} 字、"
                        f"P90 {p90:.0f} 字 —— 写成了他不会说的完整长句"
                    ),
                }
            )

    closers = [
        item for item in (voice_style.get("closers") or []) if isinstance(item, str)
    ]
    if len(closers) > PROMPT_CLOSERS_LIMIT:
        gaps.append(
            {
                "code": "closers_over_limit",
                "severity": "low",
                "detail": (
                    f"closers 写了 {len(closers)} 条，prompt 只取前 {PROMPT_CLOSERS_LIMIT} 条"
                    "（prompts.py::_compact_voice_style）—— 多写的占位但不生效"
                ),
            }
        )

    return gaps


def _clip(text: object, limit: int) -> str:
    """压成一行并截到上限 —— 上限与 `prompts._compact_voice_style` 的白名单一致，
    草稿超限会被下游静默砍掉，那正是本轮要消灭的那类坑。"""

    value = " ".join(str(text if text is not None else "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _length_phrase(block: Mapping[str, Any]) -> str:
    """句长锚点 —— 人设里最缺的一句话。"""

    median = int(block.get("median") or 0)
    p90 = int(block.get("p90") or 0)
    if median <= 0:
        return ""
    if p90 <= median:
        return f"一句话通常 {median} 字上下"
    return f"一句话通常 {median} 字上下，最多 {p90} 字左右"


#: 分句但**保留**句末标点 —— `split_sentences()` 会剥掉标点（统计用），
#: 但 openers 是给人看、直接进 prompt 的原话，少了「！」就不像台词了。
_SENTENCE_WITH_PUNCTUATION = re.compile(r"[^。！？…\n]+[。！？…]*")

#: 语料把玩家名 `@` 替换成了「你」，会留下「……这是令人兴奋的消息，你」这种读不通的尾巴。
_TRAILING_PLAYER_NAME = re.compile(r"[，,]\s*你\s*[。！？…]?$")


def _flavour(text: str) -> int:
    """一句话的「口吻浓度」—— 同等长度里优先挑有语气的那句。"""

    score = sum(1 for ch in text if ch in PARTICLE_CHARS)
    if _ELLIPSIS in text:
        score += 2
    if _EXCLAMATION in text:
        score += 1
    return score


def _pattern_second_line(fingerprint: Mapping[str, Any]) -> str:
    """句式第二条：**起句习惯**。只在真有据可依时才出，凑数没有意义。

    不能用高频词/高频短语来凑：`phrases` 里排前几的是「今天」「我们」「什么」
    这类通用词，对每个角色都一样 —— 那正是本轮要消灭的「写了等于没写」。
    """

    heads = [(str(ch), int(n)) for ch, n in fingerprint.get("sentenceHeads") or []]
    interjections = [ch for ch, _ in heads if ch in INTERJECTION_HEADS]
    if interjections:
        shown = "、".join(f"「{ch}」" for ch in interjections[:3])
        return f"常以{shown}这类语气字起句"
    for ch, count in heads:
        if ch == "（" and count >= 3:
            return "常在话里带动作或神态描写（常以括号起句）"
    return ""


def _opener_candidates(
    fingerprint: Mapping[str, Any], count: int, target_length: int
) -> list[str]:
    """挑开场原话。

    **只从 `typical` 挑**：`samples.shortest` 里是「我正在刷牙。」这类场景短句，
    既不有个性也不像开场，而且同一句会被语料采样到多次（Gus 的
    「我的庄稼很健康！」出现过 4 次）。长度对到**分句长度中位**上 ——
    `openers` 是一条开场的话，不是一整次发言（发言中位通常是它的三倍）。
    """

    pool: list[tuple[int, str]] = [
        (0, text) for text in (fingerprint.get("samples") or {}).get("typical") or []
    ]
    pool += [
        (1, text) for text in (fingerprint.get("samples") or {}).get("shortest") or []
    ]
    seen: set[str] = set()
    scored: list[tuple[int, int, int, int, str]] = []
    for source_rank, utterance in pool:
        for sentence in _SENTENCE_WITH_PUNCTUATION.findall(
            clean_dialogue_text(utterance)
        ):
            sentence = _clip(sentence, 60)
            if not 6 <= len(sentence) <= 45 or sentence in seen:
                continue
            seen.add(sentence)
            scored.append(
                (
                    # 带玩家名尾巴的句子**排最后**（而不是丢掉）：池子太小时宁可给一条
                    # 读起来别扭的原话，也不要让 openers 空着 —— 空着模型就会自己编。
                    1 if _TRAILING_PLAYER_NAME.search(sentence) else 0,
                    # 来源优先于长度：`shortest` 里是「我正在刷牙。」这类场景短句，
                    # 只有当 `typical` 凑不满时才轮得到它们。
                    source_rank,
                    abs(len(sentence) - target_length),
                    -_flavour(sentence),
                    sentence,
                )
            )
    scored.sort()
    return [sentence for *_, sentence in scored[:count]]


def _rate_phrase(rate: float, ladder: Sequence[tuple[float, str]]) -> str:
    for threshold, phrase in ladder:
        if rate >= threshold:
            return phrase
    return ""


_ELLIPSIS_LADDER = (
    (0.40, "四成以上的话带省略号"),
    (0.25, "将近三成的话带省略号"),
    (0.10, "偶尔用省略号"),
)
_EXCLAMATION_LADDER = (
    (0.40, "感叹号很多"),
    (0.20, "常带感叹号"),
    (0.08, "偶尔用感叹号"),
)


def suggest_voice_style(
    voice_style: Mapping[str, Any] | None,
    fingerprint: Mapping[str, Any],
    *,
    particle_limit: int = PROMPT_PARTICLE_LIMIT,
    opener_count: int = 4,
) -> dict[str, Any]:
    """按原文统计给 `voiceStyle` 生成**草稿** —— 只覆盖会进 prompt 的 4 个字段。

    **这是草稿不是成品**：`speechParticleHints` 与 `openers` 直接来自原文，可以照抄；
    `sentencePattern` 与 `tone` 是**数字堆出来的骨架**，必须由人改成人话
    （照抄会得到「一句话通常 11 字上下」这种说明书腔，而人设要的是角色的口吻）。

    `coreTraits` / `knowledgeRules` / `stageProfiles` / `avoid` / `preferredTopics`
    **一律不生成** —— 保持 ㊵ 的变量隔离：改完要能分清是哪一层在起作用。

    证据不足（`thin` / `event_only` / `none`）时**不出草稿**：那正是「凭想象写」的起点。
    """

    level = str(fingerprint.get("evidenceLevel") or "none")
    current = voice_style if isinstance(voice_style, Mapping) else {}
    current_view = {
        "tone": str(current.get("tone") or ""),
        "sentencePattern": list(current.get("sentencePattern") or []),
        "openers": list(current.get("openers") or []),
        "speechParticleHints": list(current.get("speechParticleHints") or []),
    }
    result: dict[str, Any] = {
        "evidenceLevel": level,
        "spokenCount": int(fingerprint.get("spokenCount") or 0),
        "current": current_view,
        "suggested": {},
        "notes": [],
    }
    if level not in {"spoken", "thin"}:
        result["notes"].append(
            "没有日常对白证据 —— 不出草稿（拿事件台词或想象填，正是要避免的错）"
        )
        return result

    particles = [str(ch) for ch, _ in fingerprint.get("particles") or []][:particle_limit]
    if particles:
        result["suggested"]["speechParticleHints"] = particles

    length_phrase = _length_phrase(fingerprint.get("sentenceLength") or {})
    second_line = _pattern_second_line(fingerprint)
    patterns = [phrase for phrase in (length_phrase, second_line) if phrase]
    if patterns:
        result["suggested"]["sentencePattern"] = [_clip(p, 65) for p in patterns[:2]]
    if len(patterns) < 2:
        # 静默少一条正是本轮的病因（写了看不出、没写也没人知道），所以要说出来。
        result["notes"].append(
            "句式只出一条：语料里没有可判定的起句习惯（叹词首字、括号描写都没有），"
            "第二条要自己写"
        )

    target_length = int((fingerprint.get("sentenceLength") or {}).get("median") or 0)
    openers = _opener_candidates(fingerprint, opener_count, target_length)
    if openers:
        result["suggested"]["openers"] = openers

    rates = fingerprint.get("rates") or {}
    tone_bits: list[str] = []
    ellipsis_phrase = _rate_phrase(float(rates.get("ellipsis") or 0.0), _ELLIPSIS_LADDER)
    if ellipsis_phrase:
        tone_bits.append(ellipsis_phrase)
    exclamation_phrase = _rate_phrase(
        float(rates.get("exclamation") or 0.0), _EXCLAMATION_LADDER
    )
    if exclamation_phrase:
        tone_bits.append(exclamation_phrase)
    if not tone_bits and length_phrase:
        # 标点习惯都不明显时，句长是唯一有据可依的语气线索。
        tone_bits.append(length_phrase)
    if tone_bits:
        result["suggested"]["tone"] = _clip("，".join(tone_bits), 120)

    if level == "thin":
        result["notes"].append(
            f"只有 {result['spokenCount']} 条出声证据（不足 {THIN_EVIDENCE_THRESHOLD} 条）"
            " —— 草稿只能当线索，别照抄"
        )
    changed = [
        key
        for key, value in result["suggested"].items()
        if value != current_view.get(key)
    ]
    result["changedFields"] = changed
    return result


def load_voice_fingerprints(path: str | Path) -> dict[str, Any]:
    """读入已生成的指纹数据（契约由 `tests/test_voice_fingerprints_data.py` 钉住）。"""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "speakers" not in payload:
        raise ValueError("指纹数据缺少 speakers 段")
    return payload
