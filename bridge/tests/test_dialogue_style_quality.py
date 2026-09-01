from __future__ import annotations

from stardew_ai_bridge.dialogue_style_quality import analyze_dialogue_style


def test_detects_repeated_speech_particle_in_one_reply() -> None:
    result = analyze_dialogue_style("嗯，今天还行。嗯，没别的事。")

    assert result["tags"] == ["repeated_speech_particle"]
    assert result["speechParticleCounts"]["嗯"] == 2


def test_detects_particle_repeated_from_recent_turns() -> None:
    result = analyze_dialogue_style(
        "嗯，先这样吧。",
        history=[{"role": "assistant", "content": "嗯，今天挺忙。"}],
    )

    assert "repeated_speech_particle" in result["tags"]


def test_keeps_different_particles_and_plain_reply_clean() -> None:
    assert analyze_dialogue_style("今天挺忙，晚点再说。")["tags"] == []
    assert analyze_dialogue_style("嗯，今天挺忙。啊，明天再看。")["tags"] == []


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
