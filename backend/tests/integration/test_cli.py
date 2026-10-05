import asyncio
import json

import pytest
from sqlalchemy import text

from stylesense.cli import main, seed_catalog
from stylesense.infra.database import create_engine
from stylesense.platform.config import Settings


async def test_seed_loads_and_embeds_the_mock_catalog(settings: Settings, migrated: None) -> None:
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE products, users CASCADE"))
    await engine.dispose()

    first = await seed_catalog(settings, seed=2026)
    second = await seed_catalog(settings, seed=2026)

    assert (first["products_created"], first["embedded"]) == (300, 300)
    assert (second["products_created"], second["embedded"], second["price_changes"]) == (0, 0, 0)


async def test_seed_refuses_to_touch_production(settings: Settings) -> None:
    production = settings.model_copy(update={"env": "production"})

    with pytest.raises(SystemExit, match="production"):
        await seed_catalog(production, seed=1)


async def test_llm_commands_configure_routing_and_report_unavailable_ai(
    settings: Settings,
    migrated: None,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE llm_models, llm_task_configs, llm_usage"))
    await engine.dispose()
    monkeypatch.setattr("stylesense.cli.get_settings", lambda: settings)

    assert (
        await asyncio.to_thread(
            main,
            [
                "llm-price",
                "openai:chat-small",
                "--input",
                "0.4",
                "--cached",
                "0.1",
                "--output",
                "1.6",
            ],
        )
        == 0
    )
    assert (
        await asyncio.to_thread(main, ["llm-route", "diagnostics.echo", "openai:chat-small"]) == 0
    )
    check_exit = await asyncio.to_thread(main, ["llm-check"])

    outputs = [json.loads(chunk) for chunk in _json_chunks(capsys.readouterr().out)]
    assert outputs[0]["output_usd_per_mtok"] == "1.600000"
    assert outputs[1]["targets"] == ["openai:chat-small"]
    assert check_exit == 1  # no API key in tests: unavailable, reported, not crashed
    assert outputs[2] == {
        "ok": False,
        "providers": [],
        "error": "no model could serve 'diagnostics.echo'",
    }


def _json_chunks(out: str) -> list[str]:
    chunks, depth, start = [], 0, 0
    for i, ch in enumerate(out):
        if ch == "{":
            depth, start = depth + 1, start if depth else i
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunks.append(out[start : i + 1])
    return chunks
