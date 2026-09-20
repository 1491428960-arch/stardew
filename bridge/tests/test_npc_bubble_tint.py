"""「设计色 → tint」反推的唯一来源护栏（承 2026-09-20 语义审计的收敛）。

本项目反复得的病是**同一个概念被实现两遍**，tint 反推复发过一次：

* ``npc_bubble_tint.bubble_to_tint`` —— 彩色 ``Maps\\MenuTiles``，基色 #fdbc6e；
* ``npc_bubble_panel_plain.to_panel_tint`` —— 去色版 ``Maps\\MenuTilesUncolored``，基色近白 248。

两者是同一条公式的两份拷贝，只差一个基色；``scripts/build_bubble_texture.py`` 里还躺着
第三份基色副本 ``(253, 188, 110)``。现在公式只有 ``npc_bubble_tint.to_tint(design, base)``
一处：两个入口都是「把基色填好」的薄封装，基色副本改为 import 同一个常量。

本文件钉四件事：

1. **两个调用点确实走同一份实现** —— 结构性（函数体只有一次 ``return to_tint(...)``）
   加数值性（与 ``to_tint`` 逐值相等）；
2. **没有第三份** —— bridge 包里公式体只出现一次，构建脚本不得自带基色副本；
3. **产物与模板同口径** —— 重跑 ``build_bubble_texture.py`` 不会把基准色的出处改回去；
4. 两个贴图模块不再产生 ``SyntaxWarning``（docstring 里的 ``Maps\\MenuTiles`` 要写双反斜杠，
   单反斜杠是无害的转义猜测，但 Python 已经在告警、未来版本会升级成 SyntaxError）。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
import warnings
from pathlib import Path

from stardew_ai_bridge import npc_bubble_panel_plain, npc_bubble_tint
from stardew_ai_bridge.npc_bubble_elements import NPC_BUBBLE_ELEMENTS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _REPO_ROOT / "bridge" / "src" / "stardew_ai_bridge"
_TINT_MODULE = _PACKAGE / "npc_bubble_tint.py"
_PANEL_MODULE = _PACKAGE / "npc_bubble_panel_plain.py"
_TEXTURE_PRODUCT = _PACKAGE / "npc_bubble_texture.py"
_BUILD_SCRIPT = _REPO_ROOT / "scripts" / "build_bubble_texture.py"

#: 公式体在源码里的模样。收敛后整个 bridge 包**只允许出现一次**（在 ``to_tint`` 里）。
_FORMULA = "min(255, round(channel * 255 /"

#: 基准色的出处：三处（tint 模块、产物、生成脚本模板）必须是同一句话。
_PROVENANCE = "基准色取自 `stardew_ai_bridge.npc_bubble_tint::BUBBLE_TEX_BASE`"

#: 上一轮搬家前的旧出处。它指向的常量已经不在那个文件里了。
_STALE_PROVENANCE = "scripts/export_npc_bubble_assets.py::BUBBLE_TEX_BASE"


# --- 1. 两个调用点走同一份实现 ------------------------------------------------


def _delegated_function_name(module_path: Path, function_name: str) -> str:
    """函数体必须是且只是一条 ``return <name>(...)``；返回被委托的函数名。"""

    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            # docstring 不算实现，其余语句只允许有一条。
            body = [
                statement
                for statement in node.body
                if not (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                )
            ]
            assert len(body) == 1, (
                f"{module_path.name}::{function_name} 的函数体不再是单行委托 —— "
                f"公式很可能又被抄了一份，收敛就白做了"
            )
            statement = body[0]
            assert isinstance(statement, ast.Return) and statement.value is not None
            assert isinstance(statement.value, ast.Call)
            assert isinstance(statement.value.func, ast.Name)
            return statement.value.func.id
    raise AssertionError(f"{module_path.name} 里找不到 {function_name}")


def test_both_entry_points_are_one_line_delegates_to_to_tint() -> None:
    assert _delegated_function_name(_TINT_MODULE, "bubble_to_tint") == "to_tint"
    assert _delegated_function_name(_PANEL_MODULE, "to_panel_tint") == "to_tint"


def _design_colors() -> list[tuple[int, int, int]]:
    """全部角色的设计色 + 两个面板设计色 + 通道边界值。"""

    colors = [
        npc_bubble_tint.parse_color(item["palette"]["bubble"])
        for item in NPC_BUBBLE_ELEMENTS.values()
    ]
    colors += [
        npc_bubble_panel_plain.PLAYER_BUBBLE_DESIGN,
        npc_bubble_panel_plain.NPC_FALLBACK_BUBBLE_DESIGN,
    ]
    colors += [
        (0, 0, 0),
        (1, 1, 1),
        (255, 255, 255),
        (254, 254, 254),
        npc_bubble_tint.BUBBLE_TEX_BASE,
        npc_bubble_panel_plain.PLAIN_PANEL_BASE,
    ]
    return colors


def test_the_two_entry_points_agree_with_to_tint_on_every_design_color() -> None:
    """两个入口与唯一实现在**全部**设计色上逐值相等（薄封装不许有自己的脾气）。"""

    colors = _design_colors()
    assert len(colors) >= 46  # 46 个角色 + 面板与边界值

    for design in colors:
        assert npc_bubble_tint.bubble_to_tint(design) == npc_bubble_tint.to_tint(
            design, npc_bubble_tint.BUBBLE_TEX_BASE
        ), design
        assert npc_bubble_panel_plain.to_panel_tint(design) == npc_bubble_tint.to_tint(
            design, npc_bubble_panel_plain.PLAIN_PANEL_BASE
        ), design


# --- 2. 没有第三份 ------------------------------------------------------------


def test_the_formula_lives_in_exactly_one_place_in_the_package() -> None:
    hits = {
        path.name: path.read_text(encoding="utf-8").count(_FORMULA)
        for path in sorted(_PACKAGE.glob("*.py"))
        if _FORMULA in path.read_text(encoding="utf-8")
    }

    assert hits == {"npc_bubble_tint.py": 1}, (
        f"反推公式在 bridge 包里出现了 {hits} —— 收敛的目标是「只有 npc_bubble_tint.to_tint 一份」，"
        f"其它地方请改为 import 它并传入基色"
    )


def _load_build_script():
    """以桩 PIL 加载构建脚本（脚本顶层 import PIL 只为生成与自检，这里只需要常量）。"""

    if "PIL" not in sys.modules:
        pil = types.ModuleType("PIL")
        image = types.ModuleType("PIL.Image")
        pil.Image = image  # type: ignore[attr-defined]
        sys.modules["PIL"] = pil
        sys.modules["PIL.Image"] = image

    spec = importlib.util.spec_from_file_location("build_bubble_texture", _BUILD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_script_imports_the_bridge_base_instead_of_a_copy() -> None:
    module = _load_build_script()

    # `is` 而不是 `==`：要的就是「同一处常量」，不是「碰巧同值的第二份副本」。
    assert module.BUBBLE_TEX_BASE is npc_bubble_tint.BUBBLE_TEX_BASE


def test_build_script_never_rebinds_the_base_locally() -> None:
    tree = ast.parse(_BUILD_SCRIPT.read_text(encoding="utf-8"))
    assigned = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    assert "BUBBLE_TEX_BASE" not in assigned, (
        "构建脚本里又出现了 BUBBLE_TEX_BASE 的本地赋值 —— 那就是第二份基准色，"
        "请改为 `from stardew_ai_bridge.npc_bubble_tint import BUBBLE_TEX_BASE`"
    )


# --- 3. 产物与模板同口径 ------------------------------------------------------


def test_texture_template_and_product_share_the_same_base_provenance() -> None:
    script = _BUILD_SCRIPT.read_text(encoding="utf-8")
    product = _TEXTURE_PRODUCT.read_text(encoding="utf-8")

    assert _PROVENANCE in script, "生成脚本的模板没同步：重跑会把产物里基准色的出处改回旧写法"
    assert _PROVENANCE in product
    assert _STALE_PROVENANCE not in script
    assert _STALE_PROVENANCE not in product


# --- 4. 面板 tint 常量由那条实现现算 ------------------------------------------


def test_panel_tints_are_computed_from_their_design_colors() -> None:
    """两个面板 tint 的 6 个数字此前是手抄的；现在由 ``to_panel_tint`` 现算并保持不变。"""

    assert npc_bubble_panel_plain.PLAYER_BUBBLE_TINT == (232, 246, 253)
    assert npc_bubble_panel_plain.NPC_FALLBACK_BUBBLE_TINT == (246, 238, 251)

    for design, tint in (
        (
            npc_bubble_panel_plain.PLAYER_BUBBLE_DESIGN,
            npc_bubble_panel_plain.PLAYER_BUBBLE_TINT,
        ),
        (
            npc_bubble_panel_plain.NPC_FALLBACK_BUBBLE_DESIGN,
            npc_bubble_panel_plain.NPC_FALLBACK_BUBBLE_TINT,
        ),
    ):
        assert npc_bubble_panel_plain.to_panel_tint(design) == tint
        # 回乘即还原设计色（游戏侧按整数截断，允许差 1 个色阶）
        back = tuple(
            round(channel * base / 255)
            for channel, base in zip(tint, npc_bubble_panel_plain.PLAIN_PANEL_BASE)
        )
        assert all(abs(a - b) <= 1 for a, b in zip(back, design)), (design, tint, back)


# --- 5. 不再有非法转义告警 ----------------------------------------------------


def test_bubble_modules_compile_without_invalid_escape_warnings() -> None:
    for path in (_TINT_MODULE, _PANEL_MODULE, _TEXTURE_PRODUCT, _BUILD_SCRIPT):
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
