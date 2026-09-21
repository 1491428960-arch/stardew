"""roleGuidance 与 persona 措辞必须是「对象导向」，不是「过程导向」（2026-09-21）。

背景（用户实测索菲亚）：「刚把最后一层**罩光**放到窗边」——「罩光」是绘画工序
术语，很生僻，而索菲亚的定位是轻快口语：她 311 条原文对话里绘画相关词只有 4 处
（两处还是「画眼线」），`varnish` / 罩光 / 清漆 **0 命中**。

诊断出的上游不是语料，是**指令本身**：
`_CONVERSATION_LEAD_ROLE_GUIDANCE["Sophia"]` 当时写着
「可以从葡萄品种、**发酵过程或绘画过程**选一个具体细节」——
模型被要求讲「过程」，而「过程」在模型先验里就是工序名（罩光、罩染、打底）。

本文件钉住改写后的口径：**要求仍然具体，但落在一道工序上的写法不许回来。**

2026-09-21 二轮（同一天，用户实测「总是谈画」）：索菲亚那条又从「对象导向」推进到
「**跨语义簇的落点池 + 同一类最多连续两次**」——一轮那次的四个落点（葡萄／酒窖／
画笔／画里的具体东西）仍全在酿造 + 绘画这一簇里，模型照样连着几轮不换。
本文件的"不讲过程"闸保持不变，跨簇与轮换上限由
`test_stage_policy.py::test_sophia_conversation_lead_guidance_bridges_cellar_and_creative_topics`
钉住。

刻意**不**禁用「过程」两个字本身：`female-bachelors.json` 里 Shane 的
avoid「把恢复过程说成已经彻底解决」是在**禁止**把过程说死，方向相反。
判据只抓「从／说／讲／落到 … 过程」这种**生成指令**形态。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from stardew_ai_bridge.stage_policy import _CONVERSATION_LEAD_ROLE_GUIDANCE

ROOT = Path(__file__).resolve().parents[2]

_PROCESS_DIRECTIVE = re.compile(r"(从|说|讲|落到|挑)[^。；]{0,24}过程")


def test_sophia_guidance_lands_on_objects_not_on_a_process() -> None:
    text = _CONVERSATION_LEAD_ROLE_GUIDANCE["Sophia"]

    assert "绘画过程" not in text
    assert "发酵过程" not in text
    assert _PROCESS_DIRECTIVE.search(text) is None
    # 2026-09-21 二轮：落点池从「同一个语义簇里的四个词」改成「跨簇 + 轮换上限」。
    # 一轮那次改的是措辞形状（对象而非工序），没有解决「总是谈画」——四个落点
    # 仍然全在酿造 + 绘画这一簇里。跨簇与上限由这两条钉住。
    assert "同一类最多连续两次" in text
    assert "小镇日常" in text
    assert "安全感与新开始" in text


def test_no_role_guidance_asks_the_model_to_narrate_a_process() -> None:
    """回归闸：任何角色的 roleGuidance 都不该要求模型「讲过程」。"""

    offenders = {
        role: _PROCESS_DIRECTIVE.search(text).group(0)
        for role, text in _CONVERSATION_LEAD_ROLE_GUIDANCE.items()
        if _PROCESS_DIRECTIVE.search(text)
    }

    assert offenders == {}


def _persona_profiles(path: Path) -> list[tuple[str, dict]]:
    """人设文件是 ``{mod, sourceMods, personas: {npc: profile}}``。

    直接遍历顶层会走到 ``mod`` / ``sourceMods`` 这两个包装键上，
    一个角色都扫不到——那是**假通过**，所以这里显式下钻。
    """

    data = json.loads(path.read_text(encoding="utf-8"))
    personas = data.get("personas") if isinstance(data, dict) else None
    if not isinstance(personas, dict):
        return []
    return [(key, value) for key, value in personas.items() if isinstance(value, dict)]


def test_persona_voice_styles_have_no_process_directives() -> None:
    """全量人设回归：voiceStyle 里不再有「讲过程」这种生成指令。"""

    offenders: list[str] = []
    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        for npc, profile in _persona_profiles(path):
            voice = profile.get("voiceStyle")
            if not isinstance(voice, dict):
                continue
            for field in ("responseRules", "sentencePattern", "signatureMoves"):
                for item in voice.get(field) or []:
                    if isinstance(item, str) and _PROCESS_DIRECTIVE.search(item):
                        offenders.append(f"{path.name}:{npc}.{field}: {item[:50]}")

    assert offenders == []


@pytest.mark.parametrize(
    ("npc", "old", "new"),
    [
        ("Penny", "谈教学时说具体的学习过程", "谈教学时说具体的课堂小事"),
    ],
)
def test_penny_teaching_rule_points_at_classroom_objects(
    npc: str,
    old: str,
    new: str,
) -> None:
    """同一原则的第二处：Penny「说具体的学习过程」→「说具体的课堂小事」。"""

    data = json.loads(
        (ROOT / "data" / "personas" / "vanilla.json").read_text(encoding="utf-8")
    )
    rules = data["personas"][npc]["voiceStyle"]["responseRules"]
    joined = "；".join(rules)

    assert new in joined
    assert old not in joined


def test_harvey_and_victor_keep_their_existing_object_focus() -> None:
    """核查记录：这两个角色**本来就**是对象导向，本轮刻意没动。

    Harvey 在 roleGuidance 里已经有「专业信息必须说得日常、简短」；
    Victor 的人设写的是「落到材料、结构或实际用途」+「用复杂术语掩盖没有回答
    玩家的问题」——两者都不需要改，这条测试防止有人"顺手"把它们改掉。
    """

    harvey = _CONVERSATION_LEAD_ROLE_GUIDANCE["Harvey"]
    assert "专业信息必须说得日常、简短" in harvey

    sve = json.loads(
        (ROOT / "data" / "personas" / "sve.json").read_text(encoding="utf-8")
    )
    victor = sve["personas"]["Victor"]["voiceStyle"]
    assert any("材料" in rule and "结构" in rule for rule in victor["responseRules"])
    assert any("复杂术语" in rule for rule in victor["avoid"])
