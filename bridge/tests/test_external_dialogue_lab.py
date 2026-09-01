from __future__ import annotations

import re
import subprocess

from fastapi.testclient import TestClient

import stardew_ai_bridge.app as app_module
from stardew_ai_bridge.app import app


def _function_body(html: str, function_name: str) -> str:
    marker = f"function {function_name}("
    start = html.index(marker)
    opening_brace = html.index("{", start)
    depth = 0
    for index in range(opening_brace, len(html)):
        if html[index] == "{":
            depth += 1
        elif html[index] == "}":
            depth -= 1
            if depth == 0:
                return html[opening_brace : index + 1]
    raise AssertionError(f"未找到 {function_name} 函数结束位置")


def _chat_html() -> str:
    return TestClient(app).get("/test/chat").text


def test_default_external_lab_prioritizes_case_browser() -> None:
    response = TestClient(app).get("/test")

    assert response.status_code == 200
    html = response.text
    for marker in (
        'id="test-case-browser"',
        'id="case-list"',
        'id="case-detail"',
        'id="coverage-panel"',
        'href="/test/chat"',
        "/api/quality/cases",
        "地点 / 时间 / 天气",
        "剧情进度",
        'id="message-input"',
        'id="raw-dialogue-filter"',
    ):
        assert marker in html


def test_case_browser_exposes_affinity_stage_filters_and_style_quality_labels() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        'data-filter="high_affinity"',
        'data-filter="close"',
        'data-filter="married"',
        'id="filter-high-affinity-count"',
        'id="coverage-high-affinity"',
        "relationshipStageLabel",
        "friendshipHearts",
        "repeated_speech_particle",
        "styleQuality",
    ):
        assert marker in html


def test_dialogue_lab_routes_return_one_integrated_workspace() -> None:
    expected_views = {
        "/test": "cases",
        "/test/chat": "chat",
        "/raw": "raw",
    }

    for route, default_view in expected_views.items():
        html = TestClient(app).get(route).text

        assert html.count('id="dialogue-lab-workspace"') == 1
        assert f'data-default-view="{default_view}"' in html
        for view in ("cases", "chat", "raw"):
            assert f'data-view-target="{view}"' in html
            assert f'data-workspace-view="{view}"' in html
        assert html.count('id="npc-select"') == 1
        assert html.count('id="raw-npc-select"') == 1


def test_integrated_workspace_switches_views_without_route_navigation() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "function showWorkspaceView(",
        "event.preventDefault()",
        "history.replaceState",
        'data-workspace-view="cases"',
        'data-workspace-view="chat"',
        'data-workspace-view="raw"',
    ):
        assert marker in html


def test_existing_chat_lab_remains_available_under_chat_route() -> None:
    response = TestClient(app).get("/test/chat")

    assert response.status_code == 200
    assert 'id="message-input"' in response.text
    assert 'id="send"' in response.text


def test_shared_ui_dialogue_lab_pages_share_the_same_workspace_shell() -> None:
    routes = {"/test": "cases", "/test/chat": "chat", "/raw": "raw"}

    for route, default_view in routes.items():
        response = TestClient(app).get(route)

        assert response.status_code == 200
        html = response.text
        assert 'data-ui-shell="v4"' in html
        assert 'class="workspace-nav"' in html
        assert 'href="/test"' in html
        assert 'href="/test/chat"' in html
        assert 'href="/raw"' in html
        assert 'aria-current="page"' in html
        assert "--ui-shell-version: 4;" in html
        nav = re.search(r'<nav class="workspace-nav".*?</nav>', html, flags=re.DOTALL)
        assert nav is not None
        assert re.findall(
            r'<a class="workspace-tab" href="([^"]+)" data-view-target="([^"]+)"',
            nav.group(0),
        ) == [
            ("/test", "cases"),
            ("/test/chat", "chat"),
            ("/raw", "raw"),
        ]
        assert f'data-default-view="{default_view}"' in html
        assert re.search(
            rf'data-view-target="{default_view}"[^>]*aria-current="page"',
            nav.group(0),
        )


def test_integrated_workspace_uses_one_versioned_shell_and_content_frame() -> None:
    html = TestClient(app).get("/test").text

    assert 'data-ui-shell="v4"' in html
    assert 'class="dialogue-lab-shell"' in html
    assert html.count('class="workspace-content"') == 1
    assert html.count('class="workspace-view ') == 3
    assert "workspace-view-heading" in html
    assert "--ui-shell-version: 4;" in html


def test_integrated_workspace_injects_canonical_shell_only_once() -> None:
    html = TestClient(app).get("/test").text

    assert html.count('data-ui-shell="v4"') == 1


def test_integrated_workspace_gives_each_view_the_same_title_region() -> None:
    html = TestClient(app).get("/test").text

    assert html.count('class="workspace-view-heading"') == 3
    assert '<div class="heading">' not in html
    assert '<h1>测试例浏览</h1>' in html
    assert '<h1>单次聊天</h1>' in html
    assert '<h1>原始对白参照</h1>' in html
    assert html.count("--ui-shell-version: 4;") == 1
    assert html.count("grid-template-columns:minmax(220px,1fr) auto auto") == 1
    assert "--ui-shell-version: 2;" not in html


def test_integrated_case_view_matches_shared_reading_scale_and_control_density() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        r'#dialogue-lab-workspace \[data-workspace-view="cases"\]\s*\{\s*font-size:12px;',
        r'#dialogue-lab-workspace \[data-workspace-view="cases"\] \.case-title \{\s*font-size:12px;',
        r'#dialogue-lab-workspace \[data-workspace-view="cases"\] \.case-meta \{\s*font-size:10px;',
        r'#dialogue-lab-workspace \[data-workspace-view="cases"\] \.scene-value \{\s*font-size:12px;',
        r'#dialogue-lab-workspace \[data-workspace-view="cases"\] \.panel-body,[\s\S]*?padding:12px 13px;',
        r'#dialogue-lab-workspace \[data-workspace-view="cases"\] \.case-row \{\s*padding:8px 10px;',
        r'#dialogue-lab-workspace \[data-workspace-view="cases"\] \.filter-btn \{\s*padding:8px 10px;',
        r'#dialogue-lab-workspace \[data-workspace-view="cases"\] \.nav-note \{\s*font-size:11px;',
        r'#dialogue-lab-workspace \[data-workspace-view="cases"\] \.detail-block h3 \{\s*font-size:13px;',
        r'#dialogue-lab-workspace \[data-workspace-view="cases"\] \.coverage-intro \{\s*font-size:11px;',
        r'#dialogue-lab-workspace \[data-workspace-view="cases"\] \.history \{\s*font-size:12px;',
    ):
        assert re.search(marker, html)


def test_integrated_case_view_adapts_detail_columns_before_mobile_stack() -> None:
    html = TestClient(app).get("/test").text

    assert '#dialogue-lab-workspace [data-workspace-view="cases"] .browser-layout' in html
    assert "grid-template-columns:minmax(240px,.85fr) minmax(0,2fr) minmax(260px,.95fr)" in html
    assert '#dialogue-lab-workspace [data-workspace-view="cases"] .detail-panel .panel-body' in html
    assert '#dialogue-lab-workspace [data-workspace-view="cases"] .prompt-card' in html


def test_integrated_view_specific_css_targets_real_view_attributes() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        '#dialogue-lab-workspace [data-workspace-view="raw"] { overflow:auto;',
        '#dialogue-lab-workspace [data-workspace-view="raw"] > .toolbar',
        '#dialogue-lab-workspace [data-workspace-view="raw"] .raw-dialogue-list',
        '#dialogue-lab-workspace [data-workspace-view="chat"] .transcript-panel',
    ):
        assert marker in html
    assert "#dialogue-lab-workspace #view-cases" not in html
    assert "#dialogue-lab-workspace #view-chat" not in html
    assert "#dialogue-lab-workspace #view-raw" not in html


def test_integrated_raw_view_has_a_compressible_scroll_chain() -> None:
    html = TestClient(app).get("/test").text

    assert re.search(
        r'#dialogue-lab-workspace \[data-workspace-view="raw"\] > '
        r'\.reference-grid \{[^}]*grid-template-rows:minmax\(0,1fr\);',
        html,
    )
    assert re.search(
        r'#dialogue-lab-workspace \[data-workspace-view="raw"\] > '
        r'\.reference-grid > \.reference-section \{[^}]*min-height:0;'
        r'[^}]*display:flex;[^}]*flex-direction:column;[^}]*overflow:hidden;',
        html,
    )
    assert re.search(
        r'#dialogue-lab-workspace \[data-workspace-view="raw"\] '
        r'\.raw-dialogue-list \{[^}]*flex:1;[^}]*min-height:0;'
        r'[^}]*max-height:none;[^}]*overflow-y:auto;',
        html,
    )


def test_standalone_raw_view_keeps_each_reference_list_scrollable() -> None:
    html = TestClient(app).get("/raw").text

    assert (
        '.reference-section { min-width:0; min-height:0; display:flex; '
        'flex-direction:column; overflow:hidden;'
    ) in html
    assert re.search(
        r'\.reference-section \.raw-dialogue-list \{[^}]*flex:1;'
        r'[^}]*min-height:0;[^}]*max-height:none;[^}]*overflow-y:auto;',
        html,
    )


def test_shared_ui_keeps_chat_accessible_on_narrow_viewports() -> None:
    html = _chat_html()

    assert "@media (max-width:700px)" in html
    assert "body { overflow:auto; }" in html
    assert re.search(r"\.layout[^\{]*\{[^\}]*grid-template-columns:1fr;", html)


def test_quality_case_browser_exposes_case_navigation_and_detail_rendering() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "async function loadQualityCases(",
        "function renderCaseList(",
        "function renderCaseDetail(",
        "function applyCaseFilter(",
        "expectedTerms",
        "forbiddenTerms",
        "history",
        "playerInput",
    ):
        assert marker in html


def test_quality_case_browser_embedded_javascript_is_syntactically_valid() -> None:
    html = TestClient(app).get("/test").text
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)

    assert scripts
    for script in scripts:
        result = subprocess.run(
            ["node", "--check", "--input-type=commonjs"],
            input=script,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr


def test_quality_cases_endpoint_exposes_sanitized_existing_cases() -> None:
    response = TestClient(app).get("/api/quality/cases")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == 1
    assert payload["source"] == "character_quality_eval.DEFAULT_CASES"
    assert len(payload["cases"]) >= 15
    case = next(item for item in payload["cases"] if item["caseId"] == "wizard-follow-up")
    assert case["npcId"] == "Wizard"
    assert case["relationshipStage"] == "friend"
    assert case["channel"] == "face_to_face"
    assert case["playerInput"] == "那第三组现在稳定了吗？"
    assert case["history"]
    assert "expectedTerms" in case
    assert "forbiddenTerms" in case


def test_quality_results_endpoint_exposes_latest_sanitized_generated_batch(
    tmp_path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "20260830-guard-markdown"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        '{"schemaVersion":1,"caseCount":1,"successful":1,"errors":0,"passed":0,"elapsedMs":99,"profileIndex":"E:/private/index.json"}',
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        '{"caseId":"wizard-daily","reply":"塔里的灰尘还没积够层数。","provider":"local","fallback":false,"latencyMs":42,"score":{"passed":false,"tags":["format_noise"]},"prompt":"敏感 prompt","apiKey":"secret","token":"secret"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "quality_artifact_root", tmp_path, raising=False)

    response = TestClient(app).get("/api/quality/results")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == 1
    assert payload["batchId"] == run_dir.name
    assert payload["summary"]["passed"] == 0
    assert payload["results"][0]["reply"] == "塔里的灰尘还没积够层数。"
    serialized = response.text
    assert "敏感 prompt" not in serialized
    assert "apiKey" not in serialized
    assert "secret" not in serialized


def test_quality_results_preserve_safe_style_quality_labels_only(
    tmp_path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "20260901-style-quality"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        '{"schemaVersion":2,"caseCount":1,"successful":1,"errors":0,"passed":0}',
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        '{"caseId":"demo-case","reply":"嗯，今天还行。","styleQuality":'
        '{"tags":["repeated_speech_particle","secret"],"speechParticleCounts":'
        '{"嗯":2,"bad":"nope","token":999},"opening":"嗯","prompt":"secret prompt"}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "quality_artifact_root", tmp_path, raising=False)

    response = TestClient(app).get("/api/quality/results")

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["styleQuality"] == {
        "tags": ["repeated_speech_particle", "secret"],
        "speechParticleCounts": {"嗯": 2},
        "opening": "嗯",
    }
    assert "secret prompt" not in response.text


def test_case_browser_loads_and_renders_real_quality_results() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "/api/quality/results",
        "state.results",
        "resultByCaseId",
        "实际生成回复",
        "format_noise",
        "renderCaseResult",
    ):
        assert marker in html


def test_case_browser_renders_multiturn_transcript_and_usage_summary() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "function renderCaseTranscript(",
        "result.turns",
        "turn.playerInput",
        "turn.reply",
        "turn.usage",
        "totalTokens",
        "usageReturnedTurns",
        "missingUsageTurns",
        "estimatedCost",
        "用量未返回",
    ):
        assert marker in html


def test_case_browser_keeps_preloaded_history_before_generated_turns() -> None:
    html = TestClient(app).get("/test").text

    render_body = _function_body(html, "renderCaseTranscript")
    for marker in (
        "item.history",
        "result.turns",
        "turn.playerInput",
        "turn.reply",
        "预置上下文",
    ):
        assert marker in render_body or marker in html


def test_case_browser_labels_quality_batch_by_actual_provider() -> None:
    html = TestClient(app).get("/test").text

    assert "batchProviderLabel" in html
    assert 'cloud:"云端（显式）"' in html
    assert 'local:"本地 qwen3.5:9b"' in html
    assert "Object.values(state.results)" in html


def test_quality_cases_expose_scene_matrix_for_manual_review() -> None:
    response = TestClient(app).get("/api/quality/cases")
    cases = response.json()["cases"]

    assert all(
        {
            "season",
            "date",
            "weather",
            "time",
            "location",
            "friendshipHearts",
        } <= set(item["gameState"])
        and item["storyProgress"]
        for item in cases
    )
    assert len({item["gameState"]["location"] for item in cases}) >= 4
    assert len({item["gameState"]["weather"] for item in cases}) >= 3
    assert len({item["storyProgress"] for item in cases}) >= 3


def test_case_browser_renders_scene_and_story_progress_for_selected_case() -> None:
    html = TestClient(app).get("/test").text

    assert "item.gameState" in html
    assert "item.storyProgress" in html
    assert "场景条件" in html
    assert "剧情进度" in html


def test_case_browser_exposes_composite_review_controls() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        'id="case-search"',
        'id="case-search-clear"',
        'id="case-role-filter"',
        'id="case-status-filter"',
        'data-filter="needs_review"',
        "caseMatchesSearch",
        "statusMatches",
        "state.query",
        "state.roleFilter",
        "state.statusFilter",
    ):
        assert marker in html


def test_case_browser_persists_case_list_view_state_in_url() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "function readCaseViewState(",
        "function updateCaseViewUrl(",
        'searchParams.get("case")',
        'searchParams.set("case"',
        'searchParams.set("q"',
        'searchParams.set("role"',
        'searchParams.set("status"',
        "history.replaceState",
    ):
        assert marker in html


def test_case_browser_provides_adjacent_case_navigation_and_review_focus() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        'toolbar.className = "case-detail-toolbar"',
        'data-case-nav="previous"',
        'data-case-nav="next"',
        'data-case-nav="review"',
        "function moveSelectedCase(",
        "function focusNextReviewCase(",
        "case-detail-toolbar",
        "position:sticky",
    ):
        assert marker in html


def test_case_browser_makes_long_detail_sections_collapsible() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "function makeDetailSectionsCollapsible(",
        "detail-section-toggle",
        "detail-section-content",
        "content.hidden",
        "预置上下文",
    ):
        assert marker in html


def test_external_lab_exposes_three_panel_controls() -> None:
    html = _chat_html()

    for marker in (
        'id="scene-panel"',
        'id="transcript"',
        'id="diagnostics-panel"',
        'id="provider-mode"',
        'id="send"',
        'id="topic"',
        'id="clear-session"',
        'id="export-session"',
    ):
        assert marker in html


def test_external_lab_displays_and_restores_single_chat_usage() -> None:
    html = _chat_html()

    for marker in (
        'id="usage-value"',
        "function formatUsage(",
        "data?.usage",
        "usage:normalizeUsage",
        "lastDiagnostics:normalizeDiagnostics(state.lastDiagnostics)",
    ):
        assert marker in html


def test_external_lab_exposes_explicit_cloud_provider_mode() -> None:
    html = _chat_html()

    assert 'value="cloud"' in html
    assert '<option value="cloud" selected>云端（显式，当前配置）</option>' in html


def test_external_lab_defaults_to_explicit_cloud_provider() -> None:
    html = _chat_html()

    assert '<option value="cloud" selected>云端（显式，当前配置）</option>' in html
    assert '<option value="auto">自动（本地 → 云端 → 兜底）</option>' in html


def test_external_lab_sends_explicit_provider_selection() -> None:
    html = _chat_html()
    build_payload_body = _function_body(html, "buildPayload")

    assert 'payload.provider=$("provider-mode").value' in build_payload_body


def test_external_lab_exposes_remote_and_face_to_face_channel_control() -> None:
    html = _chat_html()

    assert 'id="conversation-channel"' in html
    assert 'value="remote"' in html
    assert 'value="face_to_face"' in html


def test_external_lab_sends_selected_conversation_channel() -> None:
    html = _chat_html()
    build_payload_body = _function_body(html, "buildPayload")

    assert 'channel:$("conversation-channel").value' in build_payload_body


def test_external_lab_script_builds_contextual_multi_turn_requests() -> None:
    html = _chat_html()

    for marker in (
        "/api/npcs",
        "/api/context/preview",
        "/api/dialogue/test",
        "history",
        "gameState",
        "friendshipHearts",
        "shiftKey",
        "messages",
        "provider-mode",
    ):
        assert marker in html
    assert "发送 Fake 对话" not in html


def test_external_lab_defaults_to_runtime_mod_ids_for_source_specific_evidence() -> None:
    html = _chat_html()

    assert "Parrot.RomRas" in html
    assert "FlashShifter.SVECode" in html


def test_external_lab_can_show_selected_speech_evidence_source() -> None:
    html = _chat_html()

    assert "speechEvidence" in html
    assert "原文证据来源" in html


def test_external_lab_keeps_input_on_request_failure() -> None:
    html = _chat_html()

    assert "messageInput.value" in html
    assert "finally" in html
    assert "正在保留" in html or "保留输入" in html


def test_external_lab_uses_versioned_local_bridge_session_api() -> None:
    html = _chat_html()
    save_body = _function_body(html, "saveSession")

    assert "/api/dialogue/session" in html
    assert "fetch(\"/api/dialogue/session\"" in save_body
    assert "method:\"PUT\"" in save_body
    assert "version" in save_body
    assert "state.messages" in save_body
    assert "state.history" in save_body
    assert "state.lastDiagnostics" in save_body
    assert "localStorage" not in html


def test_external_lab_saves_session_after_successful_reply() -> None:
    html = _chat_html()
    send_body = _function_body(html, "sendDialogue")

    assert "await saveSession();" in send_body
    assert send_body.index("updateDiagnostics") < send_body.index("await saveSession")


def test_external_lab_loads_session_before_initial_render() -> None:
    html = _chat_html()

    assert "function loadSession(" in html
    assert "await loadSession();" in html
    assert html.index("await loadSession();") < html.index("Promise.all([loadNpcs(),loadHealth()])")


def test_external_lab_clear_session_removes_persisted_session() -> None:
    html = _chat_html()
    clear_body = _function_body(html, "clearSession")

    assert "fetch(\"/api/dialogue/session\"" in clear_body
    assert "method:\"DELETE\"" in clear_body


def test_external_lab_handles_session_load_failure_without_breaking_page() -> None:
    html = _chat_html()
    load_body = _function_body(html, "loadSession")

    assert "fetch(\"/api/dialogue/session\"" in load_body
    assert "catch" in load_body
    assert "state.messages=[]" in load_body


def test_external_lab_keeps_batch_transcripts_separate_by_npc() -> None:
    html = _chat_html()
    send_body = _function_body(html, "sendDialogue")

    assert "npcId" in send_body
    assert "historyForNpc" in html
    assert "message.npcId" in html
    assert "state.history=historyForNpc" in html


def test_external_lab_retains_five_character_batch_for_refresh_review() -> None:
    html = _chat_html()
    normalize_body = _function_body(html, "normalizeMessages")

    assert "slice(-400)" in normalize_body


def test_external_lab_does_not_force_css_zoom_at_normal_browser_scale() -> None:
    html = _chat_html()

    assert "body { margin: 0; min-height: 100vh; overflow:hidden;" in html
    assert ".app { height:100vh;" in html
    assert ".layout { display:grid; flex:1; min-height:0;" in html
    assert ".transcript-panel { display:flex; flex-direction:column; min-height:0;" in html
    assert ".transcript { flex:1; min-height:0;" in html
    assert "zoom:.76;" not in html
    assert "height:calc(100vh / .76)" not in html


def test_external_lab_keeps_quick_switches_visible_in_narrow_browser() -> None:
    html = _chat_html()
    mobile_start = html.index('@media (max-width:700px)')
    mobile_css = html[mobile_start : html.index('</style>', mobile_start)]

    assert ".layout { display:grid;" in mobile_css
    assert "grid-template-columns:minmax(130px" in mobile_css
    assert ".npc-buttons {" in mobile_css
    assert "#npc-buttons { display:none" not in mobile_css
    assert "#diagnostics-panel { grid-column:auto; }" in mobile_css


def test_integrated_workspace_exposes_one_shared_context_bar() -> None:
    html = TestClient(app).get("/test").text

    assert 'data-ui-shell="v4"' in html
    assert html.count('class="workspace-contextbar"') == 1
    for marker in (
        'id="context-character"',
        'id="context-case"',
        'id="context-scene"',
        'id="context-story"',
        'id="context-channel"',
        "当前评测上下文",
    ):
        assert marker in html


def test_case_selection_is_shared_with_chat_view() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "function selectCase(",
        "dialogue-lab:case-selected",
        "data-open-case-chat",
        "function applyQualityCase(",
        "dialogue-lab:apply-case",
        "window.DialogueLab",
    ):
        assert marker in html


def test_raw_npc_selection_is_shared_with_chat_view() -> None:
    html = TestClient(app).get("/raw").text

    for marker in (
        "dialogue-lab:npc-selected",
        "selectNpc(",
        "window.DialogueLab",
        'id="raw-npc-select"',
    ):
        assert marker in html


def test_chat_view_applies_case_scene_history_and_channel_as_one_context() -> None:
    html = _chat_html()

    apply_body = _function_body(html, "applyQualityCase")
    for marker in (
        'relationship-stage',
        'conversation-channel',
        'recent-facts',
        'gameState',
        'initialHistory',
    ):
        assert marker in apply_body or marker in html


def test_external_lab_reloads_saved_session_when_switching_npc() -> None:
    html = _chat_html()
    load_npcs_body = _function_body(html, "loadNpcs")

    assert "select.addEventListener(\"change\",async()=>{await loadSession();" in load_npcs_body


def test_external_lab_exposes_direct_npc_switch_buttons() -> None:
    html = _chat_html()
    load_npcs_body = _function_body(html, "loadNpcs")

    assert 'id="npc-buttons"' in html
    assert "function switchNpc(" in html
    assert "button.dataset.npcId" in html
    assert "renderNpcButtons()" in load_npcs_body
    assert "switchNpc(npcId)" in html


def test_external_lab_distinguishes_full_npc_catalog_from_evaluation_shortcuts() -> None:
    html = _chat_html()
    load_npcs_body = _function_body(html, "loadNpcs")

    assert 'data-npc-catalog="all"' in html
    assert "全部可聊天 NPC" in html
    assert "state.npcs=(await response.json()).npcs||[]" in load_npcs_body
    assert "npc.sourceMods" in load_npcs_body
    assert "本次评测角色只是快捷入口" in html


def test_external_lab_shortcuts_use_the_five_batch_characters_in_fixed_order() -> None:
    html = _chat_html()
    render_body = _function_body(html, "renderNpcButtons")

    assert (
        'const EVALUATION_NPC_IDS = ["Wizard", "Sophia", "Shane", "Sebastian", "Alex"];'
        in html
    )
    assert '"Rasmodia / Wizard"' in html
    assert '"Alex"' in html
    assert "npcIdsForButtons()" in render_body
    assert "state.npcs.slice(0,5)" not in html
    assert "本次评测角色" in html
    assert "当前角色没有已保存记录" in html


def test_external_lab_shortcuts_use_independent_source_presets() -> None:
    html = _chat_html()

    assert "EVALUATION_PROFILES" in html
    for source_mod in (
        "Romanceable Rasmodius",
        "Parrot.RomRas",
        "FlashShifter.SVECode",
        "Invatorzen.idcsm",
        "female.bachelors.beach",
        "vanilla",
    ):
        assert source_mod in html
    assert "setRuntimeSourceDefaults" not in html
    assert "sourceMods:profile.sourceMods" in html


def test_external_lab_canonicalizes_legacy_rasmodia_messages_to_wizard() -> None:
    html = _chat_html()

    normalize_body = _function_body(html, "normalizeMessages")
    history_body = _function_body(html, "historyForNpc")

    assert "canonicalNpcId" in html
    assert "npcId:canonicalNpcId" in normalize_body
    assert "canonicalNpcId(item.npcId)===canonicalNpcId(npcId)" in history_body
    assert "npcId:\"Wizard\"" in html


def test_external_lab_does_not_use_browser_storage_for_session() -> None:
    html = _chat_html()

    assert "/api/dialogue/session" in html
    assert "localStorage" not in html
    assert "async function loadSession(" in html
    assert "async function saveSession(" in html


def test_external_lab_exposes_raw_dialogue_reference_panel() -> None:
    html = TestClient(app).get("/raw").text

    for marker in (
        'id="raw-dialogue-page"',
        'id="raw-dialogue-list"',
        'id="raw-dialogue-representatives"',
        'id="raw-dialogue-filter"',
        "原始对白参照",
        "置顶代表对白",
        "全部原始对白",
    ):
        assert marker in html


def test_external_lab_links_to_standalone_raw_dialogue_page() -> None:
    html = _chat_html()

    assert 'href="/raw"' in html
    assert "原始对白参照" in html
    assert 'id="raw-dialogue-panel"' not in html
    assert 'data-view-target="raw"' in html
    assert 'id="raw-dialogue-page"' in html
    assert "function loadRawDialogue(" in html


def test_standalone_raw_dialogue_page_has_its_own_reference_layout() -> None:
    response = TestClient(app).get("/raw")
    html = response.text

    assert response.status_code == 200
    for marker in (
        'id="raw-dialogue-page"',
        'id="raw-dialogue-list"',
        'id="raw-dialogue-representatives"',
        'id="raw-dialogue-filter"',
        "原始对白参照",
        "置顶代表对白",
        "全部原始对白",
        'href="/test"',
    ):
        assert marker in html
    assert "最多 16 条" in html
    assert 'fetch(`/api/dialogue/raw?npcId=${encodeURIComponent(npcId)}`)' in html
    assert "function loadRawDialogue(" in html


def test_external_lab_loads_and_renders_raw_dialogue_by_selected_npc() -> None:
    html = TestClient(app).get("/raw").text

    assert 'fetch(`/api/dialogue/raw?npcId=${encodeURIComponent(npcId)}`)' in html
    assert "function loadRawDialogue(" in html
    assert "function renderRawDialogue(" in html
    render_body = _function_body(html, "renderRawDialogue")
    entry_body = _function_body(html, "renderRawDialogueList")
    assert "data.representatives" in render_body
    assert "data.dialogues" in render_body
    assert "representatives" in render_body
    assert "dialogues" in render_body
    assert "sourcePath" in entry_body
    assert "sourceKey" in entry_body


def test_external_lab_refreshes_raw_dialogue_when_switching_npc() -> None:
    html = TestClient(app).get("/raw").text

    assert 'id="raw-npc-select"' in html
    assert 'id="raw-npc-buttons"' in html
    assert "function renderQuickButtons(" in html
    assert "function loadNpcs(" in html
    assert "loadRawDialogue(select.value)" in html


def test_external_lab_raw_dialogue_does_not_enter_generation_payload() -> None:
    html = _chat_html()
    build_payload_body = _function_body(html, "buildPayload")

    assert "rawDialogue" not in build_payload_body
    assert "raw-dialogue" not in build_payload_body


def test_external_lab_raw_dialogue_endpoint_returns_references_without_prompt_fields(
    monkeypatch,
) -> None:
    class ReferenceStore:
        def dialogue_reference(self, npc_id):
            assert npc_id == "Rasmodia"
            return {
                "npcId": "Wizard",
                "total": 1,
                "representatives": [
                    {
                        "sampleId": "sample-1",
                        "npcId": "Wizard",
                        "sourceMod": "vanilla",
                        "sourcePath": "Characters/Dialogue/Wizard.json",
                        "sourceKey": "Mon",
                        "text": "今天还好。",
                        "evidenceKind": "dialogue",
                    }
                ],
                "dialogues": [
                    {
                        "sampleId": "sample-1",
                        "npcId": "Wizard",
                        "sourceMod": "vanilla",
                        "sourcePath": "Characters/Dialogue/Wizard.json",
                        "sourceKey": "Mon",
                        "text": "今天还好。",
                        "evidenceKind": "dialogue",
                    }
                ],
            }

    monkeypatch.setattr(app_module, "profile_index_store", ReferenceStore())
    response = TestClient(app).get("/api/dialogue/raw?npcId=Rasmodia")

    assert response.status_code == 200
    payload = response.json()
    assert payload["npcId"] == "Wizard"
    assert payload["total"] == 1
    assert payload["representatives"][0]["text"] == "今天还好。"
    assert "prompt" not in response.text
    assert "apiKey" not in response.text


def test_external_lab_session_api_filters_sensitive_fields(monkeypatch) -> None:
    class MemorySessionStore:
        def __init__(self) -> None:
            self.value = None

        def load(self):
            return self.value

        def save(self, value):
            self.value = value

        def clear(self):
            self.value = None

    store = MemorySessionStore()
    monkeypatch.setattr(app_module, "dialogue_lab_session_store", store, raising=False)
    client = TestClient(app)
    payload = {
        "version": 1,
        "messages": [{"role": "user", "text": "你好", "npcId": "Rasmodia"}],
        "history": [{"role": "user", "content": "你好"}],
        "lastDiagnostics": {"provider": "local", "reply": "你好。"},
        "apiKey": "should-not-persist",
        "token": "should-not-persist",
        "prompt": "should-not-persist",
        "lastPayload": {"message": "should-not-persist"},
    }

    response = client.put("/api/dialogue/session", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "version": 1,
        "messages": payload["messages"],
        "history": payload["history"],
        "lastDiagnostics": payload["lastDiagnostics"],
    }
    assert "should-not-persist" not in repr(store.value)


def test_external_lab_session_api_round_trips_saved_session(monkeypatch) -> None:
    class MemorySessionStore:
        def __init__(self) -> None:
            self.value = None

        def load(self):
            return self.value or {
                "version": 1,
                "messages": [],
                "history": [],
                "lastDiagnostics": None,
            }

        def save(self, value):
            self.value = value

        def clear(self):
            self.value = None

    store = MemorySessionStore()
    monkeypatch.setattr(app_module, "dialogue_lab_session_store", store, raising=False)
    client = TestClient(app)
    payload = {
        "version": 1,
        "messages": [{"role": "npc", "text": "欢迎。", "npcId": "Wizard"}],
        "history": [{"role": "assistant", "content": "欢迎。"}],
        "lastDiagnostics": {"provider": "local", "reply": "欢迎。"},
    }

    saved = client.put("/api/dialogue/session", json=payload)
    loaded = client.get("/api/dialogue/session")

    assert saved.status_code == 200
    assert loaded.status_code == 200
    assert loaded.json() == payload


def test_external_lab_session_api_clears_local_session(monkeypatch) -> None:
    class MemorySessionStore:
        def __init__(self) -> None:
            self.cleared = False

        def load(self):
            return {"version": 1, "messages": [], "history": [], "lastDiagnostics": None}

        def save(self, value):
            del value

        def clear(self):
            self.cleared = True

    store = MemorySessionStore()
    monkeypatch.setattr(app_module, "dialogue_lab_session_store", store, raising=False)

    response = TestClient(app).delete("/api/dialogue/session")

    assert response.status_code == 200
    assert response.json() == {"status": "cleared"}
    assert store.cleared is True


def test_external_lab_session_path_can_be_configured_without_using_repo_artifacts(
    monkeypatch,
) -> None:
    resolved = app_module.resolve_dialogue_session_path(
        "C:/local/stardew-session.json"
    )
    default_resolved = app_module.resolve_dialogue_session_path(None)

    assert resolved == app_module.Path("C:/local/stardew-session.json")
    assert default_resolved.name == "dialogue-lab-session.json"
    assert default_resolved.parent.name == "StardewAI.NPC"
    assert "artifacts" not in {part.lower() for part in default_resolved.parts}
