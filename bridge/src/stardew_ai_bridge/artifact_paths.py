from __future__ import annotations

from pathlib import Path


def stable_artifact_path(path: str | Path, *, root: str | Path) -> str:
    """返回不依赖当前工作树目录名的工件路径。"""

    root_path = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    try:
        relative = candidate.resolve().relative_to(root_path)
    except (OSError, ValueError):
        name = candidate.name or "profile-index.json"
        return f"external/{name}"
    return relative.as_posix()
