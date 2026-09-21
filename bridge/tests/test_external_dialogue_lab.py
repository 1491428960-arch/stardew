from __future__ import annotations

import json

import re
import subprocess
import os
from pathlib import Path

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
        "flirtIntensity",
        "adultConsensual",
        "relationshipContext",
        "调情强度",
        "repeated_speech_particle",
        "styleQuality",
    ):
        assert marker in html


def test_case_browser_separates_generated_player_input_quality_from_npc_score() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "playerInputMode",
        "generated_after_previous_reply",
        "玩家输入来源",
        "玩家输入质量",
        "NPC 回复评分",
        "linkedToPreviousReply",
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


def test_group_dialogue_lab_exposes_three_online_strategies() -> None:
    response = TestClient(app).get("/test/group")

    assert response.status_code == 200
    html = response.text
    for marker in (
        'id="group-participants"',
        'value="fanout"',
        'value="turn_based"',
        'value="multi_turn"',
        'value="remote"',
        "/api/dialogue/group",
        "providerCalls",
        "fallbackCount",
    ):
        assert marker in html


def test_group_dialogue_review_renders_generated_cloud_batch() -> None:
    response = TestClient(app).get("/test/group/review")

    assert response.status_code == 200
    html = response.text
    for marker in (
        "线上群聊 · 云端样本回放",
        'id="group-review-data"',
        "20260918-group-dialogue-cloud-v3-fanout-cases",
        "fanout",
        "多人回应",
        "allParticipantsReplied",
        "自然接话流（可插话）",
        "npc-message",
        "speaker-tone",
        "Sophia",
        "协议通过",
        "角色观察",
    ):
        assert marker in html


def test_group_dialogue_review_supports_explicit_batch_selection() -> None:
    client = TestClient(app)

    default_html = client.get("/test/group/review").text
    assert 'href="/test/group/review?batch=' in default_html

    # 显式请求仍返回指定批次；非法值回落到最新批次而不是报错。
    explicit = client.get(
        "/test/group/review",
        params={"batch": "20260918-group-dialogue-cloud-v3-fanout-cases"},
    )
    assert explicit.status_code == 200
    assert "20260918-group-dialogue-cloud-v3-fanout-cases" in explicit.text

    unknown = client.get("/test/group/review", params={"batch": "nope"})
    assert unknown.status_code == 200
    assert "?batch=" in unknown.text


def test_group_dialogue_lab_exposes_multi_turn_count_control() -> None:
    html = TestClient(app).get("/test/group").text

    assert 'id="group-turn-count"' in html
    assert "最多回合数" in html
    assert "turnCount" in html


def test_group_dialogue_lab_script_keeps_error_join_escaped() -> None:
    html = TestClient(app).get("/test/group").text

    assert 'body.providerErrors.join("\\n")' in html
    assert 'body.providerErrors.join("\n")' not in html


def test_group_dialogue_review_discovers_new_batches_without_code_change(tmp_path: Path) -> None:
    from stardew_ai_bridge.group_dialogue_review_page import group_dialogue_review_page

    new_batch = tmp_path / "20260919-group-dialogue-cloud-v5-addressed-continuation"
    new_batch.mkdir()
    (new_batch / "cases.json").write_text("[]", encoding="utf-8")

    html = group_dialogue_review_page(tmp_path)

    assert "?batch=20260919-group-dialogue-cloud-v5-addressed-continuation" in html
    # 没有 ?batch= 时显示最新的那个批次（按 cases.json 写入时间，而不是目录名排序）
    payload = json.loads(
        re.search(
            r'<script id="group-review-data" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        ).group(1)
    )
    assert payload["batchName"] == "20260919-group-dialogue-cloud-v5-addressed-continuation"


def test_group_dialogue_review_ignores_batches_outside_the_group_dialogue_prefix(tmp_path: Path) -> None:
    from stardew_ai_bridge.group_dialogue_review_page import group_dialogue_review_page

    other_batch = tmp_path / "20260919-topic-start-adaptive-other-suite"
    other_batch.mkdir()
    (other_batch / "cases.json").write_text("[]", encoding="utf-8")

    html = group_dialogue_review_page(tmp_path)

    assert "20260919-topic-start-adaptive-other-suite" not in html


def test_group_dialogue_review_renders_pixel_character_glyphs() -> None:
    html = TestClient(app).get("/test/group/review").text

    for marker in (
        "SPEAKER_GLYPHS",
        "avatar-glyph",
        "speaker-dot",
    ):
        assert marker in html
    # 每个已知 NPC 都要有自己的内联图形定义（不依赖外部图片）；
    # SVG 尖括号在页面里是 \u003c 转义，避免提前闭合 script 标签。
    glyphs = json.loads(re.search(r"const SPEAKER_GLYPHS = (.*);", html).group(1))
    assert len(glyphs) == 46
    assert all('<svg ' in glyph and 'aria-hidden="true"' in glyph for glyph in glyphs.values())
    assert "SPEAKER_MOTIFS" not in html
    assert all('shape-rendering="crispEdges"' in glyph for glyph in glyphs.values())
    for npc_id in ("Abigail", "Elliott", "Sophia", "Wizard", "Shane"):
        assert npc_id in html


def test_group_dialogue_review_uses_approved_palette_and_primary_motifs() -> None:
    from stardew_ai_bridge.group_dialogue_review_page import group_dialogue_review_page

    root = Path(__file__).resolve().parents[2]
    spec = json.loads((root / "docs/npc-bubble-elements-2026-09-19.json").read_text(encoding="utf-8"))
    html = group_dialogue_review_page(root / "artifacts/character-quality-eval")
    # Execute the emitted constants so this also catches stale hand-written JS data.
    declarations = "\n".join(
        re.search(rf"const {name} = .*?;", html, re.DOTALL).group(0)
        for name in ("NPC_STYLES", "SPEAKER_GLYPHS")
    )
    result = subprocess.run(
        ["node"], input=declarations + ";process.stdout.write(JSON.stringify({NPC_STYLES,SPEAKER_GLYPHS}))",
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    emitted = json.loads(result.stdout)
    assert set(spec["npcOrder"]) <= set(emitted["NPC_STYLES"])
    assert len(emitted["NPC_STYLES"]) == 46
    for npc, expected in spec["npcs"].items():
        style = emitted["NPC_STYLES"][npc]
        for key in ("accent", "accentSoft", "bubble", "border"):
            assert style[key] == expected["palette"][key], (npc, key)
        assert style["tone"] == expected["toneLabel"]
    from stardew_ai_bridge.npc_bubble_elements import NPC_BUBBLE_ELEMENTS

    for npc, elements in NPC_BUBBLE_ELEMENTS.items():
        assert elements["motifs"][0] in emitted["SPEAKER_GLYPHS"][npc]


def test_group_dialogue_review_decoration_keeps_player_and_text_separate() -> None:
    html = TestClient(app).get("/test/group/review").text
    assert "SPEAKER_MOTIFS" not in html
    assert ".bubble-ring" not in html
    assert "border-image" not in html
    # 角色物件形成独立装饰层，旧藤蔓算法与平铺边框不再使用。
    assert "bubble-vine" not in html
    assert "VINE_COLORS" not in html
    assert "vineSvg" not in html
    assert "border-color: var(--border" in html
    for role in ("sebastian", "sophia", "elliott", "wizard"):
        assert f".message.role-{role} .bubble" not in html
    # The original text remains a distinct layout box, never SVG text or innerHTML.
    assert 'el("span", "bubble-text", turn.content || "")' in html
    assert 'data-bubble-design="character-frames-v2"' in html
    assert 'const ornament = ornamentFor(speakerId)' in html
    assert 'if (ornament)' in html
    assert 'frame.setAttribute("aria-hidden", "true")' in html
    assert 'frameObserver.disconnect()' in html
    assert 'frameObserver.observe(bubble)' in html


def test_group_dialogue_review_character_frames_use_the_single_element_library() -> None:
    from stardew_ai_bridge.npc_bubble_elements import NPC_BUBBLE_ELEMENTS

    html = TestClient(app).get("/test/group/review").text
    match = re.search(r"const CHARACTER_ORNAMENTS = (.*);", html)
    assert match, "页面还没有消费角色环绕装饰库"
    emitted = json.loads(match.group(1))
    assert set(emitted) == set(NPC_BUBBLE_ELEMENTS)
    for npc, item in NPC_BUBBLE_ELEMENTS.items():
        assert emitted[npc] == json.loads(json.dumps(item["ornament"]))
    assert "Object.hasOwn(CHARACTER_ORNAMENTS, canonicalNpcId(npcId))" in html
    assert ".bubble-frame" in html and "pointer-events: none" in html


def test_character_frame_renderer_adapts_to_bubble_size_without_tiling() -> None:
    from xml.etree import ElementTree

    html = TestClient(app).get("/test/group/review").text
    assert "function characterFrameSvg(" in html, "缺少自适应角色装饰绘制器"
    declaration = re.search(r"const CHARACTER_ORNAMENTS = .*?;", html).group(0)
    function = "function characterFrameSvg(width, height, ornament) " + _function_body(html, "characterFrameSvg")
    script = declaration + function + ";process.stdout.write(JSON.stringify(Object.values(CHARACTER_ORNAMENTS).flatMap(o => [[164,94],[300,116],[700,260]].map(([w,h]) => characterFrameSvg(w,h,o)))));"
    result = subprocess.run(["node"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    frames = json.loads(result.stdout)
    assert len(frames) == 46 * 3
    for i, svg in enumerate(frames):
        root = ElementTree.fromstring(svg)
        width, height = ((164,94), (300,116), (700,260))[i % 3]
        assert root.attrib["viewBox"] == f"0 0 {width + 28} {height + 28}"
        assert root.attrib["shape-rendering"] == "crispEdges"
        assert len([n for n in root.iter() if "data-object" in n.attrib]) >= 2
        assert {n.attrib["data-side"] for n in root.iter() if "data-side" in n.attrib} == {"top", "right", "bottom", "left"}
        assert not any(n.tag.rsplit("}",1)[-1] in {"pattern", "image", "text", "script"} for n in root.iter())
        assert "NaN" not in svg and "undefined" not in svg


def test_character_frames_have_stable_asymmetric_compositions() -> None:
    html = TestClient(app).get("/test/group/review").text
    declaration = re.search(r"const CHARACTER_ORNAMENTS = .*?;", html).group(0)
    function = "function characterFrameSvg(width, height, ornament) " + _function_body(html, "characterFrameSvg")
    script = declaration + function + ";process.stdout.write(JSON.stringify([0,1,2,0].map(v=>characterFrameSvg(360,120,CHARACTER_ORNAMENTS.Sophia,v))));"
    result = subprocess.run(["node"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    frames = json.loads(result.stdout)
    assert frames[0] == frames[3], "重绘不能随机跳动"
    assert len(set(frames[:3])) == 3, "不同回合不应复制同一构图"
    assert 'bubble.dataset.frameVariant' in html


def test_chat_lab_topic_button_does_not_render_internal_topic_prompt_as_player_bubble() -> None:
    html = _chat_html()

    send_body = _function_body(html, "sendDialogue")
    assert 'intent==="topic"' in send_body
    assert "请主动找话题" not in send_body
    assert "请结合当前场景主动找一个合适的话题" not in send_body


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
        assert 'href="/test/group"' in html
        assert "多人实验" in html
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
        "initiativeExpectation",
        "initiativeKind",
        "主动回撩",
        "具体邀约",
        "克制接住",
        "允许收口",
    ):
        assert marker in html


def test_quality_case_browser_exposes_event_impact_side_by_side_contract() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "event-impact-comparison",
        "事件前 · 未完成事件",
        "事件后 · 已完成事件",
        "eventEvidence",
        "unresolved_i18n",
        "renderEventImpactComparison",
    ):
        assert marker in html


def test_quality_case_browser_follows_latest_suite_with_url_override() -> None:
    html = TestClient(app).get("/test").text
    load_cases_body = _function_body(html, "loadQualityCases")

    assert "await loadQualityResults()" in load_cases_body
    assert "summary.suite" in load_cases_body
    assert "URLSearchParams(window.location.search)" in load_cases_body
    assert "encodeURIComponent" in load_cases_body
    assert "/api/quality/cases?suite=" in load_cases_body


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
    high_case = next(
        item for item in payload["cases"] if item["caseId"] == "alex-married-evening"
    )
    assert high_case["friendshipHearts"] == 10
    assert high_case["flirtIntensity"] == "explicit"
    assert high_case["adultConsensual"] is True
    assert high_case["relationshipContext"]
    assert [item["caseNumber"] for item in payload["cases"]] == list(
        range(1, len(payload["cases"]) + 1)
    )


def test_quality_cases_endpoint_can_select_topic_start_intimacy_suite() -> None:
    response = TestClient(app).get(
        "/api/quality/cases?suite=topic-start-intimacy"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == 1
    assert payload["suite"] == "topic-start-intimacy"
    assert len(payload["cases"]) == 50
    assert [item["caseNumber"] for item in payload["cases"]] == list(range(1, 51))
    assert all(item["intent"] == "topic" for item in payload["cases"])
    assert all(item["playerInput"] == "" for item in payload["cases"])
    assert all(item["topicSeed"] for item in payload["cases"])
    assert all(item["topicKeywords"] for item in payload["cases"])
    assert all(
        [turn["intent"] for turn in item["turns"]] == ["topic", "chat", "chat"]
        for item in payload["cases"]
    )


def test_quality_cases_endpoint_can_select_event_impact_suite() -> None:
    response = TestClient(app).get(
        "/api/quality/cases?suite=topic-start-event-impact"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["suite"] == "topic-start-event-impact"
    assert payload["source"] == "event_impact_cases.EVENT_IMPACT_CASES"
    assert len(payload["cases"]) == 14
    assert {item["eventCondition"] for item in payload["cases"]} == {"before", "after"}
    assert all(item["followUpMode"] == "fixed" for item in payload["cases"])
    assert all(item["eventEvidence"] for item in payload["cases"])
    assert all(len(item["turns"]) == 3 for item in payload["cases"])
    sophia = next(
        item for item in payload["cases"] if item["eventPairId"] == "sophia-8185290"
    )
    assert sophia["eventSourceStatus"] == "unresolved_i18n"


def test_quality_cases_endpoint_can_select_conversation_lead_suite() -> None:
    response = TestClient(app).get("/api/quality/cases?suite=conversation-lead")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == 1
    assert payload["suite"] == "conversation-lead"
    assert payload["source"] == "character_quality_eval.CONVERSATION_LEAD_CASES"
    assert [item["caseId"] for item in payload["cases"]] == [
        "wizard-married-evening",
        "sophia-married-cellar",
        "shane-dating-boundary",
        "sebastian-married-music",
        "alex-married-evening",
        "elliott-married-studio",
        "harvey-married-clinic",
        "sam-married-band",
    ]
    assert [item["caseNumber"] for item in payload["cases"]] == list(range(1, 9))


def test_quality_cases_endpoint_can_select_affection_pacing_suite() -> None:
    response = TestClient(app).get("/api/quality/cases?suite=affection-pacing")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == 1
    assert payload["suite"] == "affection-pacing"
    assert payload["source"] == "affection_pacing_cases.AFFECTION_PACING_SUITE"
    assert len(payload["cases"]) == 32
    assert [item["caseNumber"] for item in payload["cases"]] == list(range(1, 33))
    assert all(len(item["turns"]) == 3 for item in payload["cases"])


def test_quality_cases_endpoint_can_select_relationship_world_suite() -> None:
    response = TestClient(app).get("/api/quality/cases?suite=relationship-world")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == 1
    assert payload["suite"] == "relationship-world"
    assert payload["source"] == "relationship_world_cases.RELATIONSHIP_WORLD_SUITE"
    assert len(payload["cases"]) == 32
    assert [item["caseNumber"] for item in payload["cases"]] == list(range(1, 33))
    assert all("objectiveRelationships" not in item for item in payload["cases"])
    assert all("relationshipWorld" not in item for item in payload["cases"])


def test_quality_cases_endpoint_can_select_deep_flirt_suite() -> None:
    response = TestClient(app).get("/api/quality/cases?suite=deep-flirt")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == 1
    assert payload["suite"] == "deep-flirt"
    assert payload["source"] == "deep_flirt_cases.DEEP_FLIRT_SUITE"
    assert [item["caseNumber"] for item in payload["cases"]] == list(range(1, 9))
    assert [item["caseId"] for item in payload["cases"]] == [
        "deep-flirt-wizard-married",
        "deep-flirt-sophia-married",
        "deep-flirt-shane-dating",
        "deep-flirt-sebastian-married",
        "deep-flirt-alex-married",
        "deep-flirt-elliott-married",
        "deep-flirt-harvey-married",
        "deep-flirt-sam-married",
    ]
    assert all(item["channel"] == "face_to_face" for item in payload["cases"])
    assert all(item["adultConsensual"] is True for item in payload["cases"])
    assert all(item["romanceEligible"] is True for item in payload["cases"])
    assert all(item["turnCount"] == 3 for item in payload["cases"])
    assert all(len(item["turns"]) == 3 for item in payload["cases"])
    assert all(
        [turn["playerInputMode"] for turn in item["turns"]]
        == ["fixed", "fixed", "fixed"]
        for item in payload["cases"]
    )


def test_quality_cases_endpoint_can_select_deep_flirt_intimate_suite() -> None:
    response = TestClient(app).get(
        "/api/quality/cases?suite=deep-flirt-intimate"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == 1
    assert payload["suite"] == "deep-flirt-intimate"
    assert payload["source"] == (
        "deep_flirt_intimate_cases.DEEP_FLIRT_INTIMATE_SUITE"
    )
    assert len(payload["cases"]) == 8
    assert all(item["turnCount"] == 5 for item in payload["cases"])
    assert all(len(item["turns"]) == 5 for item in payload["cases"])
    assert all(item["adultConsensual"] is True for item in payload["cases"])
    assert all(item["romanceEligible"] is True for item in payload["cases"])
    assert all(
        any(
            marker in "\n".join(turn["playerInput"] for turn in item["turns"])
            for marker in ("亲", "吻")
        )
        for item in payload["cases"]
    )


def test_quality_cases_endpoint_can_select_reply_driven_adaptive_suite() -> None:
    response = TestClient(app).get(
        "/api/quality/cases?suite=topic-start-adaptive"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["suite"] == "topic-start-adaptive"
    assert payload["source"] == (
        "topic_start_adaptive_cases.TOPIC_START_ADAPTIVE_CASES"
    )
    assert len(payload["cases"]) == 50
    assert all(item["followUpMode"] == "adaptive" for item in payload["cases"])
    assert all(
        [turn["playerInputMode"] for turn in item["turns"]]
        == ["fixed", "generated_after_previous_reply", "generated_after_previous_reply"]
        for item in payload["cases"]
    )
    assert all(
        [turn["playerInput"] for turn in item["turns"]] == ["", "", ""]
        for item in payload["cases"]
    )


def test_quality_cases_endpoint_rejects_unknown_suite() -> None:
    response = TestClient(app).get("/api/quality/cases?suite=not-a-suite")

    assert response.status_code == 400


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
    assert payload["runStatus"] == "valid"
    assert payload["runStatusReasons"] == []
    assert payload["results"][0]["reply"] == "塔里的灰尘还没积够层数。"
    serialized = response.text
    assert "敏感 prompt" not in serialized
    assert "apiKey" not in serialized
    assert "secret" not in serialized


def test_quality_results_endpoint_can_select_requested_suite(
    tmp_path,
    monkeypatch,
) -> None:
    relationship_run = tmp_path / "20260906-relationship-world"
    relationship_run.mkdir()
    (relationship_run / "summary.json").write_text(
        '{"schemaVersion":1,"suite":"relationship-world",'
        '"caseCount":1,"successful":1,"errors":0}',
        encoding="utf-8",
    )
    (relationship_run / "results.jsonl").write_text(
        '{"caseId":"relationship-wizard-jealousy-recovery",'
        '"suite":"relationship-world","reply":"关系结果"}\n',
        encoding="utf-8",
    )
    default_run = tmp_path / "20260907-default"
    default_run.mkdir()
    (default_run / "summary.json").write_text(
        '{"schemaVersion":1,"suite":"default",'
        '"caseCount":1,"successful":1,"errors":0}',
        encoding="utf-8",
    )
    (default_run / "results.jsonl").write_text(
        '{"caseId":"wizard-daily","suite":"default",'
        '"reply":"默认结果"}\n',
        encoding="utf-8",
    )
    os.utime(relationship_run, (1, 1))
    os.utime(default_run, (2, 2))
    monkeypatch.setattr(app_module, "quality_artifact_root", tmp_path, raising=False)

    response = TestClient(app).get(
        "/api/quality/results?suite=relationship-world"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["batchId"] == relationship_run.name
    assert payload["summary"]["suite"] == "relationship-world"
    assert payload["results"][0]["caseId"] == (
        "relationship-wizard-jealousy-recovery"
    )


def test_quality_results_endpoint_can_select_deep_flirt_suite(
    tmp_path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "20260914-deep-flirt-smoke-v1"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        '{"schemaVersion":2,"suite":"deep-flirt",'
        '"caseCount":1,"successful":1,"errors":0,'
        '"turnCount":3,"successfulTurns":3}',
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        '{"caseId":"deep-flirt-wizard-married","suite":"deep-flirt",'
        '"turns":[{"turnId":"turn-1","reply":"第一轮"},'
        '{"turnId":"turn-2","reply":"第二轮"},'
        '{"turnId":"turn-3","reply":"第三轮"}]}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "quality_artifact_root", tmp_path, raising=False)

    response = TestClient(app).get("/api/quality/results?suite=deep-flirt")

    assert response.status_code == 200
    payload = response.json()
    assert payload["batchId"] == run_dir.name
    assert payload["summary"]["suite"] == "deep-flirt"
    assert payload["runStatus"] == "valid"
    assert payload["results"][0]["caseId"] == "deep-flirt-wizard-married"


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


def test_quality_results_preserve_safe_progression_statistics_only(
    tmp_path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "20260901-progression"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        '{"schemaVersion":2,"caseCount":1,"successful":1,"errors":0,'
        '"passed":0,"passedCases":0,"passedTurns":1,'
        '"turnPassRate":0.3333,"casePassRate":0.0}',
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        '{"caseId":"wizard-married-evening","caseNumber":25,'
        '"casePassed":false,"passedTurnCount":1,"failedTurnCount":2,'
        '"progression":{"passed":false,"tags":["repeated_turn_content"],'
        '"overlap":0.91,"novelExpectedTerms":[]},'
        '"prompt":"secret prompt","apiKey":"secret"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "quality_artifact_root", tmp_path, raising=False)

    response = TestClient(app).get("/api/quality/results")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["passedTurns"] == 1
    assert payload["summary"]["passedCases"] == 0
    assert payload["summary"]["turnPassRate"] == 0.3333
    result = payload["results"][0]
    assert result["caseNumber"] == 25
    assert result["casePassed"] is False
    assert result["passedTurnCount"] == 1
    assert result["progression"] == {
        "passed": False,
        "tags": ["repeated_turn_content"],
        "overlap": 0.91,
        "novelExpectedTerms": [],
    }
    assert "secret prompt" not in response.text
    assert "apiKey" not in response.text


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


def test_case_browser_aggregates_initiative_detection_across_all_turns() -> None:
    html = TestClient(app).get("/test").text
    body = _function_body(html, "affectionInitiativeData")

    assert re.search(
        r"result\.initiativeDetected === true\s*\|\|\s*"
        r"turns\.some\(\(turn\) => turn\?\.initiativeDetected === true\)",
        body,
    )


def test_case_browser_separates_npc_pass_rate_from_adaptive_player_input_quality() -> None:
    html = TestClient(app).get("/test").text
    render_batch_body = _function_body(html, "renderBatchSummary")

    for marker in (
        "NPC 单轮通过",
        "动态玩家输入质量",
        "playerInputValidCount",
        "playerInputGenerationCount",
        "playerInputInvalidCount",
        "playerInputQualityTags",
    ):
        assert marker in render_batch_body


def test_case_browser_renders_fixed_player_expression_card_without_internal_rules() -> None:
    html = TestClient(app).get("/test?suite=deep-flirt").text
    render_body = _function_body(html, "renderAdaptiveInputSummary")

    for marker in (
        "玩家表达倾向",
        "playerExpressionCard",
        "relationshipStance",
        "languageTexture",
        "flirtProgression",
        "boundaryStyle",
        "selfCorrection",
        "不是 NPC 的运行时提示",
    ):
        assert marker in render_body or marker in html
    assert "forbiddenTendencies" not in render_body


def test_case_browser_marks_invalid_quality_batches_as_diagnostic_only() -> None:
    html = TestClient(app).get("/test").text
    render_batch_body = _function_body(html, "renderBatchSummary")

    for marker in (
        "diagnostic_invalid",
        "runStatusReasons",
        "仅诊断，不代表角色质量",
        "provider_error",
        "fallback",
        "missing_reply",
        "truncated_output",
    ):
        assert marker in render_batch_body or marker in html


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


def test_case_browser_renders_historical_guard_warnings_and_batch_coverage() -> None:
    html = TestClient(app).get("/test?suite=relationship-world").text
    batch_body = _function_body(html, "renderBatchSummary")

    for marker in (
        "turn.warnings",
        "transcript-turn-warning",
        "输出质量校验",
        "诊断详情",
    ):
        assert marker in html
    for marker in (
        "coverage",
        "结果覆盖",
        "未生成",
    ):
        assert marker in batch_body or marker in html


def test_case_browser_separates_quality_retry_history_from_final_score_and_hard_guard() -> None:
    html = TestClient(app).get("/test?suite=relationship-world").text
    transcript_body = _function_body(html, "renderCaseTranscript")

    for marker in (
        "formatTurnWarnings",
        "retryCount",
        "formatTurnWarnings(warnings, turn.score, turn.retryCount, turn.initiativeExpectation)",
        "质量重试失败",
        "质量重试未执行",
        "响应 Guard",
        "最终通过",
        "最终仍需复核",
        "诊断详情",
    ):
        assert marker in transcript_body or marker in html
    assert "Guard 重试（${warnings.length}）" not in transcript_body


def test_case_browser_deduplicates_and_explains_quality_diagnostics() -> None:
    html = TestClient(app).get("/test?suite=relationship-world").text
    transcript_body = _function_body(html, "formatTurnWarnings")

    for marker in (
        "uniqueWarningEntries",
        "qualityDiagnosticLabel",
        "缺少主动亲密信号",
        "输出质量校验",
        "查看诊断详情（已翻译）",
        "appendDiagnosticDetails",
        "（${entry.count} 次）",
    ):
        assert marker in transcript_body or marker in html


def test_case_browser_does_not_render_raw_warning_codes_in_expanded_details() -> None:
    html = TestClient(app).get("/test?suite=relationship-world").text
    details_body = _function_body(html, "appendDiagnosticDetails")

    assert "appendDiagnosticDetails(" in html
    assert "qualityDiagnosticSummary(warnings, initiativeExpectation)" in details_body
    assert "查看诊断详情（已翻译）" in details_body
    assert "rawDiagnosticSummary(warnings)" not in details_body
    assert "textContent = rawDiagnosticSummary" not in details_body


def test_case_browser_explains_legacy_affection_retry_by_turn_contract() -> None:
    html = TestClient(app).get("/test?suite=relationship-world").text
    transcript_body = _function_body(html, "formatTurnWarnings")

    for marker in (
        "initiativeExpectation",
        "旧批次",
        "当前回合无需主动亲密",
        "formatTurnWarnings(warnings, turn.score, turn.retryCount, turn.initiativeExpectation)",
    ):
        assert marker in transcript_body or marker in html


def test_case_browser_humanizes_hard_guard_and_provider_diagnostics() -> None:
    html = TestClient(app).get("/test?suite=relationship-world").text
    transcript_body = _function_body(html, "formatTurnWarnings")

    assert "qualityDiagnosticSummary(hardGuards, initiativeExpectation)" in transcript_body
    assert "qualityDiagnosticSummary(providerDiagnostics, initiativeExpectation)" in transcript_body
    assert "rawDiagnosticSummary(hardGuards)" not in transcript_body
    assert "rawDiagnosticSummary(providerDiagnostics)" not in transcript_body


def test_chat_browser_humanizes_runtime_warning_codes() -> None:
    html = TestClient(app).get("/test/chat").text

    for marker in (
        "formatChatWarnings",
        "质量重试",
        "质量重试失败",
        "质量重试未执行",
        "Provider 诊断",
        "missing_proactive_affection: \"缺少主动亲密信号\"",
    ):
        assert marker in html
    assert "data.warnings.join(\"；\")" not in html


def test_case_browser_translates_visible_quality_tags_to_human_readable_labels() -> None:
    html = TestClient(app).get("/test?suite=relationship-world").text

    for marker in (
        "function diagnosticTagLabel(tag)",
        'missing_personal_affection: "缺少个人亲密表达"',
        'missing_topic_evidence: "缺少当前话题证据"',
        'missing_conversation_lead: "缺少主动对话推进"',
        'jealousy_recovery_missing: "未完成嫉妒恢复"',
        "score.tags.map(diagnosticTagLabel)",
        "pill.textContent = diagnosticTagLabel(tag)",
    ):
        assert marker in html


def test_case_browser_exposes_case_numbers_progression_and_pass_rates() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "caseNumber",
        "case-position",
        "repeated_turn_content",
        "passedTurns",
        "passedCases",
        "单轮通过",
        "完整案例通过",
    ):
        assert marker in html


def test_case_browser_exposes_mechanical_restatement_diagnostic() -> None:
    html = TestClient(app).get("/test").text

    for marker in (
        "mechanicalRestatement",
        "mechanicalRestatementCount",
        "机械复述玩家",
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


def test_case_browser_defaults_to_actual_replies_and_exposes_all_definitions_toggle() -> None:
    """默认列表只让人工先看到有真实 NPC 回复的案例，定义目录仍可显式展开。"""
    html = TestClient(app).get("/test").text

    for marker in (
        'id="show-all-definitions"',
        "显示全部定义",
        "state.showAllDefinitions",
        "function hasActualReply(",
        "hasActualReply(item)",
        "仅显示已生成回复",
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
    assert '<option value="cloud" selected>Gemini 云端（正式运行，默认）</option>' in html


def test_external_lab_defaults_to_explicit_cloud_provider() -> None:
    html = _chat_html()

    assert '<option value="cloud" selected>Gemini 云端（正式运行，默认）</option>' in html
    assert '<option value="auto">自动（正式：仅 Gemini，失败安全兜底）</option>' in html
    assert '<option value="local">Qwen 本地（手动 A/B / 回滚）</option>' in html


def test_external_lab_explains_gemini_default_and_manual_qwen_rollback() -> None:
    html = _chat_html()

    assert "中转站波动不会静默切回 Qwen" in html


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
        "female-bachelors",
        "female.bachelors.beach",
    ):
        assert source_mod in html
    assert "setRuntimeSourceDefaults" not in html
    assert "sourceMods:profile.sourceMods" in html


def test_external_lab_uses_feminine_display_names_without_changing_canonical_ids() -> None:
    chat_html = _chat_html()
    case_html = TestClient(app).get("/test").text
    raw_html = TestClient(app).get("/raw").text

    for display_name, npc_id in (
        ("珊恩", "Shane"),
        ("塞布瑞娜", "Sebastian"),
        ("爱丽克斯", "Alex"),
    ):
        assert f'npcId:"{npc_id}",label:"{display_name} / {npc_id}",displayName:"{display_name}"' in chat_html
        assert f'{npc_id}:"{display_name} / {npc_id}"' in case_html
        assert f'{npc_id}:"{display_name} / {npc_id}"' in raw_html

    chat_load_npcs = _function_body(chat_html, "loadNpcs")
    raw_load_npcs = raw_html
    assert "const profile=evaluationProfileForNpc(npc.npcId);" in chat_load_npcs
    assert "const displayName=profile?.displayName||npc.displayName||npc.npcId" in chat_load_npcs
    assert "const label=EVALUATION_LABELS[npc.npcId]||npc.displayName||npc.npcId" in raw_load_npcs
    assert 'sourceMods:["female-bachelors","Invatorzen.idcsm","female.bachelors.beach","female.bachelors.winter"]' in chat_html
    assert 'npcId:"Alex",label:"爱丽克斯 / Alex",displayName:"爱丽克斯"' in chat_html


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


def test_integrated_raw_dialogue_follows_case_selected_npc() -> None:
    html = TestClient(app).get("/test").text

    assert 'window.addEventListener("dialogue-lab:case-selected"' in html
    assert "loadRawDialogue(event.detail?.npcId)" in html
    assert 'view: searchParams.get("view") || ""' in html
    assert 'initialCaseViewState.view === "raw"' in html


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
        # 请求路径开关（默认走游戏端紧凑路径）也是会话契约的一部分。
        "compactPrompt": True,
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
    assert loaded.json() == {**payload, "compactPrompt": True}


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
