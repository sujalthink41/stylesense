"""Operator commands: `python -m stylesense.cli <command> --help`."""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from stylesense.ai.gateway.admin import ModelPriceIn, TaskConfigIn
from stylesense.ai.gateway.exceptions import AIUnavailableError
from stylesense.ai.gateway.tasks import DIAGNOSTICS_ECHO, EchoInput
from stylesense.ai.gateway.types import ModelRef
from stylesense.bootstrap.container import Container, build_container
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


async def llm_price(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    price = ModelPriceIn(
        kind=args.kind,
        input_usd_per_mtok=Decimal(args.input),
        cached_input_usd_per_mtok=Decimal(args.cached),
        output_usd_per_mtok=Decimal(args.output),
    )
    async with _Session(settings) as c:
        saved = await c.llm_admin.upsert_model(ModelRef.parse(args.model), price, actor=None)
    return saved.model_dump(mode="json")


async def llm_route(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    config = TaskConfigIn(
        targets=args.targets,
        temperature=args.temperature,
        max_input_tokens=args.max_input,
        max_output_tokens=args.max_output,
        timeout_s=args.timeout,
        cache_ttl_s=args.cache_ttl,
        enabled=not args.disable,
    )
    async with _Session(settings) as c:
        saved = await c.llm_admin.upsert_task(args.task, config, actor=None)
    return saved.model_dump(mode="json")


async def llm_check(settings: Settings) -> dict[str, Any]:
    """End-to-end check through the real gateway (needs `diagnostics.echo` routed)."""
    async with _Session(settings) as c:
        try:
            result = await c.gateway.run(DIAGNOSTICS_ECHO, EchoInput(text="stylesense"))
        except AIUnavailableError as exc:
            return {"ok": False, "providers": list(c.llm_providers), "error": str(exc)}
        return {"ok": result.ok and result.echo == "stylesense", "providers": list(c.llm_providers)}


class _Session:
    """Builds the container for one command and always closes it."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._container: Container | None = None

    async def __aenter__(self) -> Container:
        self._container = build_container(self._settings)
        return self._container

    async def __aexit__(self, *_: object) -> None:
        if self._container:
            await self._container.aclose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stylesense.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    seed = commands.add_parser(
        "seed-catalog", help="load the deterministic mock catalog (non-production)"
    )
    seed.add_argument("--seed", type=int, default=2026)

    price = commands.add_parser("llm-price", help="set a model's price (USD per million tokens)")
    price.add_argument("model", help="provider:model")
    price.add_argument("--input", required=True)
    price.add_argument("--cached", required=True, help="cached input price")
    price.add_argument("--output", required=True)
    price.add_argument("--kind", choices=["chat", "embedding"], default="chat")

    route = commands.add_parser("llm-route", help="route a task to models (first = primary)")
    route.add_argument("task")
    route.add_argument("targets", nargs="+", help="provider:model, in fallback order")
    route.add_argument("--max-input", type=int, default=4_000)
    route.add_argument("--max-output", type=int, default=600)
    route.add_argument("--timeout", type=float, default=20)
    route.add_argument("--cache-ttl", type=int, default=0)
    route.add_argument("--temperature", type=float, default=None)
    route.add_argument("--disable", action="store_true")

    commands.add_parser("llm-check", help="call the configured model end to end")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    # Logs to stderr: stdout carries only the JSON result, so it stays machine-readable.
    configure_logging(level="WARNING", json_logs=True, stream=sys.stderr)
    match args.command:
        case "seed-catalog":
            result: dict[str, Any] = asyncio.run(seed_catalog(settings, seed=args.seed))
        case "llm-price":
            result = asyncio.run(llm_price(settings, args))
        case "llm-route":
            result = asyncio.run(llm_route(settings, args))
        case _:
            result = asyncio.run(llm_check(settings))
    sys.stdout.write(json.dumps(result, indent=2, default=str) + "\n")
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
