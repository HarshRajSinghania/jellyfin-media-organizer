"""Supported integration API for applications embedding JMO.

This module intentionally exposes only immutable planning and audit inspection.
Filesystem mutation remains available only through the explicit CLI apply
contract, not through the convenience API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .planner import PlanningConfig, PlanningOutcome
from .review_execution import execute_plan
from .tvmaze_cache import Clock, JsonGetter


@dataclass(frozen=True, slots=True)
class AuditSummary:
    """Path-independent counts and readiness extracted from summary.txt."""

    run_dir: Path
    readiness_state: str
    preflight_ready: str
    records: int
    matched: int
    extra: int
    duplicate: int
    held: int
    suspicious: int
    unresolved: int
    remaining_total: int
    plan_sha256: str | None


def plan_library(
    config: PlanningConfig,
    getter: JsonGetter,
    *,
    clock: Clock | None = None,
    review_session_path: Path | None = None,
    progress=None,
) -> PlanningOutcome:
    """Build one immutable, non-mutating plan for an embedding application."""

    return execute_plan(
        config,
        getter,
        clock=clock,
        review_session_path=review_session_path,
        progress=progress,
    )


def inspect_audit(run_dir: Path) -> AuditSummary:
    """Read one completed audit bundle without touching its media root."""

    root = run_dir.expanduser().resolve(strict=True)
    summary = root / "summary.txt"
    if not summary.is_file():
        raise FileNotFoundError(f"audit bundle does not contain summary.txt: {root}")
    values: dict[str, str] = {}
    for line in summary.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    def number(name: str) -> int:
        try:
            return int(values.get(name, "0"))
        except ValueError as exc:
            raise ValueError(f"audit summary has invalid {name}") from exc

    return AuditSummary(
        run_dir=root,
        readiness_state=values.get("readiness_state", "not-evaluated"),
        preflight_ready=values.get("preflight_ready", "unknown"),
        records=number("records"),
        matched=number("matched"),
        extra=number("extra"),
        duplicate=number("duplicate"),
        held=number("held"),
        suspicious=number("suspicious"),
        unresolved=number("unresolved"),
        remaining_total=number("remaining_total"),
        plan_sha256=values.get("plan_sha256"),
    )
