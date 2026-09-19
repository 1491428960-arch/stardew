"""`run_character_quality_eval.py` 的云端成本护栏（B14）。

2026-09-20 补。安全门审计发现：15 个脚本里只有 `run_group_dialogue_cloud_batch.py` 有
`--confirm-cloud`，而**成本最高**的恰恰是 `run_character_quality_eval.py`（历史累计约
**5,514 万 tokens**，约是群聊批次的 100 倍）——它当时**没有任何确认门**，一次手滑就是真金白银。

现在它与群聊批次采用**同一约定**：不传 `--confirm-cloud` 时只打印计划（dry-run）并退出，
绝不静默联网。下面钉住三件事：

1. dry-run **一次模型都不问**；
2. 传了 `--confirm-cloud` 才真跑；
3. **别的 provider 不被误挡**（否则会把本地评测也一起挡住）。
"""

from __future__ import annotations

import json

import pytest

import run_character_quality_eval as script


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """把真正的评测换成记录调用，避免任何联网。"""

    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(script, "run_evaluation", fake_run)
    return calls


def test_cloud_without_confirmation_is_a_dry_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _spy(monkeypatch)

    code = script.main(["--provider", "cloud", "--limit", "2"])

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 0
    assert payload["dryRun"] is True
    assert payload["provider"] == "cloud"
    assert payload["limit"] == 2
    assert "未发起任何云端请求" in payload["note"]
    # 关键：一次模型都没问
    assert calls == []


def test_cloud_with_confirmation_actually_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _spy(monkeypatch)

    code = script.main(["--provider", "cloud", "--confirm-cloud", "--limit", "1"])

    assert code == 0
    assert len(calls) == 1
    assert calls[0]["provider"] == "cloud"


@pytest.mark.parametrize("provider", ["fake", "local"])
def test_other_providers_are_not_gated(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    # 本地与 fake 不花钱，不该被确认门挡住。
    calls = _spy(monkeypatch)

    assert script.main(["--provider", provider, "--limit", "1"]) == 0
    assert len(calls) == 1


def test_the_dry_run_reports_the_budget_it_would_spend(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _spy(monkeypatch)

    script.main(
        [
            "--provider",
            "cloud",
            "--max-requests",
            "7",
            "--max-total-tokens",
            "12345",
        ]
    )

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["maxRequests"] == 7
    assert payload["maxTotalTokens"] == 12345


def test_the_confirm_flag_exists_in_the_parser() -> None:
    # 参数名是外部契约（文档与脚本都在用），改动要能被发现。
    args = script._parse_args(["--provider", "cloud", "--confirm-cloud"])

    assert args.confirm_cloud is True
    assert script._parse_args(["--provider", "cloud"]).confirm_cloud is False
