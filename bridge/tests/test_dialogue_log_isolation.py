"""真实对话日志**在测试期间必须关闭**（护栏）。

`bridge/tests/conftest.py` 用 autouse fixture 设 `BRIDGE_DIALOGUE_LOG=0`。
这个文件守两件事：

1. 那个开关**确实生效**（不是写了没人读）；
2. `_record_dialogue` 在关掉时**一个字节都不写**。

背景（2026-09-26）：当天 `artifacts/dialogue-log/2026-09-26.jsonl` 271 条里
有 205 条是跑测试留下的 `latencyMs=0` 假记录，把实机那 5 批淹掉了。
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from stardew_ai_bridge.app import DialogueResponse, _record_dialogue

_LOG_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "dialogue-log"


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def test_dialogue_log_switch_is_off_during_tests() -> None:
    assert os.environ.get("BRIDGE_DIALOGUE_LOG") == "0", (
        "测试必须关掉真实对话日志：它会追加到 artifacts/dialogue-log/<日期>.jsonl，"
        "而那正是实机验证唯一的观测通道——测试写进去就分不清哪些是真机上发生的"
    )


def test_record_dialogue_writes_nothing_when_disabled() -> None:
    """开关关着时，直接调 `_record_dialogue` 也不得产生任何行。"""
    today = _LOG_DIR / f"{datetime.now():%Y-%m-%d}.jsonl"
    before = _line_count(today)

    _record_dialogue(
        {"npcId": "Lewis", "displayName": "刘易斯", "message": "测试不该落盘"},
        DialogueResponse(reply="测试回复", provider="fake", latencyMs=1),
    )

    assert _line_count(today) == before, (
        "关掉开关后仍然写进了真实对话日志——`_record_dialogue` 的读取点失效了"
    )
