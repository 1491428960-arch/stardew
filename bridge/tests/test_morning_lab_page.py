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
    """取 `day2-lewis` 那条的开场白。

    ⚠ **不要写成 `listed[0]`。** 那等于把「数组第一条是谁」当成契约，而场景是
    **按天调度的数据**：往数组前面插一条池子型预设，`listed[0]` 就指向了别的
    场景，而这些测试断言的是「拿 day2-lewis 的开场白去 preview，能认出来」。
    2026-09-27 加第一批池子型预设时就是这么翻的 —— 报错说期望 `day2-lewis`、
    实际 `spring-pool-abigail-01`，看着像匹配逻辑坏了，其实是 fixture 取错了条。

    匹配逻辑（`match_scenario_by_history`）本身没问题：它去空白后**逐字**比对
    `opening`，所以只要拿到的是同一条预设的原文就能命中。
    """
    by_id = {str(item["scenarioId"]): item for item in listed}
    assert "day2-lewis" in by_id, "真实数据里应当有 day2-lewis"
    return str(by_id["day2-lewis"]["opening"])


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


def test_plan_fires_an_after_event_message(client: TestClient) -> None:
    """`recentEventIds` 必须真的能穿过 HTTP —— 否则事件型就是「数据写对但永不生效」。

    这是本项目反复踩的那类坑：`morning_scenario.py` 的单元测试全绿、页面上也
    看得见这条预设，但游戏端送来的字段在端点这层被丢掉，于是它永远不触发。

    第 85 天（冬季第 1 天）本来就有一条 `winter-1-george`（dated 型），所以这个测试
    同时证明了两件事：不送信号时走日历，送了信号时**事件型把 dated 也顶掉**。

    ⚠ 这里刻意**不假设**不送信号时命中的是池子还是 dated —— 那取决于当天挂着什么。
    断言只钉住「不是事件型」，这样加删日历预设不会误伤它。
    """

    plain = client.post("/api/morning/plan", json={"dayIndex": 84}).json()["messages"]
    assert plain, "冬季第 1 天本该有日历型预设"
    assert not plain[0]["scenarioId"].startswith("event-after-")

    fired = client.post(
        "/api/morning/plan",
        json={"dayIndex": 84, "recentEventIds": ["19"]},
    ).json()["messages"]

    assert [item["scenarioId"] for item in fired] == ["event-after-evelyn-cookies"]
    assert fired[0]["displayName"] == "艾芙琳"


def test_plan_rejects_an_unknown_field(client: TestClient) -> None:
    """`extra="forbid"` 是这道契约的护栏，别顺手放开。

    游戏端多送一个字段就 422 是**有意的**：它逼着新增信号走一次显式决定
    （像 `recentEventIds` 那样在 `MorningPlanRequest` 的 docstring 里写明判据），
    而不是让请求体悄悄变成什么都往里塞的口袋。
    """

    response = client.post(
        "/api/morning/plan",
        json={"dayIndex": 84, "friendshipHearts": 8},
    )

    assert response.status_code == 422


def test_page_carries_the_opening_source(listed: list[dict[str, object]]) -> None:
    """每条预设都要写清开场白是哪来的。

    2026-09-27 起有**两种**合法来源（`vanilla:` 逐字取原话 / `persona:` 基于
    persona 创作），由 `test_morning_scenario.py` 里两套守卫分别核对。
    这一层只保证字段**非空** —— 页面得让作者看见自己标的是哪一种。
    留空的话两套守卫都会跳过它，等于一条开场白谁也不守。
    """

    for item in listed:
        assert str(item["openingSource"]).strip(), f"{item['scenarioId']} 没写 _openingSource"


def test_page_exposes_direction_boundaries_and_trigger(
    listed: list[dict[str, object]],
) -> None:
    # ⚠ 按 id 取，不按 `listed[0]`：数组顺序是 data/scenarios/morning.json 的
    # 书写顺序，而这个页面本来就是给人看数据的，往前面插一条就会让 `listed[0]`
    # 变成另一条 —— 和 `opening` fixture 踩的是同一个坑。
    by_id = {str(item["scenarioId"]): item for item in listed}
    first = by_id["day2-lewis"]
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
