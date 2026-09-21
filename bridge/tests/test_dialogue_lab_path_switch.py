"""「按游戏端路径（紧凑）」开关与两条路径一致性的契约测试。

背景：网页对话实验室此前从不发 `compactPrompt`，而游戏端
`smapi/BridgeClient.cs` 的 `CompactPrompt` 默认 `true`。于是
「网页离线评测跑完整卡组、实机跑紧凑卡组」，同一份改动在两边表现不同 ——
2026-09-20 之前已经因此踩过三次（生活面槽位被紧凑白名单丢掉、
第二个弹窗出口、开场重复检测名单为空）。

这一组测试守住三件事：

1. 页面开关默认勾选、勾选状态可跨刷新恢复、并且真的进请求体；
2. `/api/context/preview` 与 `/api/dialogue/test` 走同一个紧凑判定，
   「上下文预览看到的那份」就是「实发的那份」；
3. 同类页面各自走哪条路径写成显式断言，以后再加页面时不会又冒出一个
   悄悄不发这个字段的入口。
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

import stardew_ai_bridge.app as app_module
from stardew_ai_bridge.app import app
from stardew_ai_bridge.dialogue_lab_session import (
    DialogueLabSessionStore,
    empty_session,
    normalize_session,
)
from stardew_ai_bridge.models import GroupDialogueRequest, ProviderResult


BASE_PAYLOAD: dict[str, Any] = {
    "npcId": "Wizard",
    "message": "今天过得怎么样？",
    "displayName": "Rasmodia",
    "sourceMods": ["Romanceable Rasmodius"],
    "gameState": {
        "season": "春",
        "date": "春 1 日",
        "weather": "晴天",
        "time": 800,
        "location": "法师塔",
        "friendship": 128,
    },
}


def _function_span(html: str, function_name: str) -> tuple[int, int]:
    """定位页面内联脚本里某个函数的起止下标（含 `function` 关键字）。"""

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
                return start, index + 1
    raise AssertionError(f"未找到 {function_name} 函数结束位置")


def _function_body(html: str, function_name: str) -> str:
    """只取 `{...}` 主体，用于对函数内部做文本断言。"""

    start, end = _function_span(html, function_name)
    return html[html.index("{", start) : end]


def _function_source(html: str, function_name: str) -> str:
    """连签名一起取，用于把函数原样放进 node 桩里执行。

    只取 `{...}` 会变成块语句——块里的 `return` 在 CommonJS 包装下会
    直接结束整个模块，脚本静默退出、断言拿不到任何输出。
    """

    start, end = _function_span(html, function_name)
    return html[start:end]


def _chat_html() -> str:
    return TestClient(app).get("/test/chat").text


@dataclass
class RecordingRouter:
    """记录实发给 provider 的 messages，不触碰任何真实上游。"""

    messages: list[dict[str, Any]] | None = None

    def has_configured_upstream(self) -> bool:
        return True

    def generate(
        self,
        request: object,
        *,
        messages: list[dict[str, Any]] | None = None,
    ) -> ProviderResult:
        del request
        self.messages = messages
        return ProviderResult(
            reply="塔顶今晚没有云，能看到不少东西。",
            provider="recording",
            fallback=False,
            latencyMs=0,
        )


class PathRecordingPromptBuilder:
    """按 compact 参数返回不同的卡片名，让「走了哪条路径」在 prompt 里可读。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, bool]] = []

    def build(
        self,
        context: dict[str, Any],
        player_input: str,
        *,
        compact: bool = False,
    ) -> list[dict[str, str]]:
        del player_input
        self.calls.append(
            {
                "compact": compact,
                "runtimeCompact": context.get("_runtime_compact") is True,
            }
        )
        card = "scene_compact" if compact else "game_state_full"
        return [
            {"role": "system", "name": card, "content": "captured"},
            {"role": "user", "name": "player", "content": "captured"},
        ]


# --- 1. 开关本身：默认、可见、可持久化 -------------------------------------


def test_chat_lab_ships_a_game_path_switch_that_defaults_to_on() -> None:
    html = _chat_html()

    assert 'id="compact-path"' in html
    assert 'id="compact-path" checked' in html
    assert 'id="path-indicator"' in html
    # 默认（未读过偏好时）就应显示游戏端路径，避免「默认是完整路径」的老坑。
    assert "路径：游戏端（紧凑）" in html


def test_game_path_switch_survives_the_integrated_workspace_shell() -> None:
    """集成工作台会剥掉页面 `<header>`，所以控件不能只挂在顶栏里。"""

    html = TestClient(app).get("/test").text

    assert 'id="compact-path"' in html
    assert 'id="path-indicator"' in html


def test_chat_lab_switch_is_remembered_through_the_session_api() -> None:
    """开关状态跟会话一起走 Bridge 的 session API。

    实验室有一条既有约定：会话状态一律放 `/api/dialogue/session`，
    页面不使用任何浏览器存储（见
    `test_external_dialogue_lab.test_external_lab_does_not_use_browser_storage_for_session`）。
    路径开关属于会话状态，所以它跟着同一份文件走。
    """

    html = _chat_html()
    save_body = _function_body(html, "saveSession")
    load_body = _function_body(html, "loadSession")

    # 写入：和 messages / history 一起进同一份会话文件。
    assert "compactPrompt:compactPathEnabled()" in save_body
    # 读回：刷新时由 loadSession 恢复；缺字段（老会话）按游戏端路径。
    assert "applyCompactPathPreference(session.compactPrompt!==false)" in load_body
    # 「版本不符」与「读取失败」两条分支都回默认的游戏端路径。
    assert load_body.count("applyCompactPathPreference(true)") == 2
    # 勾选变化要立刻落盘，否则「勾完就刷新」会丢。
    change_start = html.index('$("compact-path")?.addEventListener("change"')
    change_handler = html[change_start : html.index("});messageInput", change_start)]
    assert "await saveSession()" in change_handler
    assert "localStorage" not in html


def test_session_store_round_trips_the_path_switch(tmp_path: Path) -> None:
    store = DialogueLabSessionStore(tmp_path / "dialogue-lab-session.json")

    assert empty_session()["compactPrompt"] is True
    assert store.load() == empty_session()

    for wanted in (False, True):
        stored = store.save({**empty_session(), "compactPrompt": wanted})
        assert stored["compactPrompt"] is wanted
        assert store.load()["compactPrompt"] is wanted

    # 老会话文件缺这个键、或类型不对时，一律回到默认的游戏端路径。
    assert normalize_session({"version": 1})["compactPrompt"] is True
    assert normalize_session({"version": 1, "compactPrompt": "yes"})["compactPrompt"] is True
    assert normalize_session({"version": 1, "compactPrompt": False})["compactPrompt"] is False


# --- 2. buildPayload / 指示器：在 node 里真跑一遍 ---------------------------


def _run_page_script(tmp_path: Path, html: str, *, checked: bool) -> dict[str, Any]:
    """把页面的 buildPayload 与 renderPathIndicator 放进最小桩里执行。"""

    script = "\n".join(
        [
            "const COMPACT_CHECKED = " + ("true" if checked else "false") + ";",
            'const FIELDS = {"source-mods":"Romanceable Rasmodius",'
            '"recent-facts":"",'
            '"conversation-channel":"face_to_face",'
            '"provider-mode":"auto",'
            '"display-name":"Rasmodia"};',
            "const badge = { textContent: \"\", title: \"\", classList: { toggle() {} } };",
            "const $ = (id) => id === \"path-indicator\""
            " ? badge"
            " : { value: Object.prototype.hasOwnProperty.call(FIELDS, id) ? FIELDS[id] : \"\","
            " checked: COMPACT_CHECKED };",
            "const state = { initialHistory: [], history: [] };",
            'function selectedNpc() { return { npcId: "Wizard", displayName: "Rasmodia" }; }',
            "function evaluationProfileForNpc() { return null; }",
            'function sceneState() { return { season: "春" }; }',
            _function_source(html, "compactPathEnabled"),
            _function_source(html, "renderPathIndicator"),
            _function_source(html, "buildPayload"),
            "renderPathIndicator();",
            "process.stdout.write(JSON.stringify("
            '{ payload: buildPayload("今天过得怎么样？"), indicator: badge.textContent }));',
        ]
    )
    path = tmp_path / ("page-script-%s.js" % ("on" if checked else "off"))
    path.write_text(script, encoding="utf-8")

    result = subprocess.run(
        ["node", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_build_payload_sends_compact_prompt_only_when_the_switch_is_on(
    tmp_path: Path,
) -> None:
    html = _chat_html()

    on = _run_page_script(tmp_path, html, checked=True)
    assert on["payload"]["compactPrompt"] is True

    # 取消勾选时必须**不带这个字段**，而不是带一个 false ——
    # 后端的判定是 `payload.get("compactPrompt") is True`，
    # 少发字段与发 false 在这里等价，但「不发」才是与旧页面一致的对照形态。
    off = _run_page_script(tmp_path, html, checked=False)
    assert "compactPrompt" not in off["payload"]


def test_path_indicator_text_follows_the_switch(tmp_path: Path) -> None:
    html = _chat_html()

    assert _run_page_script(tmp_path, html, checked=True)["indicator"] == (
        "路径：游戏端（紧凑）"
    )
    assert _run_page_script(tmp_path, html, checked=False)["indicator"] == (
        "路径：完整（非游戏端）"
    )


def test_context_summary_shows_which_path_the_preview_used() -> None:
    """预览面板自己回显路径 —— 它和实发走同一个判定，能自证同源。"""

    html = _chat_html()
    render_body = _function_body(html, "renderContext")

    assert '"预览路径"' in render_body
    assert 'context.compactPrompt?"游戏端（紧凑）":"完整（非游戏端）"' in render_body


def test_game_path_switch_does_not_break_the_embedded_scripts() -> None:
    """页面新脚本必须仍然通过 node 语法检查（集成工作台会把脚本包进 IIFE）。"""

    for route in ("/test/chat", "/test"):
        html = TestClient(app).get(route).text
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


# --- 3. 预览与实发必须同源 -------------------------------------------------


def test_preview_and_dialogue_agree_on_the_compact_path(monkeypatch: Any) -> None:
    router = RecordingRouter()
    builder = PathRecordingPromptBuilder()
    monkeypatch.setattr(app_module, "provider_router", router)
    monkeypatch.setattr(app_module, "prompt_builder", builder)

    payload = {**BASE_PAYLOAD, "provider": "cloud", "compactPrompt": True}
    client = TestClient(app_module.app)

    preview = client.post("/api/context/preview", json=payload)
    assert preview.status_code == 200
    body = preview.json()
    assert body["compactPrompt"] is True
    preview_names = [item["name"] for item in body["promptSummary"]]
    preview_call = builder.calls[-1]

    response = client.post("/api/dialogue/test", json=payload)
    assert response.status_code == 200
    sent_call = builder.calls[-1]
    sent_names = [message["name"] for message in router.messages or []]

    assert preview_call == sent_call == {"compact": True, "runtimeCompact": True}
    assert preview_names == sent_names
    assert preview_names[0] == "scene_compact"


def test_preview_and_dialogue_agree_on_the_full_path_without_the_flag(
    monkeypatch: Any,
) -> None:
    router = RecordingRouter()
    builder = PathRecordingPromptBuilder()
    monkeypatch.setattr(app_module, "provider_router", router)
    monkeypatch.setattr(app_module, "prompt_builder", builder)

    payload = {**BASE_PAYLOAD, "provider": "cloud"}
    client = TestClient(app_module.app)

    preview = client.post("/api/context/preview", json=payload)
    assert preview.status_code == 200
    body = preview.json()
    assert body["compactPrompt"] is False
    preview_call = builder.calls[-1]

    response = client.post("/api/dialogue/test", json=payload)
    assert response.status_code == 200
    sent_call = builder.calls[-1]

    assert preview_call == sent_call == {"compact": False, "runtimeCompact": False}
    assert [item["name"] for item in body["promptSummary"]][0] == "game_state_full"


def test_preview_reads_the_flag_through_the_same_field_as_the_dialogue_route(
    monkeypatch: Any,
) -> None:
    """`compactPrompt: 1` 这类松散输入曾经让两条路各走一边。

    修复前预览用的是 `payload.get("compactPrompt") is True`（`1 is True` 为假），
    而 `/api/dialogue/test` 用的是 pydantic 归一化后的 `True` —— 预览显示完整、
    实发却走紧凑。现在两边都从 `DialogueTestRequest.compact_prompt` 取值。
    """

    router = RecordingRouter()
    builder = PathRecordingPromptBuilder()
    monkeypatch.setattr(app_module, "provider_router", router)
    monkeypatch.setattr(app_module, "prompt_builder", builder)

    payload = {**BASE_PAYLOAD, "provider": "cloud", "compactPrompt": 1}
    client = TestClient(app_module.app)

    preview = client.post("/api/context/preview", json=payload)
    assert preview.status_code == 200
    assert preview.json()["compactPrompt"] is True
    preview_call = builder.calls[-1]

    response = client.post("/api/dialogue/test", json=payload)
    assert response.status_code == 200
    sent_call = builder.calls[-1]

    assert preview_call == sent_call == {"compact": True, "runtimeCompact": True}


# --- 4. 同类页面各自走哪条路径 ---------------------------------------------


def test_group_dialogue_keeps_the_full_card_path(monkeypatch: Any) -> None:
    """群聊页**不该**加这个开关：游戏端群聊本来就走完整卡组。

    `GroupDialogueRequest` 没有紧凑字段，`_group_participant_prompts` 构造的
    内部 payload 也不带它，因此回落分支固定给出完整路径。这条断言把
    「群聊现在是对的」变成可执行的证据，而不是口头结论。
    """

    builder = PathRecordingPromptBuilder()
    monkeypatch.setattr(app_module, "prompt_builder", builder)

    participants = [
        SimpleNamespace(npc_id="Wizard", source_mods=[], game_state=None),
        SimpleNamespace(npc_id="Sophia", source_mods=[], game_state=None),
    ]
    request = SimpleNamespace(message="你们好", channel="remote", game_state=None)

    prompts = app_module._group_participant_prompts(participants, request)

    assert set(prompts) == {"Wizard", "Sophia"}
    assert builder.calls
    assert all(call == {"compact": False, "runtimeCompact": False} for call in builder.calls)
    # 请求模型里根本没有这个字段：连「不小心传进来」都不会被接受。
    assert "compact_prompt" not in GroupDialogueRequest.model_fields


def test_group_lab_page_never_sends_the_compact_flag() -> None:
    html = TestClient(app).get("/test/group").text

    assert "/api/dialogue/group" in html
    assert "compactPrompt" not in html


def test_static_pages_do_not_touch_the_dialogue_api() -> None:
    """界面预览与群聊复核页只画界面，不调对话接口 —— 不需要路径开关。"""

    client = TestClient(app)
    for route in ("/test/ui", "/test/ui-redesign", "/test/group/review"):
        html = client.get(route).text

        assert html
        assert "fetch(" not in html, route
        assert "/api/dialogue/" not in html, route
        assert "compactPrompt" not in html, route
