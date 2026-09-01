from __future__ import annotations

import os
from pathlib import Path

from stardew_ai_bridge.config import load_local_env


def test_load_local_env_reads_cloud_settings_without_overriding_process_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            (
                "BRIDGE_CLOUD_URL=https://api.openai.com/v1/chat/completions",
                "BRIDGE_CLOUD_MODEL= gpt-5.6-terra ",
                "BRIDGE_CLOUD_API_KEY=local-test-key",
                "BRIDGE_CLOUD_ENABLED=false",
                "UNRELATED_SECRET=must-not-load",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("BRIDGE_CLOUD_URL", raising=False)
    monkeypatch.delenv("BRIDGE_CLOUD_MODEL", raising=False)
    monkeypatch.delenv("BRIDGE_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("BRIDGE_CLOUD_ENABLED", raising=False)

    load_local_env(env_path)

    assert (
        os.getenv("BRIDGE_CLOUD_URL")
        == "https://api.openai.com/v1/chat/completions"
    )
    assert os.getenv("BRIDGE_CLOUD_MODEL") == "gpt-5.6-terra"
    assert os.getenv("BRIDGE_CLOUD_API_KEY") == "local-test-key"
    assert os.getenv("BRIDGE_CLOUD_ENABLED") == "false"
    assert os.getenv("UNRELATED_SECRET") is None

    monkeypatch.setenv("BRIDGE_CLOUD_MODEL", "explicit-model")
    load_local_env(env_path)
    assert os.getenv("BRIDGE_CLOUD_MODEL") == "explicit-model"
