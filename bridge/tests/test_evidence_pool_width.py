"""轮转池的**宽度**：池子必须比「每轮注入条数」宽。

## 为什么单独钉这一条

`prompts.py` 的 `_MAX_SPEECH_EVIDENCE`（=6）一度同时当两个用途：**轮转池大小**
（`_rotate_evidence_by_turn` 的 `pool_size`）与**每轮注入条数**（`speechEvidence[:6]`）。
两者共用一个 6，于是"池子"永远只有 6 条可转 —— 而 §13.2 的实测正是这样：
**槽位 20 次触发只覆盖了 6 条素材**，其余素材一次都没被建议过。

作者当时已经写明这个改动是免费的（`prompts.py` L352）：

> 池大小**不影响 prompt 体积**（每轮仍只注入 1 条），所以放宽是免费的；
> 代价只是每轮那 1 条从「前 4 名」变成「前 6 名」里轮，单条质量略降。

但它被 `profile_index.speech_evidence` 里硬编码的 `min(int(limit), 6)` 挡住了 ——
**调用方传多大都拿不到更多**。本文件钉住拆开之后的行为。

## 判据为什么是「覆盖到多少条不同素材」

不能断言"注入条数变多"（那会真的把 prompt 撑长，正是要避免的），
也不能断言某个内部常量（改个名字就失效）。**该量的是行为**：
连续 20 轮里，轮转一共建议过多少**不同**的素材。池子只有 6 条时这个数上不去。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bridge" / "src"))

from stardew_ai_bridge import app as app_module  # noqa: E402
from stardew_ai_bridge.app import _build_context  # noqa: E402
from stardew_ai_bridge.profile_index import ProfileIndexStore  # noqa: E402

INDEX_PATH = (
    ROOT
    / "data"
    / "generated"
    / "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)

SOURCE_MODS = ["FlashShifter.StardewValleyExpandedCP"]

# 旧池宽。池子一旦真的被放宽，20 轮覆盖必然超过它。
_OLD_POOL_WIDTH = 6


@pytest.fixture(autouse=True)
def _real_profile_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """把真实索引挂到 `prompt_builder` 上。

    为什么必须显式挂：`app` 在 import 时就按环境变量 `BRIDGE_PROFILE_INDEX`
    构造了全局 store（`app.py`），而测试进程里没有这个变量 —— 于是 store 是空的，
    **素材一条都取不到，`speech_evidence` 卡根本不会出现**，本文件的断言会以
    "卡数为 0"这种与主题无关的方式失败。探针一直带着那个环境变量，所以从没暴露。

    这里直接注入而不是设环境变量：环境变量是同进程共享的，会波及其他测试文件。
    """

    if not INDEX_PATH.exists():
        pytest.skip(f"缺少索引文件：{INDEX_PATH}")
    monkeypatch.setattr(
        app_module.context_builder,
        "profile_index",
        ProfileIndexStore(INDEX_PATH),
    )


def _completed_event_ids(npc_id: str) -> list[str]:
    if not INDEX_PATH.exists():
        pytest.skip(f"缺少索引文件：{INDEX_PATH}")
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return sorted(
        {
            str(sample.get("eventId", "")).strip()
            for sample in index.get("speechEvidence", [])
            if str(sample.get("npcId", "")) == npc_id
            and str(sample.get("eventId", "")).strip()
        }
    )


def _payload(history: list[dict[str, str]], events: list[str]) -> dict[str, object]:
    return {
        "npcId": "Sophia",
        "displayName": "索菲亚",
        # 走 `topic`（她主动开口）而非 `chat`：`topic` 下 `player_input` 被强制为空，
        # 素材不被"普通闲聊只留日常对白"那条过滤削掉 —— 轮转池这件事本身
        # 也正是在这条路径上被实测出来的（§13.2）。
        "message": "",
        "intent": "topic",
        "channel": "remote",
        "compactPrompt": True,
        "sourceMods": SOURCE_MODS,
        "recentFacts": [],
        "history": [dict(item) for item in history[-6:]],
        "recentReplies": [item["content"] for item in history[-24:]],
        "gameState": {
            # `_build_context` 收的是原始 dict，可以带 relationshipStage；它**不能**
            # 出现在 `DialogueTestRequest` 里（那个模型是 extra="forbid"），探针是在
            # 构造请求前 pop 掉的。少了这个字段素材会被阶段门控整类滤空。
            "relationshipStage": "dating",
            "friendshipHearts": 8,
            "sourceMods": SOURCE_MODS,
            "completedEventIds": events,
        },
    }


def _injected_evidence(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    cards = [m for m in messages if m.get("name") == "speech_evidence"]
    assert len(cards) == 1, f"speech_evidence 卡应恰好一张，实际 {len(cards)}"
    payload = json.loads(str(cards[0]["content"]))
    return list(payload.get("speechEvidence") or [])


def test_the_rotation_pool_is_wider_than_the_injection_cap() -> None:
    """20 轮里被建议过的**不同**素材数，必须超过旧的池宽 6。"""

    events = _completed_event_ids("Sophia")
    assert events, "索菲亚应当有可解锁的事件素材"

    seen: set[str] = set()
    history: list[dict[str, str]] = []
    for turn in range(20):
        _context, messages = _build_context(
            _payload(history, events), compact_prompt=True
        )
        injected = _injected_evidence(messages)
        if injected:
            seen.add(str(injected[0].get("text", "")))
        # 她的回复逐轮变化 —— 轮转靠它做偏移，也是"说过没有"的判据来源。
        history.append({"role": "user", "content": "嗯，然后呢"})
        history.append(
            {
                "role": "assistant",
                "content": (
                    f"我刚才把第 {turn} 块料子裁好了，针脚比上一块密一点。"
                    f"窗外的光一点点斜过来，落在桌角那卷线上。"
                ),
            }
        )

    assert len(seen) > _OLD_POOL_WIDTH, (
        f"20 轮只建议过 {len(seen)} 条不同素材（旧池宽 {_OLD_POOL_WIDTH}）——"
        "轮转池仍被 accessor 的 cap 钉死，放宽没有生效"
    )


def test_widening_the_pool_does_not_widen_what_is_injected() -> None:
    """放宽池子**不得**增加每轮注入条数 —— 这是"免费"的全部含义。"""

    events = _completed_event_ids("Sophia")
    history: list[dict[str, str]] = []
    for turn in range(6):
        _context, messages = _build_context(
            _payload(history, events), compact_prompt=True
        )
        injected = _injected_evidence(messages)
        assert len(injected) <= 1, (
            f"第 {turn + 1} 轮注入 {len(injected)} 条素材；"
            "轮转路径每轮只该注入 1 条，多注入就是把 prompt 撑长"
        )
        history.append({"role": "user", "content": "嗯，然后呢"})
        history.append(
            {"role": "assistant", "content": f"这是第 {turn} 轮的回复，随便说点什么。"}
        )
