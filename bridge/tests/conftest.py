"""测试期间的全局开关。

## 为什么是 autouse：**测试不得写进真实对话日志**

`artifacts/dialogue-log/<日期>.jsonl` 是**实机验证唯一的观测通道**——
SMAPI 日志只记目标/频道/延迟/`fallback`、**不记回复正文**，存档里的聊天记录
只在**保存游戏**时写入，于是「刚才那句她到底说了什么」在两边都查不到
（这正是 ㉞ 加这个文件的理由）。

而它默认是**开着**的：`TestClient` 每打一次 `/api/dialogue/test` 就追加一条。
2026-09-26 08:13 那次全量验证之后，当天 271 条记录里有 **205 条是 `latencyMs=0`
的测试产物**，真正要看的实机那 5 批（07:35–07:55）混在里面几乎认不出来 ——
**观测通道被自己的测试污染，等于没有观测通道。**

开关是 `BRIDGE_DIALOGUE_LOG=0`。`app._record_dialogue` 是在**调用时**读
`os.environ`（不是 import 时），所以在这里设来得及。

用 `autouse=True` 而不是让每个测试自己声明：**没有哪个测试作者会记得这件事**，
而忘了的代价是静默的（日志照样生成，只是混进了假数据）。
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _disable_real_dialogue_log() -> None:
    os.environ["BRIDGE_DIALOGUE_LOG"] = "0"
