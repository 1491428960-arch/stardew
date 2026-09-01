from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.local_benchmark import (
    DEFAULT_CASES,
    _SOURCE_MODS,
    build_case_messages,
    parse_ollama_stream_lines,
    score_reply,
    summarize_ollama_stream,
)
from stardew_ai_bridge.profile_index import ProfileIndexStore


def test_default_rasmodia_benchmark_covers_relationship_and_context_edges() -> None:
    case_ids = {case.case_id for case in DEFAULT_CASES}
    stages = {case.relationship_stage for case in DEFAULT_CASES}

    assert len(DEFAULT_CASES) >= 6
    assert {"stranger", "friend", "close", "married"} <= stages
    assert "same_day_follow_up" in case_ids
    assert "unknown_event_boundary" in case_ids


def test_default_cases_include_runtime_mod_ids_for_resolved_corpus_matching() -> None:
    assert "FlashShifter.StardewValleyExpandedCP" in _SOURCE_MODS
    assert "Parrot.RomRas" in _SOURCE_MODS


def test_build_case_messages_keeps_profile_state_and_history_context() -> None:
    case = next(item for item in DEFAULT_CASES if item.case_id == "same_day_follow_up")

    messages = build_case_messages(case)
    rendered = "\n".join(message["content"] for message in messages)

    assert messages[-1]["role"] == "user"
    assert "conversation_history" in {message.get("name") for message in messages}
    assert "同一天" in rendered or "咖啡" in rendered
    assert "Rasmodia" in rendered or "Wizard" in rendered


def test_build_case_messages_uses_the_selected_profile_index(tmp_path: Path) -> None:
    index_path = tmp_path / "resolved-profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": [],
                "speechEvidence": [
                    {
                        "sampleId": "wizard-benchmark-1",
                        "npcId": "Wizard",
                        "sourceMod": "Romanceable Rasmodius",
                        "sourceKey": "wizard_friend_voice",
                        "text": "我会把星界观测记在今晚的研究日志里。",
                        "evidenceKind": "dialogue",
                        "conditions": {"relationshipStage": "friend"},
                    }
                ],
                "storyEvents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    case = next(item for item in DEFAULT_CASES if item.case_id == "friend_voice")

    messages = build_case_messages(case, profile_index=ProfileIndexStore(index_path))
    rendered = "\n".join(message["content"] for message in messages)

    assert "speech_evidence" in {message.get("name") for message in messages}
    assert "星界观测" in rendered


def test_score_reply_marks_forbidden_meta_text_and_unknown_fact_boundary() -> None:
    case = next(item for item in DEFAULT_CASES if item.case_id == "unknown_event_boundary")

    score = score_reply(
        case,
        "作为 AI，我已经完成了这个仪式，<think>先解释一下</think>。",
    )

    assert score["forbiddenHits"] >= 2
    assert score["passed"] is False


def test_score_reply_accepts_a_constrained_in_character_answer() -> None:
    case = next(item for item in DEFAULT_CASES if item.case_id == "unknown_event_boundary")

    score = score_reply(case, "这件事我不能确定，也没有可以核对的记录。")

    assert score["forbiddenHits"] == 0
    assert score["expectedHits"] >= 1
    assert score["passed"] is True


def test_cases_with_expected_terms_require_at_least_one_match_by_default() -> None:
    case = next(item for item in DEFAULT_CASES if item.case_id == "friend_voice")

    score = score_reply(case, "今天的天气很平静，我暂时没有更多可说的。")

    assert case.min_expected_hits == 1
    assert score["expectedHits"] == 0
    assert score["passed"] is False


def test_unknown_event_case_rejects_unconfirmed_completion_claim() -> None:
    case = next(item for item in DEFAULT_CASES if item.case_id == "unknown_event_boundary")

    score = score_reply(case, "深夜仪式已经完成，而且我已经确认了结果。")

    assert score["forbiddenHits"] >= 1
    assert score["passed"] is False


def test_unknown_event_case_accepts_explicit_non_ritual_reframe() -> None:
    case = next(item for item in DEFAULT_CASES if item.case_id == "unknown_event_boundary")

    score = score_reply(case, "那不是传统意义上的仪式，只是一次例行检查。")

    assert score["forbiddenHits"] == 0
    assert score["expectedHits"] >= 1
    assert score["passed"] is True


def test_summarize_ollama_stream_extracts_latency_and_generation_metrics() -> None:
    events = [
        {"message": {"role": "assistant", "content": "你好"}},
        {"message": {"role": "assistant", "content": "，旅行者。"}},
        {
            "done": True,
            "eval_count": 20,
            "eval_duration": 4_000_000_000,
            "load_duration": 120_000_000,
            "prompt_eval_count": 80,
            "prompt_eval_duration": 200_000_000,
        },
    ]

    summary = summarize_ollama_stream(
        events,
        total_latency_ms=1234,
        first_content_latency_ms=231,
    )

    assert summary["reply"] == "你好，旅行者。"
    assert summary["firstContentLatencyMs"] == 231
    assert summary["totalLatencyMs"] == 1234
    assert summary["evalCount"] == 20
    assert summary["evalDurationMs"] == 4000.0
    assert summary["tokensPerSecond"] == 5.0
    assert summary["loadDurationMs"] == 120.0
    assert summary["promptEvalCount"] == 80
    assert summary["promptEvalDurationMs"] == 200.0


def test_parse_ollama_stream_lines_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="invalid Ollama stream event"):
        parse_ollama_stream_lines(['{"message": {"content": "ok"}}', "not-json"])
