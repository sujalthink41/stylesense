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
from stylesense.genui.schema import contract_json
from stylesense.integrations.sources.mock import MockSource
from stylesense.modules.stylist.evals.scoring import Report, load_golden, score, score_async
from stylesense.modules.stylist.slots import Slots
from stylesense.modules.stylist.tasks import STYLIST_UNDERSTAND, UnderstandInput
from stylesense.modules.stylist.understanding import parse_request
from stylesense.platform.config import Environment, Settings, get_settings
from stylesense.platform.logging import configure_logging

EVAL_BAR = 0.90  # minimum field accuracy for request understanding (CP8 exit criterion)


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


async def dev_token(settings: Settings, *, email: str) -> dict[str, Any]:
    """Local-only: a real user + real tokens without Google, for trying the API."""
    if settings.env == Environment.PRODUCTION:
        raise SystemExit("refusing to mint developer tokens in production")
    async with _Session(settings) as c:
        result = await c.auth.sign_in_dev(email)
    return {"user_id": str(result.user.id), **result.tokens.model_dump(mode="json")}


async def eval_understand(settings: Settings, *, engine: str) -> dict[str, Any]:
    """Score request understanding on the golden set: `rules` offline, or `llm` via the gateway."""
    examples = load_golden()
    if engine == "rules":
        report = score(examples, parse_request)
    else:
        async with _Session(settings) as c:

            async def via_llm(text: str) -> Slots:
                result = await c.gateway.run(
                    STYLIST_UNDERSTAND, UnderstandInput(text=text, known={})
                )
                return result.to_slots()

            try:
                report = await score_async(examples, via_llm)
            except AIUnavailableError as exc:
                return {"ok": False, "engine": engine, "error": str(exc)}
    return _report(engine, report)


def _report(engine: str, report: Report) -> dict[str, Any]:
    return {
        "ok": report.field_accuracy >= EVAL_BAR,
        "engine": engine,
        "examples": report.examples,
        "field_accuracy": round(report.field_accuracy, 4),
        "exact_match": round(report.exact_match, 4),
        "failures": report.failures,
    }


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


async def purge_media(settings: Settings) -> dict[str, Any]:
    """Run the expired-photo purge now (the worker also runs it every 15 minutes)."""
    async with _Session(settings) as c:
        uploads = await c.uploads.purge_expired()
        results = await c.tryon.purge_expired()
    return {"ok": True, "uploads_deleted": uploads, "tryon_results_deleted": results}


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
    commands.add_parser("export-genui-contract", help="print the GenUI JSON Schema contract")

    evals = commands.add_parser(
        "eval-understand", help="score request understanding on the golden set"
    )
    evals.add_argument("--engine", choices=["rules", "llm"], default="rules")

    commands.add_parser("purge-media", help="delete expired photos and try-on results now")

    dev = commands.add_parser("dev-token", help="local-only: tokens for a test user (no Google)")
    dev.add_argument("email")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "export-genui-contract":
        sys.stdout.write(contract_json())  # no settings or DB needed
        return 0
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
        case "eval-understand":
            result = asyncio.run(eval_understand(settings, engine=args.engine))
        case "dev-token":
            result = asyncio.run(dev_token(settings, email=args.email))
        case "purge-media":
            result = asyncio.run(purge_media(settings))
        case _:
            result = asyncio.run(llm_check(settings))
    sys.stdout.write(json.dumps(result, indent=2, default=str) + "\n")
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
