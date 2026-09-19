"""`ProfileIndexStore` 的字段白名单：构建元数据不外泄。

索引文件里带着 **67 条构建警告**（`warnings`）以及 `sourcePath` 这类构建元数据
（见 `scripts/audit_profile_index.py` 与 `docs/active-work.md` 第 81、83 项）。
`ProfileIndexStore` 的 docstring 明确写着“只读检索派生索引，并把来源路径等**构建元数据隔离在
Bridge 外**”，做法就是每个访问器配一份字段白名单。

这里把这条**架构契约**钉住：将来若有人“顺手”把 `warnings` 加进白名单、或新增一个
暴露构建元数据的访问器，这些测试会先失败。
"""

from __future__ import annotations

from stardew_ai_bridge.profile_index import ProfileIndexStore


def _field_whitelists() -> dict[str, tuple[str, ...]]:
    return {
        name: getattr(ProfileIndexStore, name)
        for name in dir(ProfileIndexStore)
        if name.startswith("_") and name.endswith("_FIELDS")
    }


def test_the_store_declares_field_whitelists() -> None:
    # 若这份清单被清空，下面的断言会变成空转，所以先把“确实存在”钉住。
    whitelists = _field_whitelists()

    assert whitelists, "ProfileIndexStore 应当为每个访问器声明字段白名单"
    assert "_STYLE_FIELDS" in whitelists
    assert "_REFERENCE_FIELDS" in whitelists


def test_no_whitelist_exposes_build_warnings() -> None:
    for name, fields in _field_whitelists().items():
        assert "warnings" not in fields, f"{name} 不该把构建警告带进 Bridge"


def test_the_store_has_no_public_warnings_accessor() -> None:
    public = [name for name in dir(ProfileIndexStore) if not name.startswith("_")]

    assert "warnings" not in public
    assert not any("warning" in name for name in public), public


def test_source_path_is_only_kept_where_it_has_been_sanitised() -> None:
    # `sourcePath` 是唯一带路径的白名单字段：它进索引前已经被
    # `corpus._normalise_source_path` 剥成不含盘符与用户名的相对路径
    # （见 test_corpus_source_path_edges.py），因此保留是安全的——
    # 但不应扩散到别的白名单里。
    whitelists = _field_whitelists()
    holders = [name for name, fields in whitelists.items() if "sourcePath" in fields]

    assert holders == ["_REFERENCE_FIELDS"]


def test_whitelist_entries_are_non_empty_strings() -> None:
    for name, fields in _field_whitelists().items():
        assert isinstance(fields, tuple), name
        assert fields, name
        for field in fields:
            assert isinstance(field, str) and field, f"{name} 里有非法字段名：{field!r}"
