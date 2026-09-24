from __future__ import annotations

from stardew_ai_bridge.dialogue_style_quality import analyze_dialogue_style


def test_detects_repeated_speech_particle_in_one_reply() -> None:
    # 这条回复同时犯两件事：同一个颗粒用了两次（重复），且 10 个字里带 2 个
    # （密度 20%，远超原文全库的 1.67%）。两个维度各自成立，不互相顶掉。
    result = analyze_dialogue_style("嗯，今天还行。嗯，没别的事。")

    assert "repeated_speech_particle" in result["tags"]
    assert "too_many_speech_particles" in result["tags"]
    assert result["speechParticleCounts"]["嗯"] == 2


def test_detects_particle_repeated_from_recent_turns() -> None:
    result = analyze_dialogue_style(
        "嗯，先这样吧。",
        history=[{"role": "assistant", "content": "嗯，今天挺忙。"}],
    )

    assert "repeated_speech_particle" in result["tags"]


def test_keeps_different_particles_and_plain_reply_clean() -> None:
    """本测试关心的是「**重复**」这个维度，不是总量。

    第二条用了两个**不同**的颗粒，所以不算重复；但它 10 个字里带 2 个，
    密度上确实过密——那是另一个维度（`too_many_speech_particles`），
    由 `test_speech_particle_density.py` 单独钉住。
    """

    assert analyze_dialogue_style("今天挺忙，晚点再说。")["tags"] == []
    assert analyze_dialogue_style("嗯，今天挺忙。啊，明天再看。")["tags"] == [
        "too_many_speech_particles"
    ]


def test_detects_repeated_opening_without_rewriting_reply() -> None:
    reply = "今天还行。"
    result = analyze_dialogue_style(
        reply,
        history=[{"role": "assistant", "content": "今天挺忙。"}],
    )

    assert "repeated_opening" in result["tags"]
    assert result["opening"] == "今天还行"


def test_ignores_non_assistant_history_and_keeps_output_redacted() -> None:
    result = analyze_dialogue_style(
        "哦，知道了。",
        history=[
            {"role": "user", "content": "嗯，今天怎么样？"},
            {"role": "assistant", "content": "昨天还行。"},
        ],
    )

    assert result["tags"] == []
    assert "prompt" not in result
    assert "apiKey" not in result
