"""Exercise an installed artifact, offline, using only temporary synthetic files.

Run with the installed environment's Python from outside the source checkout.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from jellyfin_show_organizer.cli import main
from jellyfin_show_organizer.providers import TvmazeProviderAdapter
from jellyfin_show_organizer.review_contract import load_review_contract
from jellyfin_show_organizer.review_execution import PlanningConfig, execute_plan
from jellyfin_show_organizer.review_system import run_review_system
from jellyfin_show_organizer.run_provenance import detect_source_revision
from jellyfin_show_organizer.schema import plan_to_manifest
from jellyfin_show_organizer.tvmaze_cache import TvmazeCatalogCache


def getter(url: str, params: Mapping[str, str] | None = None) -> object:
    if "search/shows" in url:
        return [
            {
                "show": {
                    "id": 4242,
                    "name": "Example Aired Series",
                    "premiered": "2024-01-01",
                }
            }
        ]
    if "/episodes" in url:
        return [
            {
                "id": 1001,
                "season": 1,
                "number": 1,
                "name": "Pilot",
                "airdate": "2024-01-01",
                "type": "regular",
            }
        ]
    raise AssertionError(f"Unexpected provider request: {url}")


def cli(args: list[str]) -> str:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        result = main(args)
    assert result == 0, (args[0], result, output.getvalue())
    return output.getvalue()


def smoke(root: Path) -> None:
    revision = detect_source_revision()
    assert revision.state == "git" and revision.dirty is False, revision
    source, destination = root / "source", root / "destination"
    source.mkdir()
    destination.mkdir()
    series = source / "Example Aired Series"
    series.mkdir()
    (series / "Example Aired Series S01E01.mkv").write_bytes(b"synthetic-video")
    (series / "Example Aired Series S01E01.en.srt").write_bytes(b"synthetic-subtitle")
    base = root / "base.toml"
    base.write_text("schema_version = 4\n", encoding="utf-8")
    cache = root / "cache"
    config = PlanningConfig(
        shows_root=source,
        destination_root=destination,
        output_dir=root / "seed",
        cache_dir=cache,
        overrides_path=base,
    )
    seed = execute_plan(config, getter)
    assert seed.preflight.ready
    # Recreate the common import case: correctly named files in another root.
    records = [(r.source.relative_path, r.destination) for r in seed.plan.records]
    records += [(r.relative_path, r.destination) for r in seed.plan.companions]
    for old, new in records:
        assert new is not None
        target = source / new
        target.parent.mkdir(parents=True, exist_ok=True)
        (source / old).rename(target)
    first = execute_plan(
        replace(config, output_dir=root / "base-plan", offline=True), getter
    )
    assert first.preflight.ready
    assert all(r.source.relative_path == r.destination for r in first.plan.records)
    base_catalog = load_review_contract(base)
    session_path = root / "session.json"
    reviewed = root / "reviewed.toml"
    provider = TvmazeProviderAdapter(TvmazeCatalogCache(cache, offline=True), getter)
    session, _ = run_review_system(
        plan_to_manifest(first.plan),
        base.read_bytes(),
        base_override_snapshot=base_catalog.snapshot_id,
        provider=provider,
        session_path=session_path,
        output_override_path=reviewed,
        resume=False,
        input_fn=lambda _: "",
        output=io.StringIO(),
    )
    final = root / "reviewed-plan"
    cli(
        [
            "plan",
            str(source),
            "--destination-root",
            str(destination),
            "--output-dir",
            str(final),
            "--cache-dir",
            str(cache),
            "--overrides",
            str(reviewed),
            "--review-session",
            str(session_path),
            "--offline",
            "--json",
        ]
    )
    manifest = json.loads((final / "plan.json").read_text(encoding="utf-8"))
    plan_hash = (final / "plan.sha256").read_text().strip()
    args = [
        "apply",
        str(final / "plan.json"),
        "--preflight",
        str(final / "preflight.json"),
        "--run-provenance",
        str(final / "run-provenance.json"),
        "--source-root",
        str(source),
        "--destination-root",
        str(destination),
        "--approve-plan-sha256",
        plan_hash,
        "--approve-review-session-sha256",
        session.sha256,
        "--approve-source-revision",
        str(revision.commit),
        "--json",
    ]
    check = json.loads(cli([*args, "--check-only"]))
    assert check["groups_total"] == 1 and check["members_moved"] == 0
    assert list(destination.iterdir()) == []
    mutation = [
        *args,
        "--journal",
        str(root / "journal.jsonl"),
        "--confirm-apply",
        check["confirmation_token"],
    ]
    result = json.loads(cli(mutation))
    assert result["members_moved"] == 2 and result["groups_completed"] == 1
    resumed = json.loads(cli([*mutation, "--resume"]))
    assert resumed["members_moved"] == 0
    for record in manifest["records"]:
        assert not (source / record["source"]["relative_path"]).exists()
        assert (destination / record["destination"]).read_bytes() == b"synthetic-video"
    for companion in manifest["companions"]:
        assert not (source / companion["relative_path"]).exists()
        assert (
            destination / companion["destination"]
        ).read_bytes() == b"synthetic-subtitle"


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="jmo-smoke-") as temporary:
        smoke(Path(temporary))
    print("Installed plan/review/check-only/apply/resume workflow passed")
