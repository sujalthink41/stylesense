"""Operator commands: `python -m stylesense.cli <command>`."""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict

from stylesense.bootstrap.container import build_container
from stylesense.integrations.sources.mock import MockSource
from stylesense.platform.config import Environment, Settings, get_settings
from stylesense.platform.logging import configure_logging


async def seed_catalog(settings: Settings, *, seed: int) -> dict[str, int]:
    # Compare by value, not identity: a safety guard must hold even for unvalidated settings.
    if settings.env == Environment.PRODUCTION:
        raise SystemExit("refusing to load mock products into production")
    container = build_container(settings)
    try:
        report = await container.catalog.ingest(MockSource(seed=seed))
        embedded = 0
        while batch := await container.catalog.embed_pending(batch_size=200):
            embedded += batch
    finally:
        await container.aclose()
    return {**asdict(report), "embedded": embedded}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stylesense.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser(
        "seed-catalog", help="load the deterministic mock catalog (non-production)"
    )
    seed.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(level="WARNING", json_logs=True)
    result = asyncio.run(seed_catalog(settings, seed=args.seed))
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
