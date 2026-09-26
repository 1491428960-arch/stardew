"""语言指纹管线的单元测试。

这一层守三件事：

1. **取值口径** —— 从语料记录里取「台词」时必须读 `resolvedText`。语料的 `text`
   保存的是 Content Patcher 的**未解析模板**（`{{i18n:Sophia.CharacterDialogue.001}}`），
   只读 `text` 不会报错，只会把 SVE 角色的全部日常对白变成一串键名去统计，
   于是指纹写成「句长中位 35、语气字 0」—— 看起来像结论，实际是垃圾。
2. **清理口径** —— 分页符当句界、性别变体取第一支、随机变体取第一支、`@` → 你。
3. **审计口径** —— 「人设写了原文里 0 次的语气字」必须报出来；prompt 只取前 4 个
   语气字这件事必须由**真实 prompt 函数**证明，不能靠人记住。
"""

from __future__ import annotations

from stardew_ai_bridge import prompts
from stardew_ai_bridge.voice_fingerprint import (
    INTERJECTION_HEADS,
    PARTICLE_CHARS,
    PROMPT_PARTICLE_LIMIT,
    build_fingerprint,
    clean_dialogue_text,
    dialogue_text,
    is_unresolved_i18n,
    persona_voice_gaps,
    split_sentences,
    suggest_voice_style,
)


def _record(text: str, *, kind: str = "dialogue", resolved: str | None = None) -> dict:
    record: dict = {"text": text, "evidenceKind": kind}
    if resolved is not None:
        record["resolvedText"] = resolved
    return record


# --- 取值口径：text 是模板，resolvedText 才是台词 ---------------------------------


def test_unresolved_i18n_reference_is_detected() -> None:
    assert is_unresolved_i18n("{{i18n:Sophia.CharacterDialogue.001}}")
    assert is_unresolved_i18n("{{ i18n : Andy.Thing }}")
    assert not is_unresolved_i18n("呀！有陌生人！")


def test_dialogue_text_prefers_resolved_text_over_the_raw_template() -> None:
    """**本次的核心回归闸**：读 `text` 会把键名当台词，读 `resolvedText` 才对。"""

    record = _record(
        "{{i18n:Sophia.CharacterDialogue.001}}",
        resolved="呀！有陌生人！等、等一下。",
    )
    assert dialogue_text(record) == "呀！有陌生人！等、等一下。"


def test_dialogue_text_drops_a_template_that_was_never_resolved() -> None:
    assert dialogue_text(_record("{{i18n:Nobody.Never.001}}")) == ""


def test_a_plain_record_keeps_its_own_text() -> None:
    assert dialogue_text(_record("早上好。")) == "早上好。"


def test_unresolved_records_are_counted_not_silently_dropped() -> None:
    """取不到台词要计数 —— 静默丢弃正是这条管线之前的毛病。"""

    records = [
        _record("{{i18n:A.B.001}}"),
        _record("真台词一。"),
        _record("真台词二。"),
    ]
    fingerprint = build_fingerprint(records)
    assert fingerprint["spokenCount"] == 2
    assert fingerprint["unresolvedCount"] == 1


# --- 清理口径 ---------------------------------------------------------------------


def test_page_breaks_become_sentence_boundaries() -> None:
    cleaned = clean_dialogue_text("你好。#$e#再见。")
    # 分句会吃掉句末标点（统计的是字，不是标点）
    assert split_sentences(cleaned) == ["你好", "再见"]


def test_a_page_break_after_punctuation_does_not_double_it() -> None:
    """`？` 后面紧跟分页符时不该补句号 —— 否则样本里全是「？。」。"""

    assert (
        clean_dialogue_text("你不这么觉得吗？#$e#然而我七天都在上班。")
        == "你不这么觉得吗？然而我七天都在上班。"
    )


def test_gender_variant_keeps_the_first_branch() -> None:
    """prompt 里没有玩家性别，统计只能取第一支（并在报告里声明这个偏差）。"""

    assert clean_dialogue_text("你好，${先生^女士}$。") == "你好，先生。"


def test_random_variant_keeps_the_first_branch() -> None:
    assert clean_dialogue_text("今天天气不错。|今天下雨。") == "今天天气不错。"


def test_player_name_placeholder_reads_as_you() -> None:
    assert clean_dialogue_text("你好，@。") == "你好，你。"


def test_emote_markers_are_removed() -> None:
    assert clean_dialogue_text("我很高兴。$h$1") == "我很高兴。"


def test_sentence_length_is_measured_after_splitting() -> None:
    """一条长发言会被拆成多句 —— 只报整条长度会得出「他说话 40 字」的错印象。"""

    record = _record("你好呀。今天天气不错。嗯。")
    fingerprint = build_fingerprint([record])
    assert fingerprint["utteranceLength"]["count"] == 1  # 一条发言
    assert fingerprint["sentenceLength"]["count"] == 3  # 三句话
    assert fingerprint["sentenceLength"]["median"] == 3.0  # 3 / 6 / 1 字
    assert fingerprint["sentenceLength"]["max"] == 6


# --- 证据分级 ---------------------------------------------------------------------


def test_event_dialogue_is_not_spoken_evidence() -> None:
    records = [_record("事件里的一句话。", kind="event_dialogue")]
    fingerprint = build_fingerprint(records)
    assert fingerprint["spokenCount"] == 0
    assert fingerprint["eventCount"] == 1
    assert fingerprint["evidenceLevel"] == "event_only"
    gaps = persona_voice_gaps({"openers": ["你好。"]}, fingerprint)
    assert [gap["code"] for gap in gaps] == ["no_spoken_evidence"]


def test_marriage_and_extra_dialogue_count_as_spoken_evidence() -> None:
    for kind in ("dialogue", "marriage_dialogue", "extra_dialogue"):
        fingerprint = build_fingerprint([_record("嗯，好啊。", kind=kind)])
        assert fingerprint["spokenCount"] == 1, kind


def test_thin_evidence_is_flagged() -> None:
    fingerprint = build_fingerprint([_record("嗯。") for _ in range(3)])
    assert fingerprint["evidenceLevel"] == "thin"


# --- 审计口径 ---------------------------------------------------------------------


def _corpus_fingerprint(particles: str, *, times: int = 5) -> dict:
    text = "".join(f"{ch}今天天气不错。" for ch in particles) * times
    return build_fingerprint([_record(text)])


def test_a_declared_particle_absent_from_the_corpus_is_high_severity() -> None:
    fingerprint = _corpus_fingerprint("啊嘿吧")
    gaps = persona_voice_gaps({"speechParticleHints": ["啊", "哦"]}, fingerprint)
    codes = [gap["code"] for gap in gaps]
    assert "particle_not_in_corpus" in codes
    detail = next(g["detail"] for g in gaps if g["code"] == "particle_not_in_corpus")
    assert "哦" in detail


def test_a_frequent_particle_missing_from_the_persona_is_reported() -> None:
    fingerprint = _corpus_fingerprint("啊嘿吧")
    gaps = persona_voice_gaps({"speechParticleHints": ["啊"]}, fingerprint)
    detail = next(g["detail"] for g in gaps if g["code"] == "particle_missing")
    assert "嘿" in detail and "吧" in detail


def test_declaring_more_particles_than_prompt_keeps_is_reported() -> None:
    fingerprint = _corpus_fingerprint("啊嘿吧嗯嘛嚯")
    gaps = persona_voice_gaps(
        {"speechParticleHints": ["啊", "嘿", "吧", "嗯", "嘛", "嚯"]}, fingerprint
    )
    detail = next(g["detail"] for g in gaps if g["code"] == "particle_over_prompt_limit")
    assert "嘛" in detail and "嚯" in detail


def test_empty_particles_with_no_interjection_opener_leaves_no_grain() -> None:
    gaps = persona_voice_gaps(
        {"speechParticleHints": [], "openers": ["最近小镇还算平稳。"]},
        _corpus_fingerprint("啊"),
    )
    assert "no_particle_anywhere" in [gap["code"] for gap in gaps]


def test_openers_written_longer_than_the_corpus_are_reported() -> None:
    fingerprint = build_fingerprint([_record("嗯。") for _ in range(40)])
    gaps = persona_voice_gaps(
        {"openers": ["你好，最近小镇还算平稳，我正好在整理一些事务。"]}, fingerprint
    )
    assert "openers_longer_than_corpus" in [gap["code"] for gap in gaps]


def test_closers_beyond_the_prompt_limit_are_reported() -> None:
    """2026-09-26：`closers` 已补进 prompt 白名单，不再是死字段。

    体检改成报「写多了不生效」—— 超出的条数占位但发不出去，
    与 `speechParticleHints` 第 5 个起不生效同型。
    """

    gaps = persona_voice_gaps(
        {"closers": ["一。", "二。", "三。", "四。", "五。"], "speechParticleHints": ["啊"]},
        _corpus_fingerprint("啊"),
    )
    assert "closers_over_limit" in [gap["code"] for gap in gaps]


# --- 与 prompt 的一致性（用真实函数证明，不靠人记住） ------------------------------


def test_prompt_really_keeps_only_four_particles() -> None:
    """`PROMPT_PARTICLE_LIMIT` 必须与 `prompts._compact_voice_style` 的实际行为一致。

    这一条是「写了 6 个语气字，实际只有 4 个生效」的闸 —— 两处一旦分叉，
    审计就会开始说假话。
    """

    compacted = prompts._compact_voice_style(
        {"speechParticleHints": ["啊", "嘿", "吧", "嗯", "嘛", "嚯"]}
    )
    assert compacted["speechParticleHints"] == ["啊", "嘿", "吧", "嗯"]
    assert len(compacted["speechParticleHints"]) == PROMPT_PARTICLE_LIMIT


def test_interjection_heads_are_shared_with_prompts() -> None:
    """叹词表是同一个对象 —— 抄第二份就会让审计和线上分叉。"""

    assert INTERJECTION_HEADS is prompts._INTERJECTION_HEADS


def test_particle_chars_cover_every_interjection_head() -> None:
    """语气字表必须是叹词表的**超集**。

    两者不一致会造出一个静默的假结论：句首能当叹词、却不在语气字表里的字，
    全文频次永远记 0，于是声明它的角色被判成「凭空写的字（high）」。
    实测踩过：「嗨」在语料里 142 次、句首 133 次，却因不在表里让 8 个角色误报
    （「哈」129 次、「欸」7 次同理）。
    """

    missing = set(INTERJECTION_HEADS) - set(PARTICLE_CHARS)
    assert not missing, f"这些叹词在全文语气字统计里记 0 次：{sorted(missing)}"


# --- 草稿生成：只覆盖会进 prompt 的 4 个字段 --------------------------------------


#: 每条 10~20 字、带语气字的日常台词 —— 拿来当「像样的语料」。
_LINES = [
    "嘿，来点喝的吧。",
    "啊，真是美味佳肴。",
    "哎，今天可真够忙的。",
    "哦，你也这么觉得吗？",
    "嗯……我想想再说。",
]


def _fingerprint_from(texts: list[str], *, kind: str = "dialogue") -> dict:
    return build_fingerprint([_record(text, kind=kind) for text in texts])


def test_draft_covers_only_the_four_prompt_fields() -> None:
    """`coreTraits` / `knowledgeRules` 这些行为层字段**不许**出现在草稿里 ——
    变量隔离是 ㊵ 的前提：改完要能分清是哪一层在起作用。"""

    draft = suggest_voice_style(
        {"coreTraits": ["勤劳"], "knowledgeRules": ["知道镇上事"]},
        _fingerprint_from(_LINES * 8),
    )
    assert set(draft["suggested"]) <= {
        "tone",
        "sentencePattern",
        "openers",
        "speechParticleHints",
    }


def test_particles_follow_corpus_frequency_and_stop_at_the_prompt_limit() -> None:
    texts = ["啊，好啊。", "啊，行吧。", "啊……嗯。", "嘿，哦。"]
    draft = suggest_voice_style({}, _fingerprint_from(texts))
    particles = draft["suggested"]["speechParticleHints"]
    assert particles[0] == "啊"
    assert len(particles) <= PROMPT_PARTICLE_LIMIT


def test_draft_respects_every_prompt_limit() -> None:
    """草稿超限会被 `_compact_voice_style` 静默砍掉 —— 那正是本轮要消灭的坑。"""

    draft = suggest_voice_style({}, _fingerprint_from(_LINES * 8))
    suggested = draft["suggested"]
    assert len(suggested["tone"]) <= 120
    assert all(len(item) <= 65 for item in suggested["sentencePattern"])
    assert all(len(item) <= 60 for item in suggested["openers"])
    assert all(len(item) <= 12 for item in suggested["speechParticleHints"])


def test_openers_are_real_lines_keeping_their_punctuation() -> None:
    """openers 是**分句后的一句话**，所以可能是某条原话的一段 —— 但必须真的出自语料，
    且带着台词该有的标点（`split_sentences` 会剥标点，那是统计用的口径，不能拿来当台词）。"""

    draft = suggest_voice_style({}, _fingerprint_from(_LINES * 8))
    openers = draft["suggested"]["openers"]
    assert openers
    assert all(any(line in source for source in _LINES) for line in openers)
    assert all(line.endswith(("。", "！", "？", "…")) for line in openers)


def test_openers_prefer_the_line_with_voice_over_the_flat_one() -> None:
    """同等长度里优先挑带语气的 —— 否则会挑出「我正在刷牙。」这类场景短句。"""

    flat = "我今天去镇上买东西。"  # 10 字，零语气字
    vivid = "哎，我今天去镇上啊。"  # 10 字，两个语气字
    draft = suggest_voice_style({}, _fingerprint_from([flat, vivid]))
    assert draft["suggested"]["openers"][0] == vivid


def test_a_line_ending_in_the_player_name_placeholder_is_ranked_last() -> None:
    """语料把 `@` 换成了「你」，会留下读不通的尾巴 —— 排最后，但池子够时不入选。"""

    normal = "哎，今天真不错啊。"
    awkward = "回星露谷再见，你。"
    draft = suggest_voice_style(
        {}, _fingerprint_from([normal, awkward] + _LINES * 8)
    )
    assert normal in draft["suggested"]["openers"]
    assert awkward not in draft["suggested"]["openers"]


def test_no_draft_without_spoken_evidence() -> None:
    """事件台词与想象都不是「他平时怎么说话」的证据 —— 那正是要避免的错。"""

    fingerprint = build_fingerprint([_record("镇长的开场白。", kind="event_dialogue")])
    draft = suggest_voice_style({}, fingerprint)
    assert draft["suggested"] == {}
    assert draft["notes"]


def test_thin_evidence_draft_warns_against_copying_it() -> None:
    draft = suggest_voice_style({}, _fingerprint_from(_LINES))
    assert draft["evidenceLevel"] == "thin"
    assert any("别照抄" in note for note in draft["notes"])


def test_a_single_pattern_line_says_the_second_one_is_on_you() -> None:
    """少一条就少一条，但要说出来 —— 静默缺失正是这轮查出来的那类病。"""

    fingerprint = _fingerprint_from(["我今天去镇上。", "你看见了吗。", "这个不错。"])
    draft = suggest_voice_style({}, fingerprint)
    assert len(draft["suggested"]["sentencePattern"]) == 1
    assert any("第二条要自己写" in note for note in draft["notes"])


def test_drafting_from_the_draft_reports_no_further_change() -> None:
    """幂等：拿草稿再跑一遍，应该没有可改的了（否则人审时看不出该看哪条）。"""

    fingerprint = _fingerprint_from(_LINES * 8)
    first = suggest_voice_style({}, fingerprint)
    second = suggest_voice_style(first["suggested"], fingerprint)
    assert second["changedFields"] == []


def test_a_page_break_before_punctuation_does_not_double_it() -> None:
    """`#$e#` 的**两侧**都要看 —— 只修前面会留下「哦。。」。

    实测出处：Evelyn 的「是小南瓜形状的哦#$e#。」被草稿原样带出来，
    说明上一次只修了「前面已有标点」那一半。
    """

    assert clean_dialogue_text("是小南瓜形状的哦#$e#。") == "是小南瓜形状的哦。"
    assert clean_dialogue_text("你不这么觉得吗？#$e#然而") == "你不这么觉得吗？然而"


def test_openers_prefer_the_typical_pool_over_the_shortest_one() -> None:
    """`shortest` 是「我正在刷牙。」这类场景短句 —— 只有 `typical` 凑不满时才轮到它。"""

    typical_ish = [
        "嘿，今天可真够忙的啊。",
        "啊，我正准备收摊呢。",
        "哎，你也来一杯吧。",
        "嗯……我想想该怎么说。",
        "哦，那可真不错啊！",
        "吧台这边还有位置。",
    ]
    short_only = "嘿，你好啊。"
    draft = suggest_voice_style({}, _fingerprint_from(typical_ish + [short_only]))
    openers = draft["suggested"]["openers"]
    assert len(openers) >= 4
    assert short_only not in openers


def test_the_draft_never_contains_doubled_punctuation() -> None:
    draft = suggest_voice_style({}, _fingerprint_from(["是小南瓜形状的哦#$e#。"] * 8))
    for line in draft["suggested"]["openers"]:
        assert "。。" not in line


def test_a_dialogue_command_is_removed() -> None:
    """`$c 0.5#` / `$p 17#` / `#$1 Abigail1#` 是脚本指令，不是台词。"""

    assert (
        clean_dialogue_text("$c 0.5#哇……我最喜欢这个颜色了！")
        == "哇……我最喜欢这个颜色了！"
    )
    assert clean_dialogue_text("$p 17#你是不是认为什么都不会发生？") == (
        "你是不是认为什么都不会发生？"
    )
    assert clean_dialogue_text("#$1 Abigail1#今天晚上估计要由我爸下厨了。") == (
        "今天晚上估计要由我爸下厨了。"
    )


def test_branching_answers_keep_only_the_first_branch() -> None:
    """`$q` / `$r` 是**互斥**分支 —— 全拼在一起会变成「一个人一口气说完三个回答」。"""

    raw = (
        "要是在墓地里待上一整夜会发生什么事呢？"
        "#$q 17/18 Sun_old#你觉得我们死后会变成什么样？"
        "#$r 17 0 Sun_17#我不知道。"
        "#$r 18 40 Sun_18#我们会变成鬼魂。"
    )
    cleaned = clean_dialogue_text(raw)
    assert "要是在墓地里待上一整夜会发生什么事呢？" in cleaned
    assert "我不知道" not in cleaned
    assert "我们会变成鬼魂" not in cleaned


def test_the_page_break_survives_the_command_rule() -> None:
    """`$e#` / `$b#` 不能被指令规则吃掉 —— 它是句界，吃掉了整段就并成一句。"""

    assert clean_dialogue_text("你好。$6#$b#再见。") == "你好。再见。"
    assert clean_dialogue_text("你好#$e#再见") == "你好。再见"
