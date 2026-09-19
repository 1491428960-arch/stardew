"""群聊「开场」在**请求校验层**的合法性。

## 为什么单独写这个文件（2026-09-20 的真实教训）

Bridge 侧的「空玩家消息 ⇒ 开场」语义早已在 `group_conversation` 里实现并有单元测试，
但**端到端不通**：真机测试时接受邀约后 NPC 不说话，玩家点「重试」才说话。

原因在**更靠前的一层**——`GroupDialogueRequest` 的 `model_validator` 里写着：

    if not self.message:
        raise ValueError("多人对话消息不能为空")

于是开场请求（空消息）在 Pydantic 校验阶段就吃 **422**，
`GroupDialogueMenu` 把它当成「请求失败」，提示可以重试；
而**重试走的是 `retry=True` 分支，发的是一句非空的占位文案**，于是成功。

**教训**：单元测试全绿 ≠ 功能可用。这个文件专门盯住**请求能不能被接受**这一层，
并同时覆盖模型层与 API 层。

## 新语义

**「消息为空」只有在「历史也为空」时才是合法的开场**（首轮、NPC 自己起头）；
已经聊过还发空消息依然应当被拒——那是无意义的请求，不是开场。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from stardew_ai_bridge.app import app
from stardew_ai_bridge.models import GroupDialogueRequest

_PARTICIPANTS = [
    {"npcId": "Abigail", "displayName": "Abigail"},
    {"npcId": "Sebastian", "displayName": "Sebastian"},
]


def _payload(message: str, history: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "message": message,
        "provider": "fake",
        "strategy": "multi_turn",
        "channel": "remote",
        "participants": _PARTICIPANTS,
        "activeSpeakerNpcId": "Abigail",
        "turnCount": 2,
        "history": history or [],
    }


def _history_entry() -> dict[str, object]:
    return {"speakerType": "player", "speakerId": "player", "content": "你们好啊"}


# --- 模型层 -----------------------------------------------------------------


def test_an_empty_message_with_no_history_is_a_legal_opening() -> None:
    request = GroupDialogueRequest.model_validate(_payload(""))

    assert request.message == ""


def test_a_whitespace_message_with_no_history_is_also_legal() -> None:
    # 纯空白也按开场处理（组 prompt 侧用的是 strip()）。
    request = GroupDialogueRequest.model_validate(_payload("   "))

    assert request.message.strip() == ""


def test_an_empty_message_with_history_is_still_rejected() -> None:
    import pytest

    with pytest.raises(Exception) as excinfo:
        GroupDialogueRequest.model_validate(_payload("", [_history_entry()]))

    assert "不能为空" in str(excinfo.value)


def test_a_real_message_with_history_is_legal() -> None:
    request = GroupDialogueRequest.model_validate(_payload("那你们呢？", [_history_entry()]))

    assert request.message == "那你们呢？"


# --- API 层（端到端：这才是上一次漏掉的那层）-------------------------------


def test_the_endpoint_accepts_an_opening_request() -> None:
    client = TestClient(app)

    response = client.post("/api/dialogue/group", json=_payload(""))

    assert response.status_code == 200, response.text
    body = response.json()
    # fake provider 会返回一轮可用的对白——说明开场请求真的走到了生成逻辑。
    assert body["turns"], body


def test_the_endpoint_still_rejects_an_empty_message_after_history() -> None:
    client = TestClient(app)

    response = client.post("/api/dialogue/group", json=_payload("", [_history_entry()]))

    assert response.status_code == 422


def test_the_endpoint_still_requires_a_message_for_a_normal_turn() -> None:
    # 回归保护：非开场（有历史）时行为不变。
    client = TestClient(app)

    response = client.post("/api/dialogue/group", json=_payload("你们周末干嘛？", [_history_entry()]))

    assert response.status_code == 200
