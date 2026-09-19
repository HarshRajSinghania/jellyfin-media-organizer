"""Merge answered items from a scoped review into a validated base session."""

from __future__ import annotations

import argparse
from pathlib import Path

from jellyfin_show_organizer.review_session import (
    ReviewItemState,
    ReviewSession,
    atomic_write_new,
    load_review_session,
    render_review_session,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("scoped", type=Path)
    parser.add_argument("plan_sha256")
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-contains", default=None)
    args = parser.parse_args()

    base = load_review_session(args.base.read_bytes())
    scoped = load_review_session(args.scoped.read_bytes())
    merged = {item.review_ref: item for item in base.items}
    for item in scoped.items:
        if args.source_contains is not None and (
            item.source is None or args.source_contains.casefold() not in item.source.casefold()
        ):
            continue
        previous = merged.get(item.review_ref)
        if previous is not None and previous != item:
            if item.state is not ReviewItemState.ANSWERED:
                continue
            raise SystemExit(f"conflicting answered review ref: {item.review_ref}")
        merged[item.review_ref] = item

    session = ReviewSession(
        schema_version=base.schema_version,
        plan_sha256=args.plan_sha256,
        # The scoped session was created from the current base override. Use
        # that exact payload and carry forward only the already-answered items
        # from the older ledger.
        base_override_snapshot=scoped.base_override_snapshot,
        base_override_toml=scoped.base_override_toml,
        items=tuple(sorted(merged.values(), key=lambda item: item.review_ref)),
    )
    atomic_write_new(args.output, render_review_session(session))
    print(
        f"merged session_sha256={session.sha256} items={len(session.items)} "
        f"complete={session.complete}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
