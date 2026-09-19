from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from jellyfin_show_organizer import apply_scope_cli
from jellyfin_show_organizer.apply_contract import (
    ApplyContract,
    ApplyMember,
    ApplyMemberRole,
    ApplyOperationGroup,
)
from jellyfin_show_organizer.apply_execution import (
    ApplyExecutionError,
    ApplyExecutionResult,
    PreparedApply,
)
from jellyfin_show_organizer.apply_scope import create_apply_scope, render_apply_scope
from jellyfin_show_organizer.models import SourceFingerprint
from jellyfin_show_organizer.run_provenance import SourceRevision

pytestmark = pytest.mark.local


def _prepared() -> PreparedApply:
    member = ApplyMember(
        role=ApplyMemberRole.VIDEO,
        source_relative_path="source.mkv",
        destination_relative_path="dest.mkv",
        fingerprint=SourceFingerprint(size=1, mtime_ns=1),
    )
    return PreparedApply(
        contract=ApplyContract(
            plan_sha256="a" * 64,
            groups=(
                ApplyOperationGroup(group_id="op-a", members=(member,)),
                ApplyOperationGroup(group_id="op-b", members=(member,)),
            ),
        ),
        review_session_sha256="b" * 64,
        source_revision="c" * 40,
    )


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    plan = tmp_path / "plan.json"
    preflight = tmp_path / "preflight.json"
    provenance = tmp_path / "run-provenance.json"
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    for path in (plan, preflight, provenance):
        path.write_text("{}", encoding="utf-8")
    source.mkdir()
    destination.mkdir()
    return plan, preflight, provenance, source, destination


def test_scope_create_cli_writes_canonical_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan, preflight, provenance, source, destination = _inputs(tmp_path)
    prepared = _prepared()
    monkeypatch.setattr(
        apply_scope_cli, "prepare_apply", lambda *args, **kwargs: prepared
    )
    monkeypatch.setattr(
        apply_scope_cli,
        "detect_source_revision",
        lambda: SourceRevision(state="git", commit="c" * 40, dirty=False),
    )
    output = tmp_path / "scope.json"
    args = argparse.Namespace(
        plan=plan,
        preflight=preflight,
        run_provenance=provenance,
        source_root=source,
        destination_root=destination,
        approve_plan_sha256="a" * 64,
        approve_review_session_sha256="b" * 64,
        approve_source_revision="c" * 40,
        group_ids=["op-a"],
        output=output,
        json_output=True,
    )

    assert apply_scope_cli._run_scope_create(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["groups_total"] == 1
    assert payload["output"] == str(output)
    assert output.read_bytes() == render_apply_scope(
        create_apply_scope(prepared, ("op-a",))
    )


def test_scope_create_cli_rejects_output_inside_media_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan, preflight, provenance, source, destination = _inputs(tmp_path)
    monkeypatch.setattr(
        apply_scope_cli, "prepare_apply", lambda *args, **kwargs: _prepared()
    )
    monkeypatch.setattr(
        apply_scope_cli,
        "detect_source_revision",
        lambda: SourceRevision(state="git", commit="c" * 40, dirty=False),
    )
    args = argparse.Namespace(
        plan=plan,
        preflight=preflight,
        run_provenance=provenance,
        source_root=source,
        destination_root=destination,
        approve_plan_sha256="a" * 64,
        approve_review_session_sha256="b" * 64,
        approve_source_revision="c" * 40,
        group_ids=["op-a"],
        output=source / "scope.json",
        json_output=False,
    )

    assert apply_scope_cli._run_scope_create(args) == 30
    assert "outside the source root" in capsys.readouterr().err


def test_scoped_apply_cli_check_only_binds_scope_and_emits_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan, preflight, provenance, source, destination = _inputs(tmp_path)
    prepared = _prepared()
    scope = create_apply_scope(prepared, ("op-a",))
    scope_path = tmp_path / "scope.json"
    scope_path.write_bytes(render_apply_scope(scope))
    result = ApplyExecutionResult(
        plan_sha256="a" * 64,
        review_session_sha256="b" * 64,
        groups_total=1,
        groups_completed=0,
        members_moved=0,
        members_recovered=0,
        journal_path=None,
        check_only=True,
    )
    monkeypatch.setattr(
        apply_scope_cli, "prepare_apply", lambda *args, **kwargs: prepared
    )
    monkeypatch.setattr(
        apply_scope_cli,
        "detect_source_revision",
        lambda: SourceRevision(state="git", commit="c" * 40, dirty=False),
    )
    monkeypatch.setattr(apply_scope_cli, "approval_token", lambda *_args: "TOKEN")
    monkeypatch.setattr(
        apply_scope_cli, "execute_apply", lambda *args, **kwargs: result
    )
    args = argparse.Namespace(
        plan=plan,
        preflight=preflight,
        run_provenance=provenance,
        source_root=source,
        destination_root=destination,
        journal=None,
        approve_plan_sha256="a" * 64,
        approve_review_session_sha256="b" * 64,
        approve_source_revision="c" * 40,
        scope=scope_path,
        approve_scope_sha256=scope.sha256,
        check_only=True,
        confirm_apply=None,
        resume=False,
        json_output=True,
    )

    assert apply_scope_cli._run_apply(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["apply_scope_sha256"] == scope.sha256
    assert payload["confirmation_token"] == "TOKEN"

    args.check_only = False
    args.confirm_apply = "TOKEN"
    args.journal = tmp_path / "apply.jsonl"
    args.json_output = False
    monkeypatch.setattr(
        apply_scope_cli,
        "execute_apply",
        lambda *args, **kwargs: ApplyExecutionResult(
            plan_sha256="a" * 64,
            review_session_sha256="b" * 64,
            groups_total=1,
            groups_completed=1,
            members_moved=1,
            members_recovered=0,
            journal_path=args[3] if len(args) > 3 else None,
            check_only=False,
        ),
    )
    assert apply_scope_cli._run_apply(args) == 0
    assert "Scoped apply complete" in capsys.readouterr().out


def test_bind_optional_scope_requires_both_arguments(tmp_path: Path) -> None:
    prepared = _prepared()
    with pytest.raises(Exception, match="supplied together"):
        apply_scope_cli.bind_optional_scope(
            argparse.Namespace(scope=tmp_path / "missing", approve_scope_sha256=None),
            prepared,
        )


@pytest.mark.parametrize(
    ("revision", "message"),
    [
        (SourceRevision(state="unavailable", commit=None, dirty=None), "verifiable"),
        (SourceRevision(state="git", commit="c" * 40, dirty=True), "dirty"),
        (SourceRevision(state="git", commit="d" * 40, dirty=False), "does not match"),
    ],
)
def test_current_revision_must_match_clean_git(
    monkeypatch: pytest.MonkeyPatch,
    revision: SourceRevision,
    message: str,
) -> None:
    monkeypatch.setattr(apply_scope_cli, "detect_source_revision", lambda: revision)
    with pytest.raises(ApplyExecutionError, match=message):
        apply_scope_cli._current_revision_matches(_prepared(), operation="test")


def test_unscoped_apply_preserves_existing_apply_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(apply_scope_cli.cli, "_run_apply", lambda _args: 7)
    args = argparse.Namespace(scope=None, approve_scope_sha256=None)
    assert apply_scope_cli._run_apply(args) == 7
