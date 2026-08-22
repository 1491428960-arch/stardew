from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
PACKAGE_ROOT = PROJECT_ROOT / "src" / "stardew_ai_bridge"


def test_bridge_project_is_ready_for_development() -> None:
    assert PYPROJECT_PATH.is_file()
    pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")

    assert 'requires-python = ">=3.12,<3.13"' in pyproject
    assert '"fastapi>=' in pyproject
    assert '"httpx>=' in pyproject
    assert '"uvicorn[standard]>=' in pyproject
    assert '"pytest>=' in pyproject
    assert '"pytest-asyncio>=' in pyproject
    assert PACKAGE_ROOT.is_dir()
    assert (PACKAGE_ROOT / "__init__.py").is_file()

    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    try:
        import stardew_ai_bridge
    finally:
        sys.path.pop(0)

    assert stardew_ai_bridge.__name__ == "stardew_ai_bridge"
