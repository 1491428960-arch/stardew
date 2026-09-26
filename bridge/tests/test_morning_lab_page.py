"""晨间预设的游戏外审阅页与端点（`/test/morning`、`/api/morning/scenarios`）。

关注两件事：

1. **页面上审的那句话，就是游戏端会收到的那句。** 预设的价值全在措辞上，
   而 `/api/morning/plan`（游戏端读）与 `/api/morning/scenarios`（页面读）
   是两条路径——它们漂移时不会报错，只是「你在页面上审的」和「她真说的」
   变成了两句不同的话。
2. **认人回显可用。** 逐字比对失败是**静默**的（只少一层方向约束，
   回复照样正常生成），页面靠 `morningScenarioId` 把「这次认出来了没有」
   变成看得见的一行；没有它，试聊的效果无从归因。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stardew_ai_bridge.app import app

ROOT = Path(__file__).resolve().parents[2]
REAL_MORNING = ROOT / "data" / "scenarios" / "morning.json"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def listed(client: TestClient) -> list[dict[str, object]]:
    response = client.get("/api/morning/scenarios")
    assert response.status_code == 200
    return list(response.json()["scenarios"])


@pytest.fixture
def opening(listed: list[dict[str, object]]) -> str:
    assert listed
    return str(listed[0]["opening"])


def _file_scenarios() -> list[dict[str, object]]:
    payload = json.loads(REAL_MORNING.read_text(encoding="utf-8"))
    return list(payload.get("scenarios") or [])


def test_scenarios_endpoint_reads_the_real_file(
    listed: list[dict[str, object]],
) -> None:
    expected = _file_scenarios()
    assert expected, "真实数据文件里应当有预设"
    assert [item["scenarioId"] for item in listed] == [item["id"] for item in expected]


def test_page_text_matches_what_the_game_receives(
    client: TestClient, listed: list[dict[str, object]]
) -> None:
    """两条读取路径给出的开场白必须逐字相同。"""

    by_id = {item["scenarioId"]: item for item in listed}
    # ⚠ 这里必须送**游戏端的计数器**（`Game1.Date.TotalDays`），不是「第几天」：
    # 第 2 天在游戏里是 1（第 1 天 = 0）。原先这里写死 2，于是离线全绿、
    # 实机却永远收不到——详见下面 test_plan_takes_the_game_day_counter。
    planned = client.post("/api/morning/plan", json={"dayIndex": 1}).json()["messages"]
    assert planned, "第 2 天（TotalDays=1）应当有一条预设"
    for message in planned:
        page_item = by_id[message["scenarioId"]]
        assert page_item["opening"] == message["opening"]
        assert page_item["npcId"] == message["npcId"]
        assert page_item["displayName"] == message["displayName"]


def test_plan_takes_the_game_day_counter(client: TestClient) -> None:
    """⓵ 锁住「游戏的天数计数器」与「人话第几天」之间那 1 天的换算。

    `data/scenarios/morning.json` 的 `absoluteDay.dayIndex` 写的是**人话**
    （「第 2 天」= 2），而游戏端送进 `RequestMorningPlanAsync` 的是
    `Game1.Date.TotalDays`（第 1 年春季第 1 天 = 0）—— 两者差 1。

    **2026-09-26 实机踩到**：预设挂在「第 2 天」，玩家真的过到了第 2 天，
    Bridge 也真的被调用了两次（`POST /api/morning/plan` → 200 OK），
    但游戏里一条消息都没有。送进来的是 1、配置等的是 2，**永远匹配不上**；
    而当时的离线测试恰好用 `dayIndex=2` 去问，正好把这个错位盖住了 ——
    测试写对了逻辑、却锁死了错误的语义。
    """

    # 第 1 天（TotalDays = 0）：那天早上还压在开场动画里，没有预设。
    assert client.post("/api/morning/plan", json={"dayIndex": 0}).json()["messages"] == []
    # 第 2 天（TotalDays = 1）：命中 day2-lewis。
    got = client.post("/api/morning/plan", json={"dayIndex": 1}).json()["messages"]
    assert [item["scenarioId"] for item in got] == ["day2-lewis"]


def test_page_carries_the_opening_source(listed: list[dict[str, object]]) -> None:
    """开场白必须能看出取自哪条原话（模块硬约束第 1 条）。"""

    for item in listed:
        assert str(item["openingSource"]).strip()


def test_page_exposes_direction_boundaries_and_trigger(
    listed: list[dict[str, object]],
) -> None:
    first = listed[0]
    assert str(first["direction"]).strip()
    assert first["boundaries"]
    assert first["dayIndex"] == 2


def test_morning_route_renders_its_own_view(client: TestClient) -> None:
    html = client.get("/test/morning").text
    assert 'id="morning-scenario-view"' in html
    assert 'data-workspace-view="morning"' in html
    assert "/api/morning/scenarios" in html
    # 试聊那一栏要显示「这一轮发了几次请求」：延迟含重试，不显示次数时
    # 3.2s 与 21.1s 无法区分是上游慢还是重试叠加（字段加了没人消费 = 白加）。
    assert "requestCount" in html
    # 占位符必须都被替换掉——残留会以字面量显示在页面上。
    assert "__MORNING_CLASS__" not in html
    assert "__MORNING_CURRENT__" not in html


def test_morning_tab_is_highlighted_only_on_its_own_route(client: TestClient) -> None:
    morning_html = client.get("/test/morning").text
    other_html = client.get("/test").text
    assert 'href="/test/morning"' in other_html
    assert 'data-view-target="morning" aria-current="page"' in morning_html
    assert 'data-view-target="morning" aria-current="page"' not in other_html


def test_the_other_three_views_still_work(client: TestClient) -> None:
    for route, view in (("/test", "cases"), ("/test/chat", "chat"), ("/raw", "raw")):
        html = client.get(route).text
        assert f'data-workspace-view="{view}"' in html
        assert f"__{view.upper()}_CURRENT__" not in html


def test_preview_reports_the_matched_scenario(client: TestClient, opening: str) -> None:
    response = client.post(
        "/api/context/preview",
        json={
            "npcId": "Lewis",
            "displayName": "刘易斯",
            "message": "还行吧，就是那张床一翻身就响。",
            "intent": "chat",
            "compactPrompt": True,
            "history": [{"role": "assistant", "content": opening}],
        },
    )
    assert response.status_code == 200
    assert response.json()["morningScenarioId"] == "day2-lewis"


def test_preview_does_not_match_an_unrelated_first_message(client: TestClient) -> None:
    response = client.post(
        "/api/context/preview",
        json={
            "npcId": "Lewis",
            "displayName": "刘易斯",
            "message": "早上好。",
            "intent": "chat",
            "compactPrompt": True,
            "history": [{"role": "assistant", "content": "今天天气不错。"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["morningScenarioId"] is None


def test_preview_reports_none_without_history(client: TestClient) -> None:
    response = client.post(
        "/api/context/preview",
        json={"npcId": "Lewis", "message": "早上好。", "compactPrompt": True},
    )
    assert response.status_code == 200
    assert response.json()["morningScenarioId"] is None


def test_tryout_payload_is_accepted_by_the_dialogue_endpoint(
    client: TestClient, opening: str
) -> None:
    """页面「发一句」用的请求体必须真能被 `/api/dialogue/test` 接受。

    它防的是「前端拼的字段后端不认」——那种失败在页面上只表现成一句
    红字，很容易被当成模型的问题。
    """

    response = client.post(
        "/api/dialogue/test",
        json={
            "npcId": "Lewis",
            "displayName": "刘易斯",
            "message": "还行吧，就是那张床一翻身就响。",
            "provider": "fake",
            "intent": "chat",
            "compactPrompt": True,
            "history": [{"role": "assistant", "content": opening}],
        },
    )
    assert response.status_code == 200
    assert str(response.json()["reply"]).strip()
