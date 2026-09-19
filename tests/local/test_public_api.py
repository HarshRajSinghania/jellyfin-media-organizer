from __future__ import annotations

from pathlib import Path

import pytest

from jellyfin_show_organizer.api import inspect_audit


def test_inspect_audit_returns_structured_summary(tmp_path: Path) -> None:
    (tmp_path / "summary.txt").write_text(
        "readiness_state=apply-ready\npreflight_ready=true\nrecords=2\n"
        "matched=2\nextra=0\nduplicate=0\nheld=0\nsuspicious=0\n"
        "unresolved=0\nremaining_total=0\nplan_sha256=abc\n",
        encoding="utf-8",
    )
    result = inspect_audit(tmp_path)
    assert result.readiness_state == "apply-ready"
    assert result.records == 2
    assert result.plan_sha256 == "abc"


def test_inspect_audit_rejects_missing_summary(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="summary.txt"):
        inspect_audit(tmp_path)
