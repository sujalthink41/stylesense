import asyncio
import json

import pytest
from sqlalchemy import text

from stylesense.bootstrap.container import build_container
from stylesense.cli import dev_token, eval_understand, main, seed_catalog
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


async def test_dev_token_issues_working_tokens_for_a_local_user(
    settings: Settings, migrated: None
) -> None:
    result = await dev_token(settings, email="Dev@Example.com")

    container = build_container(settings)
    try:
        claims = container.token_codec.decode(result["access_token"])
        profile = await container.users.get_active(claims.user_id)
        assert profile.email == "dev@example.com"
        assert await container.auth.refresh(result["refresh_token"])  # a real, rotatable session
    finally:
        await container.aclose()
    again = await dev_token(settings, email="dev@example.com")
    assert again["user_id"] == result["user_id"]  # same user on repeat


async def test_dev_token_refuses_production(settings: Settings) -> None:
    with pytest.raises(SystemExit, match="production"):
        await dev_token(settings.model_copy(update={"env": "production"}), email="x@example.com")


async def test_eval_understand_scores_the_rule_parser(settings: Settings) -> None:
    report = await eval_understand(settings, engine="rules")

    assert report["ok"] is True
    assert report["examples"] >= 50


async def test_eval_understand_llm_reports_unavailable_without_a_key(
    settings: Settings, migrated: None
) -> None:
    report = await eval_understand(settings, engine="llm")

    assert report["ok"] is False
    assert "stylist.understand" in report["error"]
