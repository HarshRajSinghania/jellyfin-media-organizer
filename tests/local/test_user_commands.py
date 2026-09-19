from __future__ import annotations

import json
import tomllib
from pathlib import Path

from jellyfin_show_organizer.user_commands import (
    run_demo,
    run_doctor,
    run_init,
    run_inspect,
    write_example,
)


def test_doctor_reports_ready_and_json(tmp_path: Path, capsys) -> None:
    source = tmp_path / "Shows"
    destination = tmp_path / "Organized"
    source.mkdir()
    destination.mkdir()
    (source / "Episode.mkv").write_bytes(b"x")

    assert run_doctor(
        source,
        destination,
        tmp_path / "state",
        tmp_path / "cache",
        json_output=True,
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ready"] is True
    assert payload["checks"]


def test_doctor_rejects_state_inside_media(tmp_path: Path, capsys) -> None:
    source = tmp_path / "Shows"
    destination = tmp_path / "Organized"
    source.mkdir()
    destination.mkdir()
    assert run_doctor(source, destination, source / "state", tmp_path / "cache") == 2
    assert "FIX REQUIRED" in capsys.readouterr().out


def test_doctor_reports_missing_source(tmp_path: Path, capsys) -> None:
    destination = tmp_path / "Organized"
    destination.mkdir()
    assert run_doctor(
        tmp_path / "MissingShows",
        destination,
        tmp_path / "state",
        tmp_path / "cache",
    ) == 2
    assert "source_exists" in capsys.readouterr().out


def test_init_creates_reusable_state_without_overwriting(tmp_path: Path, capsys) -> None:
    source = tmp_path / "Shows"
    destination = tmp_path / "Organized"
    source.mkdir()
    destination.mkdir()
    state = tmp_path / "state"
    assert run_init(source, destination, state) == 0
    assert (state / "planning.toml").is_file()
    assert (state / "base-overrides.toml").read_text(encoding="utf-8") == "schema_version = 4\n"
    config = tomllib.loads((state / "planning.toml").read_text(encoding="utf-8"))
    assert config["schema_version"] == 1
    assert config["plan"]["overrides"] == "base-overrides.toml"
    assert run_init(source, destination, state) == 2
    assert "refusing" in capsys.readouterr().out.lower()


def test_init_rejects_invalid_roots_and_mode(tmp_path: Path, capsys) -> None:
    source = tmp_path / "Shows"
    source.mkdir()
    assert run_init(source, tmp_path / "missing", tmp_path / "state") == 2
    assert "destination" in capsys.readouterr().out.lower()
    destination = tmp_path / "Organized"
    destination.mkdir()
    assert run_init(source, destination, tmp_path / "state", provider_mode="bad") == 2
    assert "provider mode" in capsys.readouterr().out.lower()


def test_demo_creates_only_synthetic_workspace(tmp_path: Path, capsys) -> None:
    output = tmp_path / "demo"
    assert run_demo(output) == 0
    assert (output / "Shows" / "Example Show" / "Season 01" / "Example Show - S01E01.mkv").is_file()
    assert (output / "README.txt").is_file()
    assert (output / "State" / "runs" / "demo-run" / "plan.json").is_file()
    assert "apply-ready" in (output / "State" / "runs" / "demo-run" / "summary.txt").read_text(encoding="utf-8")
    assert run_demo(output) == 2
    assert "refusing" in capsys.readouterr().out.lower()


def test_inspect_summarizes_run(tmp_path: Path, capsys) -> None:
    (tmp_path / "summary.txt").write_text(
        "records=3\nmatched=2\nextra=1\nduplicate=0\nheld=0\n"
        "suspicious=0\nunresolved=0\nremaining_total=0\n"
        "readiness_state=apply-ready\npreflight_ready=true\n",
        encoding="utf-8",
    )
    assert run_inspect(tmp_path) == 0
    output = capsys.readouterr().out
    assert "apply-ready" in output
    assert "check-only" in output

    assert run_inspect(tmp_path, json_output=True) == 0
    assert json.loads(capsys.readouterr().out)["records"] == 3


def test_inspect_requires_summary(tmp_path: Path, capsys) -> None:
    assert run_inspect(tmp_path) == 2
    assert "summary.txt" in capsys.readouterr().out


def test_write_example_refuses_overwrite(tmp_path: Path, capsys) -> None:
    target = tmp_path / "example.toml"
    assert write_example(target, "x\n") == 0
    assert write_example(target, "y\n") == 2
    assert target.read_text(encoding="utf-8") == "x\n"
    assert "Refusing" in capsys.readouterr().out


def test_write_example_can_print_and_reject_missing_parent(capsys, tmp_path: Path) -> None:
    assert write_example(None, "schema_version = 1\n") == 0
    assert "schema_version" in capsys.readouterr().out
    assert write_example(tmp_path / "missing" / "example.toml", "x\n") == 2
    assert "does not exist" in capsys.readouterr().out
