"""「编造回忆」的分层口径（2026-09-21 用户拍板）。

旧口径是**一刀切**：`_SHARED_POLICIES["close"]` 写「不虚构共同经历」、
`married` 写「不凭空补写家庭经历」，熟稔度档写「没发生过的共同回忆」。

用户实测那句「画里那排葡萄架，只有你陪我支过」按旧口径算违规，但用户的口径是：

* **角色的日常补全**（「你陪我支过葡萄架」「你尝过我酿的那批酒」）→ ✅ 允许，
  这是**她的世界**里的合理拓展；
* **玩家侧的事实**（「你上次说你妈妈病了」「你说过你不爱吃鱼」）→ ❌ 禁止，
  玩家没说过，会与他的认知直接冲突。

这三处此前**没有任何测试钉住**，改措辞不会被拦住。本文件把改写后的口径钉住，
防止有人把它改回一刀切（那会把「合理拓展」一起禁掉）。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.stage_policy import (
    _FAMILIARITY_GUIDANCE,
    _ROLE_OVERRIDES,
    _SHARED_POLICIES,
)

# 旧的一刀切措辞：必须已经从档位里消失。
_RETIRED_PHRASES = (
    "不虚构共同经历",
    "不凭空补写家庭经历",
    "没发生过的共同回忆",
)


@pytest.mark.parametrize("stage", ["close", "married"])
def test_self_disclosure_guards_the_player_side_only(stage: str) -> None:
    """两层都在：允许角色补自己的日常 + 禁止替玩家补写。"""

    text = _SHARED_POLICIES[stage]["selfDisclosure"]

    # 放行侧：角色自己的日常算合理拓展。
    assert "自己的日常可以自然补全" in text
    # 禁止侧：玩家侧的三类——他说过的话、他做过的事、他自己的近况。
    assert "不替玩家补写" in text or "不替伴侣补写" in text
    assert "说过的话" in text
    assert "做过的事" in text
    assert "近况" in text


@pytest.mark.parametrize("stage", ["close", "married"])
def test_retired_one_size_fits_all_wording_stays_out(stage: str) -> None:
    text = _SHARED_POLICIES[stage]["selfDisclosure"]

    for phrase in _RETIRED_PHRASES[:2]:
        assert phrase not in text


def test_no_shared_policy_carries_a_retired_phrase() -> None:
    """共享档位里任何字段都不该再挂着旧的一刀切口径。"""

    for stage, policy in _SHARED_POLICIES.items():
        for field, value in policy.items():
            text = str(value)
            for phrase in _RETIRED_PHRASES[:2]:
                assert phrase not in text, f"{stage}.{field} 还用着旧口径：{phrase}"


def test_unfamiliar_familiarity_is_a_degree_not_a_fact_ban() -> None:
    """熟稔度那档讲的是「还少」，不是「不许提」。"""

    text = _FAMILIARITY_GUIDANCE["unfamiliar"]

    assert "没发生过的共同回忆" not in text
    assert "共同经历还少" in text


def test_role_overrides_do_not_reintroduce_the_blanket_ban() -> None:
    """角色专属 override 也不能把一刀切口径塞回来。"""

    for role, stages in _ROLE_OVERRIDES.items():
        for stage, fields in stages.items():
            for field, text in fields.items():
                for phrase in _RETIRED_PHRASES:
                    assert phrase not in text, (
                        f"{role}.{stage}.{field} 出现旧口径：{phrase}"
                    )


def test_sophia_married_override_keeps_player_side_guard() -> None:
    """索菲亚婚后档没有覆盖 selfDisclosure，通用档的玩家侧护栏必须仍然生效。

    她正是本次实测的角色：她的 override 只动了 initiative / followUp，
    所以 married 的 selfDisclosure 是她唯一拿到的这条约束——覆盖掉就等于没有。
    """

    assert "selfDisclosure" not in _ROLE_OVERRIDES["Sophia"]["married"]
    assert "不替伴侣补写" in _SHARED_POLICIES["married"]["selfDisclosure"]
