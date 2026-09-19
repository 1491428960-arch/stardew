"""角色资料的边界处理：来源标记解析与叠加层容错。

这两处此前没有覆盖，而它们各自挡着一个真实的坑：
`_mod_markers` 若不在字符串分支把 `sourceMods` 包成列表，后面的 `Iterable`
遍历会把它**逐字符**拆成来源；`_ensure_profile_layers` 若不校验叠加层类型，
一个写错的 `modOverlay` 会让后续合并拿到字符串。
"""

from __future__ import annotations

from pathlib import Path

from stardew_ai_bridge.personas import _ensure_profile_layers, _mod_markers


def test_mod_markers_treats_a_string_source_mods_as_one_marker() -> None:
    markers = _mod_markers(
        {"mod": "vanilla", "sourceMods": "FlashShifter.SVE"},
        Path("vanilla.json"),
    )

    # 关键：不能变成 ["v", "a", "n", ...] 这种逐字符结果。
    assert markers == ["vanilla", "FlashShifter.SVE"]


def test_mod_markers_falls_back_to_the_file_stem() -> None:
    # path.stem 已去掉扩展名；sourceMods 全是空白时同样回落到文件名。
    assert _mod_markers({}, Path("sve.json")) == ["sve"]
    assert _mod_markers({"sourceMods": ["  ", ""]}, Path("fallback.json")) == [
        "fallback"
    ]


def test_mod_markers_keeps_order_and_drops_duplicates() -> None:
    markers = _mod_markers(
        {"mod": "vanilla", "sourceMods": ["vanilla", "SVE", "sve"]},
        Path("vanilla.json"),
    )

    assert markers == ["vanilla", "SVE", "sve"]


def test_ensure_profile_layers_ignores_a_non_mapping_mod_overlay() -> None:
    # modOverlay 写错类型时按“没有叠加层”处理，而不是把字符串当映射用。
    layered = _ensure_profile_layers({"npcId": "Shane", "modOverlay": "not-a-mapping"})

    assert isinstance(layered, dict)
    assert layered.get("npcId") == "Shane"
