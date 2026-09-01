from __future__ import annotations

from importlib import import_module
from pathlib import Path


def test_stable_artifact_path_uses_project_relative_path() -> None:
    root = Path("E:/workspace/projects/stardew-ai-npc.worktrees/story-memory")
    path = root / "data" / "generated" / "profile-index.json"
    try:
        module = import_module("stardew_ai_bridge.artifact_paths")
    except ModuleNotFoundError:
        module = None

    assert module is not None
    assert module.stable_artifact_path(path, root=root) == "data/generated/profile-index.json"


def test_stable_artifact_path_redacts_external_absolute_path() -> None:
    root = Path("E:/workspace/projects/stardew-ai-npc.worktrees/story-memory")
    path = Path("C:/Users/Lenovo/private/selected-index.json")
    try:
        module = import_module("stardew_ai_bridge.artifact_paths")
    except ModuleNotFoundError:
        module = None

    assert module is not None
    assert module.stable_artifact_path(path, root=root) == "external/selected-index.json"
