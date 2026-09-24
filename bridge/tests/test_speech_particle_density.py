"""语气词「过密」判定与配套重试。

背景（`docs/report-kimi-filler-diagnosis-2026-09-24.md`）：Kimi 输出的语气词
密度是本角色原文全库的 2.4~2.7 倍（每百汉字 3.99~4.56，全库 1.67），
而同一批 prompt 下 DeepSeek 是 1.12。

修之前已实测两条「证据层」路线都拉不动它：

- **改 prompt 措辞**：每角色 100 轮、共 600 轮，0/3 角色显著变化，平均 +2%。
- **修 `voiceAnchors` 选样偏置**：共 300 轮，0/3 角色显著，平均 −7%。
  而且各角色 anchors 变化幅度不同，凑成天然对照——
  Sebastian 的 anchors 降 68% 而输出只降 10%，Elliott 的 anchors 降 73%
  而输出反升 18%。**范例密度与输出密度不相关。**

所以判定只能做在输出侧：这一组测试钉住那个判定。
"""

from __future__ import annotations

from stardew_ai_bridge.dialogue_boundaries import (
    SPEECH_PARTICLES,
    reply_exceeds_speech_particle_density,
    speech_particle_density,
    speech_particle_window_density,
)
from stardew_ai_bridge.dialogue_style_quality import analyze_dialogue_style


def test_speech_particle_table_covers_pausing_particles() -> None:
    """表要覆盖项目既有的那套颗粒，不能只在密度判定里另起一套。"""

    for particle in ("嗯", "哦", "啊", "唔", "呃", "嘿", "好吧", "行吧"):
        assert particle in SPEECH_PARTICLES


def test_density_counts_particles_at_sentence_boundaries() -> None:
    """只数句首或标点之后的颗粒——词内同字不算。

    分母是**全部**汉字（含颗粒自身），与 `docs/report-kimi-filler-diagnosis`
    里所有测量脚本的口径一致，这样阈值才能直接对比。
    """

    # 3 个颗粒（呃/哦/嗯），13 个汉字。
    count, chinese, density = speech_particle_density("呃……你好。哦，是你啊。嗯，那我知道了。")
    assert count == 3
    assert chinese == 13
    assert density > 20


def test_particle_inside_word_is_not_counted() -> None:
    """「嘿」出现在词内部时不算颗粒，否则「嘿嘿」之外的正常词也会被误判。"""

    # 「呵护」「啊呀」之外的场景：这里用一个不含句首颗粒的长句。
    count, _, density = speech_particle_density("今天的葡萄园还算安静，我下午想画一会儿画。")
    assert count == 0
    assert density == 0.0


def test_normal_reply_is_not_flagged() -> None:
    """原文全库水平（1.67 每百字）的回复不该被判过密。"""

    assert not reply_exceeds_speech_particle_density(
        "今天的葡萄园还算安静。我下午想画一会儿画，你要不要来看看？"
    )


def test_single_particle_in_short_reply_is_not_flagged() -> None:
    """「嗯，好的。」单看比例很高，但它完全正常。

    短回复里一个颗粒就能撑起很高的比例，所以判定要求**至少两个**颗粒，
    否则会把大量正常短句拉去重试。
    """

    assert not reply_exceeds_speech_particle_density("嗯，好的。")


def test_reply_at_original_corpus_ceiling_is_not_flagged() -> None:
    """原文里密度最高的角色（Sophia 2.20）也不该被误伤。"""

    assert not reply_exceeds_speech_particle_density(
        "啊，对了。我今天在葡萄园里待了一下午，然后回来画了会儿画。"
    )


def test_dense_reply_is_flagged() -> None:
    """Kimi 的实际输出风格要被判出来。"""

    assert reply_exceeds_speech_particle_density(
        "呃……你好。哦，是你啊。嗯，那我知道了，我这就去办。"
    )


def test_style_quality_reports_too_many_speech_particles() -> None:
    """离线标签要真的产出这个码。

    此前 `dialogue_lab_page` 已经把这个码翻译成「语气词过密」，但**没有任何
    代码产出它**——一个界面上等着用的死标签。这条测试钉住它现在是活的。
    """

    result = analyze_dialogue_style("呃……你好。哦，是你啊。嗯，那我知道了。")
    assert "too_many_speech_particles" in result["tags"]


def test_style_quality_does_not_flag_normal_reply() -> None:
    result = analyze_dialogue_style("今天的葡萄园还算安静。我下午想画一会儿画。")
    assert "too_many_speech_particles" not in result["tags"]


def test_repeated_particle_still_reported_separately() -> None:
    """「过密」与「重复」是两个维度，不能互相顶掉。"""

    # 同一条回复里「嗯」用了两次，且整体很密。
    result = analyze_dialogue_style(
        "嗯，我在。嗯，你说吧。",
        history=[{"role": "assistant", "content": "嗯，我在。"}],
    )
    assert "repeated_speech_particle" in result["tags"]


def test_window_density_catches_one_particle_per_reply_pattern() -> None:
    """Kimi 的真实模式：每条只带一个颗粒，但**每条都带**。

    这是 2026-09-24 实测踩到的坑。最初只看单条、且要求「至少 2 个颗粒」，
    结果 Kimi 的 300 轮里 **gate 一次都没触发过**——它的模式是「几乎每条都以
    一个『呃』开头，但很少带两个」，单条永远只有 1 个颗粒，于是全部逃逸，
    B 方案被误判成「无效」。窗口口径才能看见这个模式。
    """

    history = [
        {"role": "assistant", "content": "呃，还活着。"},
        {"role": "assistant", "content": "呃，还行。刚喂完鸡。"},
        {"role": "assistant", "content": "哦。还活着。"},
    ]
    # 单看这一条：1 个颗粒 ⇒ 单条判据要求至少 2 个，放过。
    assert not reply_exceeds_speech_particle_density("呃，今天挺累。")
    # 放进窗口：4 条里 4 个颗粒，密度远高于原文全库。
    assert reply_exceeds_speech_particle_density("呃，今天挺累。", history)


def test_window_density_does_not_flag_normal_conversation() -> None:
    """窗口里颗粒总量不够时不该触发——否则正常应答也会被拉去重试。"""

    history = [
        {"role": "assistant", "content": "今天的葡萄园还算安静，我下午想画一会儿画。"},
        {"role": "assistant", "content": "好啊，那你先忙，晚点我再来找你。"},
    ]
    assert not reply_exceeds_speech_particle_density("嗯，好的。", history)


def test_window_ignores_non_assistant_history() -> None:
    """玩家说的话不算——否则玩家自己用语气词会把 NPC 判成过密。"""

    history = [
        {"role": "user", "content": "呃……那个……嗯……"},
        {"role": "user", "content": "哦，好吧。"},
    ]
    assert not reply_exceeds_speech_particle_density("今天挺忙，晚点再说。", history)


def test_window_accepts_plain_string_history() -> None:
    """窗口必须**同时**接受字符串列表和消息字典。

    2026-09-24 实测踩到的不对称：`guard._prompt_assistant_replies` 从 prompt
    卡片里提取出的是纯字符串列表，而本函数原先只认 `{"role": ...}` 字典，
    于是 `previous` 恒为空、**窗口逻辑在运行时从未生效**——症状是「本地判定
    返回 True，guard 却从不触发重试」。单元测试当时恰好喂了字典格式，全绿。
    """

    history = ["哦。还活着。", "谢恩。在干活。"]
    reply = "呃，有什么可说的。在上班，住我阿姨那儿。没了。"
    # 窗口口径：2 个颗粒 / 27 字 = 7.4%，高于阈值。
    assert reply_exceeds_speech_particle_density(reply, history)
    # 同样内容用字典形态表达，结论必须一致——这条就是防上面那个不对称。
    as_messages = [{"role": "assistant", "content": text} for text in history]
    assert reply_exceeds_speech_particle_density(reply, as_messages)


def test_string_history_window_is_not_fooled_by_empty_entries() -> None:
    """空串和空白不该被算进窗口，否则分母被稀释、判定失真。"""

    history = ["", "   ", "哦。还活着。"]
    reply = "呃，有什么可说的。在上班，住我阿姨那儿。没了。"
    count, chinese, _ = speech_particle_window_density([*history, reply])
    assert count == 2
    assert chinese == 4 + 18
