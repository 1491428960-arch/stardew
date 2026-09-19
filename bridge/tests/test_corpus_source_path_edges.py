"""`corpus` 的来源路径规范化与 locale 回退链。

`_normalise_source_path` 的 docstring 写得很清楚：“把来源路径变成**可提交**的相对路径，
**避免泄露本机绝对路径**”——这是安全相关的一条，且此前没有直接测试。
`_locale_candidates` 决定 i18n 目录的回退顺序（`zh-CN` → `zh` → `default`），
顺序错了会取到错误的语言文本。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stardew_ai_bridge.corpus import (
    _locale_candidates,
    _normalise_source_path,
    _ordered_i18n_catalogs,
)


# --- _normalise_source_path -------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("assets/dialogue.json", "assets/dialogue.json"),  # 相对路径原样保留
        ("assets\\dialogue.json", "assets/dialogue.json"),  # 反斜杠统一成 /
        ("/home/someone/mods/mod/dialogue.json", "dialogue.json"),  # POSIX 绝对路径只留文件名
        ("C:\\Users\\someone\\Mods\\Mod\\dialogue.json", "dialogue.json"),  # Windows 同理
        ("./dialogue.json", "dialogue.json"),
        ("", "unknown.json"),
        ("   ", "unknown.json"),
        (".", "unknown.json"),
        ("/", "unknown.json"),
    ],
)
def test_source_path_is_reduced_to_a_committable_relative_path(
    raw: str, expected: str
) -> None:
    assert _normalise_source_path(raw) == expected


def test_absolute_paths_never_leak_the_machine_layout() -> None:
    # 只保留最后一段：目录结构（含用户名、盘符）都不会出现在结果里。
    result = _normalise_source_path(
        "D:\\sbeam\\steamapps\\common\\Stardew Valley\\Mods\\X\\i18n\\zh.json"
    )

    assert result == "zh.json"
    assert "sbeam" not in result
    assert ":" not in result


def test_pathlib_input_is_accepted() -> None:
    assert _normalise_source_path(Path("assets/dialogue.json")) == "assets/dialogue.json"


# --- _locale_candidates -----------------------------------------------------


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("zh-CN", ["zh-CN", "zh", "default"]),
        ("zh_CN", ["zh-CN", "zh", "default"]),  # 下划线归一成连字符
        ("zh", ["zh", "default"]),  # 单段：第二级与第一级重复，被去重
        ("default", ["default"]),
        ("", ["default"]),
        ("   ", ["default"]),
        ("ZH-cn", ["ZH-cn", "ZH", "default"]),  # 大小写保留，但去重比较不敏感
    ],
)
def test_locale_candidates_build_the_fallback_chain(
    locale: str, expected: list[str]
) -> None:
    assert _locale_candidates(locale) == expected


# --- _ordered_i18n_catalogs -------------------------------------------------


def test_catalogs_are_ordered_by_the_locale_fallback_chain() -> None:
    catalogs = {
        "default": {"k": "默认"},
        "zh": {"k": "简体"},
        "zh-CN": {"k": "中国"},
    }

    ordered = _ordered_i18n_catalogs(catalogs, "zh-CN")

    assert [catalog["k"] for catalog in ordered] == ["中国", "简体", "默认"]


def test_catalog_matching_is_case_insensitive() -> None:
    catalogs = {"ZH-cn": {"k": "中国"}, "default": {"k": "默认"}}

    ordered = _ordered_i18n_catalogs(catalogs, "zh-CN")

    assert [catalog["k"] for catalog in ordered] == ["中国", "默认"]


def test_missing_candidates_are_skipped_and_each_catalog_is_used_once() -> None:
    catalogs = {"zh": {"k": "简体"}}

    ordered = _ordered_i18n_catalogs(catalogs, "zh-CN")

    # 既没有 zh-CN 也没有 default，只剩 zh 命中一次
    assert [catalog["k"] for catalog in ordered] == ["简体"]
